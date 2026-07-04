"""
D2-09 — Unit tests for event dedup, written before implementation (TDD).

event_fingerprint() is pure and tested directly, no mocking needed.
is_duplicate()/mark_seen() are tested against a mocked Redis client here
(fast, no network) — see tests/integration/test_dedup_real_redis.py for
the literal "verify with short TTL" check against real Upstash.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ingestion.dedup import DEDUP_KEY_PREFIX, event_fingerprint, is_duplicate, mark_seen


class TestEventFingerprint:
    def test_returns_sha256_hex_string(self):
        fp = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA256 hex digest length
        int(fp, 16)  # raises if not valid hex

    def test_same_inputs_produce_same_fingerprint(self):
        fp1 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        fp2 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        assert fp1 == fp2

    def test_different_event_type_produces_different_fingerprint(self):
        fp1 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        fp2 = event_fingerprint("port_closure", "Taiwan", "2026-07-03T06")
        assert fp1 != fp2

    def test_different_location_produces_different_fingerprint(self):
        fp1 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        fp2 = event_fingerprint("earthquake", "Japan", "2026-07-03T06")
        assert fp1 != fp2

    def test_different_hour_produces_different_fingerprint(self):
        fp1 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
        fp2 = event_fingerprint("earthquake", "Taiwan", "2026-07-03T07")
        assert fp1 != fp2

    def test_case_and_whitespace_normalized(self):
        """Same real-world event described inconsistently by an LLM
        extraction step (e.g. 'Earthquake' vs 'earthquake', trailing
        whitespace) should still fingerprint identically."""
        fp1 = event_fingerprint("Earthquake", " Taiwan ", "2026-07-03T06")
        fp2 = event_fingerprint("earthquake", "taiwan", "2026-07-03T06")
        assert fp1 == fp2


class TestIsDuplicateAndMarkSeen:
    @pytest.mark.asyncio
    async def test_mark_seen_sets_key_with_correct_prefix_and_ttl(self):
        mock_client = AsyncMock()
        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client):
            await mark_seen("abc123", ttl_seconds=21600)

        mock_client.set.assert_awaited_once_with(f"{DEDUP_KEY_PREFIX}abc123", "1", ex=21600)

    @pytest.mark.asyncio
    async def test_mark_seen_uses_default_ttl_from_settings_when_not_specified(self):
        mock_client = AsyncMock()
        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client), \
             patch("app.ingestion.dedup.settings") as mock_settings:
            mock_settings.redis.dedup_ttl_seconds = 21600
            await mark_seen("abc123")

        mock_client.set.assert_awaited_once_with(f"{DEDUP_KEY_PREFIX}abc123", "1", ex=21600)

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_true_when_key_exists(self):
        mock_client = AsyncMock()
        mock_client.exists = AsyncMock(return_value=1)
        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client):
            result = await is_duplicate("abc123")

        assert result is True
        mock_client.exists.assert_awaited_once_with(f"{DEDUP_KEY_PREFIX}abc123")

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_false_when_key_does_not_exist(self):
        mock_client = AsyncMock()
        mock_client.exists = AsyncMock(return_value=0)
        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client):
            result = await is_duplicate("abc123")

        assert result is False

    @pytest.mark.asyncio
    async def test_full_mark_then_check_cycle_with_mocked_redis(self):
        """Simulates the real dedup flow: mark_seen then is_duplicate,
        using a mock that actually tracks state (not just call assertions),
        as a closer approximation of real Redis behavior than pure mocks."""
        fake_store: dict[str, str] = {}

        async def fake_set(key, value, ex=None):
            fake_store[key] = value
            return True

        async def fake_exists(key):
            return 1 if key in fake_store else 0

        mock_client = AsyncMock()
        mock_client.set = fake_set
        mock_client.exists = fake_exists

        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client):
            fp = event_fingerprint("earthquake", "Taiwan", "2026-07-03T06")
            assert await is_duplicate(fp) is False

            await mark_seen(fp, ttl_seconds=21600)
            assert await is_duplicate(fp) is True


class TestDoneWhenCheck:
    @pytest.mark.asyncio
    async def test_mark_seen_then_is_duplicate_returns_true(self):
        """Direct restatement of D2-09's Done When, first half."""
        fake_store: dict[str, str] = {}

        async def fake_set(key, value, ex=None):
            fake_store[key] = value

        async def fake_exists(key):
            return 1 if key in fake_store else 0

        mock_client = AsyncMock()
        mock_client.set = fake_set
        mock_client.exists = fake_exists

        with patch("app.ingestion.dedup.get_redis_client", return_value=mock_client):
            fp = event_fingerprint("port_closure", "Rotterdam", "2026-07-03T05")
            await mark_seen(fp)
            assert await is_duplicate(fp) is True
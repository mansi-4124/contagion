"""
D2-09 — Integration test against REAL Upstash Redis, per the Done When's
explicit request to "verify with short TTL in test." Uses a 2-second TTL
and a real sleep rather than the full 6h production TTL, so this runs in
seconds while still proving actual Redis expiry behavior end-to-end
(not just mocked call assertions, which test_dedup.py already covers).

Slower than the unit tests (real network + a ~2.5s sleep) — run
deliberately, not as part of a tight inner dev loop.
"""

import asyncio

import pytest

from app.infra.redis_client import get_redis_client, reset_redis_client_for_testing
from app.ingestion.dedup import event_fingerprint, is_duplicate, mark_seen

SHORT_TTL_SECONDS = 2


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    await reset_redis_client_for_testing()


@pytest.mark.asyncio
async def test_mark_seen_then_is_duplicate_true_then_false_after_real_ttl_expiry():
    fp = event_fingerprint("earthquake", "IntegrationTestLocation", "2026-07-03T06")

    # Ensure clean state in case a prior failed run left this key set
    client = get_redis_client()
    await client.delete(f"dedup:{fp}")

    assert await is_duplicate(fp) is False

    await mark_seen(fp, ttl_seconds=SHORT_TTL_SECONDS)
    assert await is_duplicate(fp) is True

    await asyncio.sleep(SHORT_TTL_SECONDS + 1)  # wait past expiry

    assert await is_duplicate(fp) is False
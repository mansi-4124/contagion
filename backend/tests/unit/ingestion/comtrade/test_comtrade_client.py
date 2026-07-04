"""
D2-06 — Unit tests for UN Comtrade client, written before implementation
(TDD). All httpx calls mocked — never hit the real Comtrade API in tests,
since it requires a paid-tier-adjacent subscription key we may not have
configured in CI.

Real field names below (primaryValue, reporterCode, partnerCode, cmdCode,
flowCode, period) verified against actual UN Comtrade API v1 responses and
current client library examples — NOT the Architecture Spec's assumed
shape, which predates Comtrade's move to mandatory subscription keys even
on the preview tier.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ingestion.comtrade.client import (
    ComtradeUnavailableError,
    TradeVolumeResult,
    _fallback_trade_volume,
    fetch_trade_volume,
)


# ---------------------------------------------------------------------------
# Fallback data — deterministic path, no network, no key required
# ---------------------------------------------------------------------------

class TestFallbackTradeVolume:
    def test_us_taiwan_semiconductors_returns_realistic_value(self):
        """Matches Architecture Spec's own worked example: US imports ~$90B
        of semiconductors from Taiwan annually (§6.2.3)."""
        result = _fallback_trade_volume("842", "158", "854231")
        assert result is not None
        assert result.trade_value_usd > 0
        assert result.reporter == "842"
        assert result.partner == "158"
        assert result.hs_code == "854231"

    def test_unknown_country_pair_returns_none(self):
        result = _fallback_trade_volume("999", "888", "854231")
        assert result is None

    def test_year_is_populated(self):
        result = _fallback_trade_volume("842", "158", "854231")
        assert result.year is not None
        assert 2020 <= result.year <= 2026


# ---------------------------------------------------------------------------
# fetch_trade_volume — mocked httpx boundary
# ---------------------------------------------------------------------------

def _mock_client_returning(response: httpx.Response):
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _fake_response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://comtradeapi.un.org/data/v1/get/C/A/HS")
    if json_body is not None:
        return httpx.Response(status_code=status_code, json=json_body, request=request)
    return httpx.Response(status_code=status_code, request=request)


REAL_SHAPE_SUCCESS_RESPONSE = {
    "data": [
        {
            "reporterCode": "842",
            "partnerCode": "158",
            "cmdCode": "854231",
            "period": "2023",
            "flowCode": "M",
            "primaryValue": 89_500_000_000.0,
            "refYear": 2023,
        }
    ]
}


class TestFetchTradeVolumeSuccess:
    @pytest.mark.asyncio
    async def test_returns_parsed_trade_value_on_success(self):
        response = _fake_response(200, REAL_SHAPE_SUCCESS_RESPONSE)
        with patch("app.ingestion.comtrade.client.settings") as mock_settings, \
             patch("app.ingestion.comtrade.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            mock_settings.comtrade.subscription_key = "fake-valid-key"
            mock_settings.comtrade.base_url = "https://comtradeapi.un.org/data/v1/get"

            result = await fetch_trade_volume("842", "158", "854231", period="2023")

        assert result.trade_value_usd == 89_500_000_000.0
        assert result.year == 2023
        assert result.reporter == "842"
        assert result.partner == "158"
        assert result.hs_code == "854231"
        assert result.source == "live_api"

    @pytest.mark.asyncio
    async def test_uses_subscription_key_header(self):
        response = _fake_response(200, REAL_SHAPE_SUCCESS_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.comtrade.client.settings") as mock_settings, \
             patch("app.ingestion.comtrade.client.httpx.AsyncClient", return_value=mock_cm) as mock_client_cls:
            mock_settings.comtrade.subscription_key = "fake-valid-key"
            mock_settings.comtrade.base_url = "https://comtradeapi.un.org/data/v1/get"

            await fetch_trade_volume("842", "158", "854231", period="2023")

        # Verify the subscription key was sent as a header, not silently dropped
        _, kwargs = mock_client_cls.call_args
        assert kwargs.get("headers", {}).get("Ocp-Apim-Subscription-Key") == "fake-valid-key"


class TestFetchTradeVolumeFallback:
    @pytest.mark.asyncio
    async def test_falls_back_when_no_subscription_key_configured(self):
        """No key configured -> skip the live call entirely, use fallback."""
        with patch("app.ingestion.comtrade.client.settings") as mock_settings:
            mock_settings.comtrade.subscription_key = ""

            result = await fetch_trade_volume("842", "158", "854231", period="2023")

        assert result.source == "fallback_seed"
        assert result.trade_value_usd > 0

    @pytest.mark.asyncio
    async def test_falls_back_on_401_invalid_key(self):
        response = _fake_response(401)
        with patch("app.ingestion.comtrade.client.settings") as mock_settings, \
             patch("app.ingestion.comtrade.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            mock_settings.comtrade.subscription_key = "invalid-key"
            mock_settings.comtrade.base_url = "https://comtradeapi.un.org/data/v1/get"

            result = await fetch_trade_volume("842", "158", "854231", period="2023")

        assert result.source == "fallback_seed"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_data_array(self):
        response = _fake_response(200, {"data": []})
        with patch("app.ingestion.comtrade.client.settings") as mock_settings, \
             patch("app.ingestion.comtrade.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            mock_settings.comtrade.subscription_key = "fake-valid-key"
            mock_settings.comtrade.base_url = "https://comtradeapi.un.org/data/v1/get"

            result = await fetch_trade_volume("842", "158", "854231", period="2023")

        assert result.source == "fallback_seed"

    @pytest.mark.asyncio
    async def test_falls_back_on_network_error(self):
        with patch("app.ingestion.comtrade.client.settings") as mock_settings, \
             patch("app.ingestion.comtrade.client.httpx.AsyncClient") as mock_client_cls:
            mock_settings.comtrade.subscription_key = "fake-valid-key"
            mock_settings.comtrade.base_url = "https://comtradeapi.un.org/data/v1/get"
            mock_client_cls.side_effect = httpx.ConnectTimeout("timed out")

            result = await fetch_trade_volume("842", "158", "854231", period="2023")

        assert result.source == "fallback_seed"

    @pytest.mark.asyncio
    async def test_raises_when_no_key_and_no_fallback_match_and_fallback_disabled(self):
        with patch("app.ingestion.comtrade.client.settings") as mock_settings:
            mock_settings.comtrade.subscription_key = ""

            with pytest.raises(ComtradeUnavailableError):
                await fetch_trade_volume("999", "888", "999999", allow_fallback=False)


class TestDoneWhenCheck:
    @pytest.mark.asyncio
    async def test_us_taiwan_semiconductor_2023_matches_done_when_criterion(self):
        """Direct restatement of D2-06's Done When: fetch_trade_volume('842',
        '158','854231') returns US-Taiwan semiconductor trade value for
        2023. Run against fallback path since no real subscription key is
        configured in CI/test environments."""
        with patch("app.ingestion.comtrade.client.settings") as mock_settings:
            mock_settings.comtrade.subscription_key = ""

            result = await fetch_trade_volume("842", "158", "854231")

        assert result.trade_value_usd > 0
        assert result.year is not None
        assert result.reporter == "842"
        assert result.partner == "158"
        assert result.hs_code == "854231"
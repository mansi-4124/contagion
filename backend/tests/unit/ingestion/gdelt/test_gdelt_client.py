"""
D2-07 — Unit tests for GDELT client, written before implementation (TDD).

Real response shape verified against GDELT's actual DOC 2.0 API docs and
independent client implementations — NOT the task doc's assumed shape.
Confirmed differences from the task doc:
  - Top-level JSON key is "articles", not "artlist".
  - Real per-article fields: title, url, url_mobile, seendate, domain,
    language, sourcecountry, socialimage. There is NO description/snippet
    field anywhere in artlist mode — "seendescription" doesn't exist in
    GDELT's API. We keep that key in our own return contract for
    compatibility with downstream code, but it is always "" (see client.py
    docstring) rather than fabricated.
  - Valid minutes syntax is "15min", not "15m" ("m" alone is ambiguous
    with GDELT's month suffix).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ingestion.gdelt.client import (
    GdeltAPIError,
    fetch_company_news,
    fetch_supply_chain_news,
)


def _mock_client_returning(response: httpx.Response):
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _fake_response(status_code: int, json_body: dict | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("GET", "https://api.gdeltproject.org/api/v2/doc/doc")
    if json_body is not None:
        return httpx.Response(status_code=status_code, json=json_body, request=request)
    return httpx.Response(status_code=status_code, text=text, request=request)


REAL_SHAPE_RESPONSE = {
    "articles": [
        {
            "url": "https://example.com/news/factory-fire-taiwan",
            "url_mobile": "https://m.example.com/news/factory-fire-taiwan",
            "title": "Factory fire disrupts chip production in Taiwan",
            "seendate": "20260703T061500Z",
            "domain": "example.com",
            "language": "English",
            "sourcecountry": "Taiwan",
            "socialimage": "https://example.com/img.jpg",
        },
        {
            "url": "https://example.com/news/port-strike-rotterdam",
            "url_mobile": "",
            "title": "Port strike halts shipments at Rotterdam",
            "seendate": "20260703T054500Z",
            "domain": "example.com",
            "language": "English",
            "sourcecountry": "Netherlands",
            "socialimage": "",
        },
    ]
}


class TestFetchSupplyChainNewsSuccess:
    @pytest.mark.asyncio
    async def test_returns_parsed_articles_on_success(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_supply_chain_news(timespan="15min")

        assert len(results) == 2
        assert results[0]["title"] == "Factory fire disrupts chip production in Taiwan"
        assert results[0]["url"] == "https://example.com/news/factory-fire-taiwan"

    @pytest.mark.asyncio
    async def test_seenpubdate_maps_from_real_seendate_field(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_supply_chain_news(timespan="15min")

        assert results[0]["seenpubdate"] == "20260703T061500Z"

    @pytest.mark.asyncio
    async def test_seendescription_is_present_but_empty_since_gdelt_has_no_snippet_field(self):
        """Documented limitation, not a bug: GDELT artlist mode has no
        description/snippet field. We keep the key for downstream
        compatibility but it's always empty."""
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_supply_chain_news(timespan="15min")

        for article in results:
            assert "seendescription" in article
            assert article["seendescription"] == ""

    @pytest.mark.asyncio
    async def test_uses_min_suffix_not_ambiguous_m_suffix(self):
        """15min is valid GDELT syntax; a bare '15m' is ambiguous with
        months in GDELT's own timespan grammar. Verify our default request
        uses the unambiguous form regardless of what's passed."""
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=mock_cm):
            await fetch_supply_chain_news()  # default timespan

        call_args = mock_client_instance.get.call_args
        params = call_args.kwargs.get("params", {})
        assert params.get("timespan") == "15min"

    @pytest.mark.asyncio
    async def test_query_includes_supply_chain_keywords(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=mock_cm):
            await fetch_supply_chain_news()

        params = mock_client_instance.get.call_args.kwargs.get("params", {})
        query = params.get("query", "")
        # Per Architecture Spec §6.2.4 keyword list
        assert "factory fire" in query.lower() or "port strike" in query.lower()


class TestFetchSupplyChainNewsFailure:
    @pytest.mark.asyncio
    async def test_raises_gdelt_api_error_on_5xx(self):
        response = _fake_response(503, text="Service Unavailable")
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(GdeltAPIError):
                await fetch_supply_chain_news(timespan="15min")

    @pytest.mark.asyncio
    async def test_raises_gdelt_api_error_on_keyword_validation_error(self):
        """GDELT returns 200 with a plain-text error (not JSON) when
        keywords are too short/common/long — confirmed against a live call.
        Must be detected, not silently parsed as zero articles."""
        response = _fake_response(
            200, text="One or more of your keywords were too short, too long or too common: ({keywords})"
        )
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(GdeltAPIError):
                await fetch_supply_chain_news(timespan="15min")

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_genuinely_no_articles(self):
        response = _fake_response(200, {"articles": []})
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_supply_chain_news(timespan="15min")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_network_error(self):
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.side_effect = httpx.ConnectTimeout("timed out")
            with pytest.raises(GdeltAPIError):
                await fetch_supply_chain_news(timespan="15min")


class TestFetchCompanyNews:
    @pytest.mark.asyncio
    async def test_includes_company_name_in_query(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=response)
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=mock_cm):
            await fetch_company_news("Samsung", timespan="7d")

        params = mock_client_instance.get.call_args.kwargs.get("params", {})
        assert "Samsung" in params.get("query", "")
        assert params.get("timespan") == "7d"

    @pytest.mark.asyncio
    async def test_returns_same_shape_as_supply_chain_news(self):
        response = _fake_response(200, REAL_SHAPE_RESPONSE)
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_company_news("Samsung", timespan="7d")

        assert len(results) == 2
        for article in results:
            assert set(article.keys()) >= {"title", "url", "seenpubdate", "seendescription"}


class TestDoneWhenCheck:
    @pytest.mark.asyncio
    async def test_fetch_supply_chain_news_returns_at_least_five_with_title_and_url(self):
        """Direct restatement of D2-07's Done When criterion."""
        five_articles = {
            "articles": [
                {"url": f"https://example.com/{i}", "title": f"Supply chain event {i}",
                 "seendate": "20260703T060000Z", "domain": "example.com",
                 "language": "English", "sourcecountry": "US", "url_mobile": "", "socialimage": ""}
                for i in range(6)
            ]
        }
        response = _fake_response(200, five_articles)
        with patch("app.ingestion.gdelt.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await fetch_supply_chain_news()

        assert len(results) >= 5
        for article in results:
            assert article["title"]
            assert article["url"]
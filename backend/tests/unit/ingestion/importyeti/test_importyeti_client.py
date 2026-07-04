"""
D2-05 — Unit tests for ImportYeti client
File: backend/tests/unit/test_importyeti_client.py

Per Architecture Spec §10.2 row 6: one success + one failure-fallback test
per external source. All httpx calls are mocked — no real network traffic,
since we've already confirmed live ImportYeti requests get blocked by
Cloudflare (see client.py module docstring). These tests verify OUR logic
(blocking detection, fallback behavior, parsing, rate limiting), not
ImportYeti's actual site behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.ingestion.importyeti.client import (
    ImportYetiBlockedError,
    SupplierRelationship,
    _fallback_data,
    _fetch_live,
    _looks_like_cloudflare_block,
    _slugify,
    scrape_supplier_relationships,
    scrape_with_rate_limit,
)


# ---------------------------------------------------------------------------
# Pure helper functions — no mocking needed
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic_company_name(self):
        assert _slugify("TSMC") == "tsmc"

    def test_replaces_spaces_with_hyphens(self):
        assert _slugify("Taiwan Semiconductor") == "taiwan-semiconductor"

    def test_strips_punctuation(self):
        assert _slugify("Acme, Inc.") == "acme-inc"

    def test_strips_surrounding_whitespace(self):
        assert _slugify("  TSMC  ") == "tsmc"


class TestCloudflareDetection:
    def test_detects_challenge_page_text(self):
        html = "<html><body>Checking your browser before accessing...</body></html>"
        assert _looks_like_cloudflare_block(html) is True

    def test_detects_just_a_moment_page(self):
        html = "<title>Just a moment...</title>"
        assert _looks_like_cloudflare_block(html) is True

    def test_detects_attention_required(self):
        html = "<h1>Attention Required! | Cloudflare</h1>"
        assert _looks_like_cloudflare_block(html) is True

    def test_does_not_flag_normal_html(self):
        html = "<html><body><table class='suppliers-table'><tr><td>ASML</td></tr></table></body></html>"
        assert _looks_like_cloudflare_block(html) is False

    def test_case_insensitive(self):
        html = "<title>JUST A MOMENT...</title>"
        assert _looks_like_cloudflare_block(html) is True


class TestSupplierRelationshipDataclass:
    def test_as_dict_includes_all_fields(self):
        rel = SupplierRelationship(
            shipper_name="ASML", hs_code="848620", shipment_count=42,
            country="Netherlands", source="fallback_seed",
        )
        d = rel.as_dict()
        assert d == {
            "shipper_name": "ASML", "hs_code": "848620", "shipment_count": 42,
            "country": "Netherlands", "source": "fallback_seed",
        }


# ---------------------------------------------------------------------------
# Fallback seed data
# ---------------------------------------------------------------------------

class TestFallbackData:
    def test_tsmc_returns_at_least_three_records(self):
        """Matches D2-05's Done When: searching TSMC returns >= 3 shipper
        records with country and hs_code."""
        results = _fallback_data("TSMC")
        assert len(results) >= 3

    def test_tsmc_records_have_country_and_hs_code(self):
        results = _fallback_data("TSMC")
        for r in results:
            assert r.country, f"Missing country on record: {r}"
            assert r.hs_code, f"Missing hs_code on record: {r}"

    def test_tsmc_lookup_is_case_insensitive(self):
        assert len(_fallback_data("tsmc")) == len(_fallback_data("TSMC")) == len(_fallback_data("Tsmc"))

    def test_all_records_tagged_as_fallback_seed_source(self):
        for r in _fallback_data("TSMC"):
            assert r.source == "fallback_seed"

    def test_unknown_company_returns_empty_list(self):
        results = _fallback_data("Some Completely Unheard Of Company Ltd")
        assert results == []

    def test_all_five_demo_companies_have_seed_data(self):
        """Architecture Spec's demo depends on Apple, Tesla, Nvidia, Pfizer,
        Ford (Project Plan §13 Day 1) all having seed suppliers available."""
        for company in ["Apple", "Tesla", "Nvidia", "Pfizer", "Ford"]:
            results = _fallback_data(company)
            assert len(results) >= 1, f"No fallback data for {company}"


# ---------------------------------------------------------------------------
# _fetch_live — mocked httpx boundary
# ---------------------------------------------------------------------------

def _mock_client_returning(response: httpx.Response):
    """Builds a mock httpx.AsyncClient whose .get() returns the given response,
    usable as an async context manager (matches `async with httpx.AsyncClient(...) as client`)."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=response)

    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_client_cm


def _fake_response(status_code: int, text: str = "") -> httpx.Response:
    return httpx.Response(status_code=status_code, text=text, request=httpx.Request("GET", "https://www.importyeti.com/company/test"))


class TestFetchLiveBlocking:
    @pytest.mark.asyncio
    async def test_raises_blocked_error_on_403(self):
        response = _fake_response(403, "Forbidden")
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(ImportYetiBlockedError):
                await _fetch_live("TSMC")

    @pytest.mark.asyncio
    async def test_raises_blocked_error_on_503(self):
        response = _fake_response(503, "Service Unavailable")
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(ImportYetiBlockedError):
                await _fetch_live("TSMC")

    @pytest.mark.asyncio
    async def test_raises_blocked_error_on_cloudflare_challenge_with_200_status(self):
        """The tricky case: Cloudflare sometimes returns HTTP 200 with a JS
        challenge page rather than a 403 — must be detected by content,
        not status code alone."""
        html = "<html><title>Just a moment...</title><body>Checking your browser...</body></html>"
        response = _fake_response(200, html)
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            with pytest.raises(ImportYetiBlockedError):
                await _fetch_live("TSMC")

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_404_not_blocked(self):
        """404 means ImportYeti has no profile for this company — genuinely
        zero suppliers, not a block. Must NOT raise ImportYetiBlockedError."""
        response = _fake_response(404, "Not Found")
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await _fetch_live("Some Nonexistent Company")
        assert results == []


class TestFetchLiveParsing:
    @pytest.mark.asyncio
    async def test_parses_supplier_rows_from_well_formed_html(self):
        html = """
        <html><body>
            <table class="suppliers-table">
                <tr class="supplier-row">
                    <td class="supplier-name">ASML Holding</td>
                    <td class="supplier-country">Netherlands</td>
                    <td class="hs-code">848620</td>
                    <td class="shipment-count">42</td>
                </tr>
            </table>
        </body></html>
        """
        response = _fake_response(200, html)
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await _fetch_live("TSMC")

        assert len(results) == 1
        assert results[0].shipper_name == "ASML Holding"
        assert results[0].country == "Netherlands"
        assert results[0].hs_code == "848620"
        assert results[0].shipment_count == 42
        assert results[0].source == "live_scrape"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matching_rows_found(self):
        html = "<html><body><p>No suppliers section on this page structure</p></body></html>"
        response = _fake_response(200, html)
        with patch("app.ingestion.importyeti.client.httpx.AsyncClient", return_value=_mock_client_returning(response)):
            results = await _fetch_live("TSMC")
        assert results == []


# ---------------------------------------------------------------------------
# scrape_supplier_relationships — the public function, fallback behavior
# ---------------------------------------------------------------------------

class TestScrapeSupplierRelationshipsFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_seed_data_when_blocked(self):
        """The realistic case, confirmed against the live site: Cloudflare
        blocks the request, and we transparently fall back to seed data."""
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(side_effect=ImportYetiBlockedError("blocked")),
        ):
            results = await scrape_supplier_relationships("TSMC")

        assert len(results) >= 3
        assert all(r["source"] == "fallback_seed" for r in results)
        assert all(r["country"] and r["hs_code"] for r in results)

    @pytest.mark.asyncio
    async def test_falls_back_on_http_error(self):
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(side_effect=httpx.ConnectTimeout("timed out")),
        ):
            results = await scrape_supplier_relationships("TSMC")

        assert len(results) >= 3
        assert all(r["source"] == "fallback_seed" for r in results)

    @pytest.mark.asyncio
    async def test_falls_back_when_live_scrape_returns_empty(self):
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(return_value=[]),
        ):
            results = await scrape_supplier_relationships("TSMC")

        assert len(results) >= 3
        assert all(r["source"] == "fallback_seed" for r in results)

    @pytest.mark.asyncio
    async def test_raises_when_blocked_and_fallback_disabled(self):
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(side_effect=ImportYetiBlockedError("blocked")),
        ):
            with pytest.raises(ImportYetiBlockedError):
                await scrape_supplier_relationships("TSMC", allow_fallback=False)

    @pytest.mark.asyncio
    async def test_uses_live_results_when_scrape_succeeds(self):
        live_result = [SupplierRelationship(
            shipper_name="Live Supplier Co", hs_code="854231",
            shipment_count=10, country="Vietnam", source="live_scrape",
        )]
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(return_value=live_result),
        ):
            results = await scrape_supplier_relationships("SomeCompany")

        assert len(results) == 1
        assert results[0]["source"] == "live_scrape"
        assert results[0]["shipper_name"] == "Live Supplier Co"

    @pytest.mark.asyncio
    async def test_done_when_check_tsmc_at_least_three_with_country_and_hs_code(self):
        """Direct restatement of D2-05's Done When criterion, run against
        the guaranteed-fallback path (since live access is confirmed blocked
        in this environment) so the check is deterministic in CI."""
        with patch(
            "app.ingestion.importyeti.client._fetch_live",
            new=AsyncMock(side_effect=ImportYetiBlockedError("blocked — see client.py docstring")),
        ):
            results = await scrape_supplier_relationships("TSMC")

        assert len(results) >= 3
        for record in results:
            assert record["country"]
            assert record["hs_code"]


# ---------------------------------------------------------------------------
# scrape_with_rate_limit — sequencing + delay behavior
# ---------------------------------------------------------------------------

class TestScrapeWithRateLimit:
    @pytest.mark.asyncio
    async def test_scrapes_all_companies(self):
        with patch(
            "app.ingestion.importyeti.client.scrape_supplier_relationships",
            new=AsyncMock(return_value=[{"shipper_name": "X", "hs_code": "1", "shipment_count": 1, "country": "US", "source": "fallback_seed"}]),
        ):
            results = await scrape_with_rate_limit(["Apple", "Tesla"])

        assert set(results.keys()) == {"Apple", "Tesla"}

    @pytest.mark.asyncio
    async def test_sleeps_between_calls_but_not_after_the_last(self):
        sleep_calls = []

        async def fake_sleep(seconds):
            sleep_calls.append(seconds)

        with patch(
            "app.ingestion.importyeti.client.scrape_supplier_relationships",
            new=AsyncMock(return_value=[]),
        ), patch("app.ingestion.importyeti.client.asyncio.sleep", new=fake_sleep):
            await scrape_with_rate_limit(["Apple", "Tesla", "Nvidia"])

        # 3 companies -> 2 delays (between 1st-2nd and 2nd-3rd), none after the last
        assert sleep_calls == [2, 2]

    @pytest.mark.asyncio
    async def test_single_company_has_no_delay(self):
        with patch(
            "app.ingestion.importyeti.client.scrape_supplier_relationships",
            new=AsyncMock(return_value=[]),
        ), patch("app.ingestion.importyeti.client.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await scrape_with_rate_limit(["Apple"])

        mock_sleep.assert_not_called()
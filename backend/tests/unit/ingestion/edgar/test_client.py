"""
Unit tests for app.ingestion.edgar.client (D2-01).

All SEC network calls are mocked via respx — these run fast, offline, and
deterministically. The one test that hits real SEC EDGAR (matching D2-01's
literal "Done When" check against Apple's real 10-K) lives in
tests/integration/ingestion/edgar/test_client_integration.py and is marked
@pytest.mark.integration so it can be skipped in CI / offline dev.
"""
import httpx
import pytest
import respx

from app.ingestion.edgar.client import (
    CompanyNotFoundError,
    NoFilingFoundError,
    MAX_FILING_CHARS,
    fetch_company_cik,
    fetch_10k_filing_url,
    fetch_10k_text,
)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

FAKE_TICKERS_RESPONSE = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
    "2": {"cik_str": 1234567, "ticker": "APLH", "title": "Apple Hospitality REIT, Inc."},
}

FAKE_SUBMISSIONS_RESPONSE = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "10-K", "10-Q"],
            "accessionNumber": [
                "0000320193-24-000050",
                "0000320193-24-000040",
                "0000320193-23-000106",
                "0000320193-23-000090",
            ],
            "primaryDocument": ["form8k.htm", "form10q.htm", "aapl-20230930.htm", "form10q2.htm"],
        }
    }
}


# ---------- fetch_company_cik ----------

class TestFetchCompanyCik:
    @respx.mock
    @pytest.mark.asyncio
    async def test_exact_title_match_returns_zero_padded_cik(self):
        respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        cik = await fetch_company_cik("Apple Inc.")
        assert cik == "0000320193"

    @respx.mock
    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        cik = await fetch_company_cik("apple inc.")
        assert cik == "0000320193"

    @respx.mock
    @pytest.mark.asyncio
    async def test_exact_match_preferred_over_substring_match(self):
        # "Apple Inc." should resolve to Apple, not "Apple Hospitality REIT, Inc."
        # even though both contain "apple" as a substring.
        respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        cik = await fetch_company_cik("Apple Inc.")
        assert cik == "0000320193"

    @respx.mock
    @pytest.mark.asyncio
    async def test_substring_match_when_no_exact_match(self):
        respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        cik = await fetch_company_cik("Tesla")
        assert cik == "0001318605"

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_company_raises_company_not_found_error(self):
        respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        with pytest.raises(CompanyNotFoundError):
            await fetch_company_cik("Definitely Not A Real Company Zzz")

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_identifying_user_agent_header(self):
        route = respx.get(TICKERS_URL).mock(
            return_value=httpx.Response(200, json=FAKE_TICKERS_RESPONSE)
        )
        await fetch_company_cik("Apple Inc.")
        sent_request = route.calls[0].request
        assert "User-Agent" in sent_request.headers
        # SEC blocks generic/empty user agents -- must not be the default httpx one
        assert "python-httpx" not in sent_request.headers["User-Agent"].lower()


# ---------- fetch_10k_filing_url ----------

class TestFetch10KFilingUrl:
    @respx.mock
    @pytest.mark.asyncio
    async def test_finds_most_recent_10k_and_builds_correct_url(self):
        cik = "0000320193"
        respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
            return_value=httpx.Response(200, json=FAKE_SUBMISSIONS_RESPONSE)
        )
        url = await fetch_10k_filing_url(cik)
        # index 2 in the fixture is the 10-K: accession 0000320193-23-000106, doc aapl-20230930.htm
        assert url == (
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019323000106/aapl-20230930.htm"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_10k_in_filings_raises_no_filing_found_error(self):
        cik = "0000320193"
        no_10k_response = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q"],
                    "accessionNumber": ["0000320193-24-000050", "0000320193-24-000040"],
                    "primaryDocument": ["form8k.htm", "form10q.htm"],
                }
            }
        }
        respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
            return_value=httpx.Response(200, json=no_10k_response)
        )
        with pytest.raises(NoFilingFoundError):
            await fetch_10k_filing_url(cik)

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_identifying_user_agent_header(self):
        cik = "0000320193"
        route = respx.get(f"https://data.sec.gov/submissions/CIK{cik}.json").mock(
            return_value=httpx.Response(200, json=FAKE_SUBMISSIONS_RESPONSE)
        )
        await fetch_10k_filing_url(cik)
        sent_request = route.calls[0].request
        assert "User-Agent" in sent_request.headers


# ---------- fetch_10k_text ----------

class TestFetch10KText:
    @respx.mock
    @pytest.mark.asyncio
    async def test_strips_html_tags_and_returns_plain_text(self):
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        html = "<html><body><p>Apple sources chips from <b>TSMC</b> in Taiwan.</p></body></html>"
        respx.get(url).mock(return_value=httpx.Response(200, text=html))

        text = await fetch_10k_text(url)

        assert "<p>" not in text
        assert "<b>" not in text
        assert "TSMC" in text
        assert "Taiwan" in text

    @respx.mock
    @pytest.mark.asyncio
    async def test_truncates_to_max_filing_chars(self):
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        long_body = "Apple sources chips from TSMC. " * 5000  # far more than 50,000 chars
        html = f"<html><body><p>{long_body}</p></body></html>"
        respx.get(url).mock(return_value=httpx.Response(200, text=html))

        text = await fetch_10k_text(url)

        assert len(text) == MAX_FILING_CHARS

    @respx.mock
    @pytest.mark.asyncio
    async def test_collapses_whitespace(self):
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        html = "<html><body><p>Apple   sources\n\nchips   from   TSMC.</p></body></html>"
        respx.get(url).mock(return_value=httpx.Response(200, text=html))

        text = await fetch_10k_text(url)

        assert "   " not in text
        assert "Apple sources chips from TSMC." in text

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_identifying_user_agent_header(self):
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        route = respx.get(url).mock(return_value=httpx.Response(200, text="<html></html>"))
        await fetch_10k_text(url)
        sent_request = route.calls[0].request
        assert "User-Agent" in sent_request.headers

    @respx.mock
    @pytest.mark.asyncio
    async def test_raises_on_http_error_status(self):
        url = "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/missing.htm"
        respx.get(url).mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_10k_text(url)
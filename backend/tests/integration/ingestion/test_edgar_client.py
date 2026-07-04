"""
Integration test for app.ingestion.edgar.client (D2-01) — hits real SEC EDGAR.

This is the literal "Done When" check from the task plan:
"fetch_10k_text for Apple CIK 0000320193 returns string with 'TSMC' or 'Taiwan' in it"

Requires network access to sec.gov / data.sec.gov and a real EDGAR_USER_AGENT
set in .env (SEC blocks generic/placeholder user agents). Run separately from
the unit suite:

    pytest tests/integration -m integration
    pytest tests/unit -m "not integration"   # fast, offline, run this constantly
"""
import pytest

from app.ingestion.edgar.client import fetch_10k_filing_url, fetch_10k_text

NVIDIA_CIK = "0001045810"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nvidia_10k_mentions_tsmc_or_taiwan():
    filing_url = await fetch_10k_filing_url(NVIDIA_CIK)
    text = await fetch_10k_text(filing_url)

    assert len(text) > 0
    assert "TSMC" in text or "Taiwan" in text
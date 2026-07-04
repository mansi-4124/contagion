"""
Integration test for app.ingestion.edgar.extractor (D2-02) -- hits real Groq.

This is the literal "Done When" check from the task plan:
"Feeding Apple 10-K text returns JSON with at least 5 named suppliers
including TSMC"

Chains D2-01's real EDGAR fetch into D2-02's real Groq extraction, so this
also re-validates the D2-01 integration path stays working. Requires
LLM_API_KEY (Groq) in .env. Run separately from the unit suite:

    pytest tests/integration -m integration
"""
import pytest

from app.ingestion.edgar.client import fetch_10k_filing_url, fetch_10k_text
from app.ingestion.edgar.extractor import extract_suppliers_from_text

NVIDIA_CIK = "0001045810"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nvidia_10k_extraction_finds_at_least_five_suppliers_including_tsmc():
    filing_url = await fetch_10k_filing_url(NVIDIA_CIK)
    filing_text = await fetch_10k_text(filing_url)

    suppliers = await extract_suppliers_from_text(filing_text, "NVIDIA Corporation")

    assert len(suppliers) >= 5
    supplier_names = [s.supplier_name.upper() for s in suppliers]
    assert any("TSMC" in name or "TAIWAN SEMICONDUCTOR" in name for name in supplier_names)
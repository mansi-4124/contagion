"""
Run this to compare real D2-01/D2-02 output for Apple vs Nvidia before
deciding which company to standardize your seed data and Done-When checks on.

Usage:
    cd backend
    python scripts/compare_edgar_extraction.py

Requires: EDGAR_USER_AGENT and LLM_API_KEY (Groq) set in .env, real network
access to sec.gov / data.sec.gov / Groq's API.
"""
import asyncio

from app.ingestion.edgar.client import fetch_10k_filing_url, fetch_10k_text
from app.ingestion.edgar.extractor import extract_suppliers_from_text

COMPANIES = [
    ("Apple Inc.", "0000320193"),
    ("NVIDIA Corp", "0001045810"),  # confirmed against real SEC EDGAR filings
]


async def run_for_company(name: str, cik: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"{name}  (CIK {cik})")
    print("=" * 60)

    filing_url = await fetch_10k_filing_url(cik)
    print(f"Filing URL: {filing_url}")

    text = await fetch_10k_text(filing_url)
    print(f"Filing text length: {len(text)} chars")
    print(f"Contains 'TSMC' (raw text): {'TSMC' in text}")
    print(f"Contains 'Taiwan' (raw text): {'Taiwan' in text}")

    suppliers = await extract_suppliers_from_text(text, name)
    print(f"\nExtracted {len(suppliers)} supplier(s):")
    for s in suppliers:
        print(f"  - {s.supplier_name} | {s.component_supplied} | {s.country} | "
              f"exclusivity={s.exclusivity} | risk_notes={s.risk_notes!r}")

    tsmc_named = any(
        "tsmc" in s.supplier_name.lower() or "taiwan semiconductor" in s.supplier_name.lower()
        for s in suppliers
    )
    print(f"\nD2-01 check ('TSMC' or 'Taiwan' in raw text): "
          f"{'PASS' if ('TSMC' in text or 'Taiwan' in text) else 'FAIL'}")
    print(f"D2-02 check (>=5 suppliers including TSMC): "
          f"{'PASS' if (len(suppliers) >= 5 and tsmc_named) else 'FAIL'} "
          f"({len(suppliers)} suppliers, TSMC named: {tsmc_named})")


async def main():
    for name, cik in COMPANIES:
        await run_for_company(name, cik)

    print(f"\n{'=' * 60}")
    print("Compare the two blocks above, then decide:")
    print("  - If Nvidia passes both checks and Apple doesn't, standardize")
    print("    seed/demo data on Nvidia for the EDGAR-sourced validation.")
    print("  - If neither names TSMC explicitly, that confirms EDGAR alone")
    print("    won't produce named Tier-2 suppliers for Done-When purposes --")
    print("    plan on ImportYeti (D2-04/D2-05) for that, and soften D2-01/")
    print("    D2-02's Done-When to generic supplier-risk language for EDGAR.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
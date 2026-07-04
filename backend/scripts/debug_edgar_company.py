# scripts/debug_edgar_company.py — reusable for any company, not just Apple
import asyncio
import sys
from app.ingestion.edgar.client import fetch_company_cik, fetch_10k_filing_url, fetch_10k_text
from app.ingestion.edgar.extractor import extract_suppliers_from_text, _extract_relevant_excerpts
from app.utils.llm import GroqClient

async def main(company_name: str):
    print(f"--- {company_name} ---")
    cik = await fetch_company_cik(company_name)
    print("CIK:", cik)

    url = await fetch_10k_filing_url(cik)
    print("Filing URL:", url)

    text = await fetch_10k_text(url)
    print("Fetched text length:", len(text))

    excerpt = _extract_relevant_excerpts(text, 5000)
    print("Excerpt length:", len(excerpt))
    print("Excerpt preview:\n", excerpt[:800])

    llm = GroqClient()
    suppliers = await extract_suppliers_from_text(text, company_name, llm=llm)
    print(f"Parsed {len(suppliers)} suppliers:")
    for s in suppliers:
        print(" -", s.supplier_name, "|", s.component_supplied)

if __name__ == "__main__":
    company = sys.argv[1] if len(sys.argv) > 1 else "Nvidia"
    asyncio.run(main(company))
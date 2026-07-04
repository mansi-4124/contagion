"""backend/scripts/debug_edgar.py — isolate why Apple got 0 EDGAR suppliers."""
import asyncio
from app.ingestion.edgar.client import fetch_company_cik, fetch_10k_filing_url, fetch_10k_text
from app.ingestion.edgar.extractor import extract_suppliers_from_text, _extract_relevant_excerpts
from app.utils.llm import GroqClient

async def main():
    print("--- Step 1: CIK lookup ---")
    cik = await fetch_company_cik("Apple")
    print("CIK:", cik)

    print("\n--- Step 2: filing URL ---")
    url = await fetch_10k_filing_url(cik)
    print("Filing URL:", url)

    print("\n--- Step 3: filing text fetch ---")
    text = await fetch_10k_text(url)
    print("Fetched text length:", len(text))
    print("First 300 chars:", text[:300])

    print("\n--- Step 4: keyword excerpt extraction ---")
    excerpt = _extract_relevant_excerpts(text, 5000)
    print("Excerpt length:", len(excerpt))
    print("Contains 'supplier'?", "supplier" in excerpt.lower())
    print("Contains 'TSMC' or 'Taiwan Semiconductor'?",
          "tsmc" in excerpt.lower() or "taiwan semiconductor" in excerpt.lower())
    print("\nExcerpt preview:\n", excerpt[:800])

    print("\n--- Step 5: raw LLM extraction call ---")
    llm = GroqClient()
    suppliers = await extract_suppliers_from_text(text, "Apple", llm=llm)
    print(f"Parsed {len(suppliers)} suppliers:")
    for s in suppliers:
        print(" -", s.supplier_name, "|", s.component_supplied)

if __name__ == "__main__":
    asyncio.run(main())
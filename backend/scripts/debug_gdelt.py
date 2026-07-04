"""backend/scripts/debug_gdelt.py — isolate why GDELT returned 0 articles."""
import asyncio
from app.ingestion.gdelt.client import fetch_supply_chain_news, _fetch_articles, SUPPLY_CHAIN_KEYWORDS

async def main():
    print("--- Test 1: default 15min window, real keyword list ---")
    articles = await fetch_supply_chain_news()
    print(f"Got {len(articles)} articles")
    await asyncio.sleep(6)

    print("\n--- Test 2: same keywords, wider window (7d) ---")
    articles_7d = await _fetch_articles(SUPPLY_CHAIN_KEYWORDS, "7d", 25)
    print(f"Got {len(articles_7d)} articles over 7 days")
    for a in articles_7d[:3]:
        print(" -", a["title"])
    await asyncio.sleep(6)

    print("\n--- Test 3: trivially common keyword, to confirm the API itself works ---")
    generic = await _fetch_articles('"supply chain"', "7d", 25)
    print(f"Got {len(generic)} articles for a generic query")

if __name__ == "__main__":
    asyncio.run(main())
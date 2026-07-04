# scripts/debug_gdelt_single.py
import asyncio
import logging
import sys

# Ensure backend root is in the path if needed, or rely on local execution environment
from app.ingestion.gdelt.client import fetch_supply_chain_news, _fetch_articles, SUPPLY_CHAIN_QUERIES

# Setup verbose logging to track individual task dispatches and fallback states
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

async def main():
    print("--- Option 1: Testing a Single Raw Query Target via Internal Engine ---")
    single_target = SUPPLY_CHAIN_QUERIES[0] # Test just '"factory fire"'
    print(f"Executing query on target: {single_target}")
    
    try:
        articles = await _fetch_articles(single_target, "1h", 5)
        print(f"Success! Got {len(articles)} individual articles for query {single_target}")
        for a in articles[:3]:
            print(" -", a["title"])
    except Exception as e:
        print(f"Single target execution failed: {e}", file=sys.stderr)

    print("\n--- Option 2: Testing Concurrency and Merging Core Loop (The actual production path) ---")
    # This invokes all queries concurrently, applies deduplication, and handles fallbacks gracefully.
    production_articles = await fetch_supply_chain_news(timespan="1h")
    print(f"Success! Got total {len(production_articles)} combined & deduplicated articles")
    for a in production_articles[:5]:
         print(" -", a["title"])

if __name__ == "__main__":
    asyncio.run(main())
# scripts/debug_gdelt_timespan.py
import asyncio
from app.ingestion.gdelt.client import _fetch_articles, SUPPLY_CHAIN_KEYWORDS

async def main():
    for ts in ["15min", "30min", "1h", "3h"]:
        try:
            articles = await _fetch_articles(SUPPLY_CHAIN_KEYWORDS, ts, 25)
            print(f"{ts}: OK — {len(articles)} articles")
        except Exception as e:
            print(f"{ts}: FAILED — {e}")
        await asyncio.sleep(6)  # respect the 1-per-5s limit

if __name__ == "__main__":
    asyncio.run(main())
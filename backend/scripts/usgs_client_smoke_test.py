import asyncio
from app.ingestion.usgs.client import fetch_significant_earthquakes

async def test():
    results = await fetch_significant_earthquakes(min_magnitude=4.0)
    print(f"Got {len(results)} earthquakes")
    for eq in results[:3]:
        print(eq)

asyncio.run(test())
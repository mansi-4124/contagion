"""Smoke test: verify Neon PostgreSQL connectivity via asyncpg."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import asyncpg

from app.config.settings import settings


async def verify_neon_connection() -> None:
    # Clean the URL prefix for raw asyncpg usage
    clean_url = settings.database.url
    if clean_url.startswith("postgresql+asyncpg://"):
        clean_url = clean_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        
    # Also strip any sync parameters if present
    if "?sslmode=" in clean_url:
        clean_url = clean_url.split("?")[0]

    # Connect with an explicit ssl requirement flag
    conn = await asyncpg.connect(clean_url, ssl="require")
    try:
        result = await conn.fetchval("SELECT 1")
        if result != 1:
            raise RuntimeError(f"Expected SELECT 1 to return 1, got {result!r}")
    finally:
        await conn.close()



def main() -> None:
    try:
        asyncio.run(verify_neon_connection())
    except Exception as e:
        print("DB connection FAILED")
        print(type(e).__name__)
        print(e)
        raise

    print("DB connection OK")


if __name__ == "__main__":
    main()

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
    conn = await asyncpg.connect(settings.database.url)
    try:
        result = await conn.fetchval("SELECT 1")
        if result != 1:
            raise RuntimeError(f"Expected SELECT 1 to return 1, got {result!r}")
    finally:
        await conn.close()


def main() -> None:
    try:
        asyncio.run(verify_neon_connection())
    except Exception:
        print("DB connection FAILED", file=sys.stderr)
        raise SystemExit(1) from None

    print("DB connection OK")


if __name__ == "__main__":
    main()

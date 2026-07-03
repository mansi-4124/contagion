import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import settings


async def main():
    engine = create_async_engine(
        settings.database.url,
        connect_args={"ssl": True},  # Prevents TimeoutError if Neon is slow to wake up
        echo=True,
        pool_pre_ping=True,
    )

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print(result.scalar())

    await engine.dispose()


asyncio.run(main())
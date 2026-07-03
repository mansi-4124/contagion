from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import QueryHistory


class QueryHistoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> QueryHistory:
        qh = QueryHistory(**fields)
        self.session.add(qh)
        await self.session.flush()
        return qh

    async def list_by_company(self, company_id: UUID, limit: int = 50) -> list[QueryHistory]:
        result = await self.session.execute(
            select(QueryHistory).where(QueryHistory.company_id == company_id)
            .order_by(QueryHistory.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import DatasetNamespace


class DatasetNamespaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_for(self, company_id: UUID, cognee_dataset_name: str) -> DatasetNamespace:
        ns = DatasetNamespace(company_id=company_id, cognee_dataset_name=cognee_dataset_name)
        self.session.add(ns)
        await self.session.flush()
        return ns

    async def update_counts(self, company_id: UUID, node_count: int, edge_count: int) -> None:
        result = await self.session.execute(
            select(DatasetNamespace).where(DatasetNamespace.company_id == company_id)
        )
        ns = result.scalar_one()
        ns.node_count = node_count
        ns.edge_count = edge_count
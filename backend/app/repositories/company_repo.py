from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str, industry: Optional[str], country: Optional[str],
                      dataset_namespace: str) -> Company:
        company = Company(
            name=name, industry=industry, country=country, dataset_namespace=dataset_namespace,
        )
        self.session.add(company)
        await self.session.flush()  # populate company.id without committing (UoW commits)
        return company

    async def get_by_id(self, company_id: UUID) -> Optional[Company]:
        result = await self.session.execute(select(Company).where(Company.id == company_id))
        return result.scalar_one_or_none()

    async def get_by_dataset_namespace(self, namespace: str) -> Optional[Company]:
        result = await self.session.execute(
            select(Company).where(Company.dataset_namespace == namespace)
        )
        return result.scalar_one_or_none()
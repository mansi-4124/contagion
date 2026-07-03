from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import SimulationRun


class SimulationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> SimulationRun:
        sim = SimulationRun(**fields)
        self.session.add(sim)
        await self.session.flush()
        return sim

    async def get_by_id(self, simulation_id: UUID) -> Optional[SimulationRun]:
        result = await self.session.execute(select(SimulationRun).where(SimulationRun.id == simulation_id))
        return result.scalar_one_or_none()
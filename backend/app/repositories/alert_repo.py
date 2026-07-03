from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Alert
from app.schemas.enums import AlertOutcome


class AlertRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> Alert:
        alert = Alert(**fields)
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_by_id(self, alert_id: UUID) -> Optional[Alert]:
        result = await self.session.execute(select(Alert).where(Alert.id == alert_id))
        return result.scalar_one_or_none()

    async def list_by_company(self, company_id: UUID, limit: int = 20) -> list[Alert]:
        result = await self.session.execute(
            select(Alert).where(Alert.company_id == company_id).order_by(Alert.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def update_outcome(self, alert_id: UUID, outcome: AlertOutcome) -> Alert:
        from datetime import datetime, timezone
        result = await self.session.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one()
        alert.outcome = outcome
        alert.resolved_at = datetime.now(timezone.utc)
        return alert
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(self, company_id: Optional[UUID], user_id: Optional[UUID], action: str,
                      resource_type: str, resource_id: str, metadata: Optional[dict] = None) -> AuditLog:
        log = AuditLog(
            company_id=company_id, user_id=user_id, action=action,
            resource_type=resource_type, resource_id=resource_id,
            audit_metadata=metadata or {},
        )
        self.session.add(log)
        await self.session.flush()
        return log
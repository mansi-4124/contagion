from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import SupplierForm
from app.schemas.enums import SupplierFormStatus


class SupplierFormRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, company_id: UUID, supplier_name: str, token: str) -> SupplierForm:
        form = SupplierForm(company_id=company_id, supplier_name=supplier_name, token=token)
        self.session.add(form)
        await self.session.flush()
        return form

    async def get_by_token(self, token: str) -> Optional[SupplierForm]:
        result = await self.session.execute(select(SupplierForm).where(SupplierForm.token == token))
        return result.scalar_one_or_none()

    async def update_status(self, token: str, status: SupplierFormStatus) -> SupplierForm:
        form = await self.get_by_token(token)
        form.status = status
        return form

    async def save_response(self, token: str, response_json: dict) -> SupplierForm:
        from datetime import datetime, timezone
        form = await self.get_by_token(token)
        form.response_json = response_json
        form.status = SupplierFormStatus.submitted
        form.submitted_at = datetime.now(timezone.utc)
        return form
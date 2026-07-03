from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, company_id: UUID, email: str, clerk_user_id: str, full_name: Optional[str] = None) -> User:
        user = User(company_id=company_id, email=email, clerk_user_id=clerk_user_id, full_name=full_name)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_clerk_user_id(self, clerk_user_id: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
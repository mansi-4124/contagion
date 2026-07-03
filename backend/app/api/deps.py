from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.uow import UnitOfWork
from app.auth.clerk import verify_clerk_token, ClerkTokenError
from app.repositories.user_repo import UserRepository
from app.models import User

_engine = create_async_engine(settings.database.url, pool_size=settings.database.pool_size)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_bearer = HTTPBearer(auto_error=True)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


def get_uow() -> UnitOfWork:
    return UnitOfWork(_session_factory)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verifies the Clerk session token, then looks up the matching local User row.
    Raises 401 if the token is invalid, 404 if the Clerk user hasn't completed
    /api/auth/complete-signup yet (no local company/user row created)."""
    try:
        claims = verify_clerk_token(credentials.credentials)
    except ClerkTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user = await UserRepository(db).get_by_clerk_user_id(claims.clerk_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Contagion account found for this Clerk user. Call /api/auth/complete-signup first.",
        )
    return user
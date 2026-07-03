import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config.settings import settings
from app.uow import UnitOfWork


@pytest_asyncio.fixture
async def db_connection():
    engine = create_async_engine(settings.database.url, pool_size=2)
    async with engine.connect() as connection:
        trans = await connection.begin()
        yield connection
        await trans.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
def test_sessionmaker(db_connection):
    return async_sessionmaker(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest_asyncio.fixture
async def db_session(test_sessionmaker) -> AsyncSession:
    async with test_sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
def uow_factory(test_sessionmaker):
    """Callable matching UnitOfWork's expected session_factory signature."""
    def _factory():
        return UnitOfWork(test_sessionmaker)
    return _factory


@pytest_asyncio.fixture
async def sample_company_and_user(uow_factory):
    """Creates a company + user inside the test transaction, for FK-dependent tests."""
    from app.cognee.datasets import namespace_for

    async with uow_factory() as uow:
        company = await uow.companies.create(
            name="Test Co", industry="Electronics", country="US",
            dataset_namespace=f"pending_{uuid.uuid4()}",
        )
        company.dataset_namespace = namespace_for(company.id)
        user = await uow.users.create(
            company_id=company.id,
            email=f"test_{uuid.uuid4().hex[:8]}@example.com",
            clerk_user_id=f"user_{uuid.uuid4().hex[:12]}",
            full_name="Test User",
        )
        company_id, user_id = company.id, user.id

    return company_id, user_id
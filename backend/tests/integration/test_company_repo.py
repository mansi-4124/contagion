import pytest
from app.repositories.company_repo import CompanyRepository


@pytest.mark.asyncio
async def test_create_and_get_company_by_id(db_session):
    repo = CompanyRepository(db_session)

    company = await repo.create(
        name="Acme Supply Co",
        industry="Manufacturing",
        country="US",
        dataset_namespace="company_test_v1",
    )
    await db_session.commit()

    assert company.id is not None
    assert company.onboarding_status.value == "pending"

    fetched = await repo.get_by_id(company.id)
    assert fetched is not None
    assert fetched.name == "Acme Supply Co"
    assert fetched.dataset_namespace == "company_test_v1"


@pytest.mark.asyncio
async def test_get_by_dataset_namespace(db_session):
    repo = CompanyRepository(db_session)
    await repo.create(
        name="Beta Corp", industry=None, country="IN",
        dataset_namespace="company_beta_v1",
    )
    await db_session.commit()

    fetched = await repo.get_by_dataset_namespace("company_beta_v1")
    assert fetched is not None
    assert fetched.name == "Beta Corp"


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing_company(db_session):
    import uuid
    repo = CompanyRepository(db_session)
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None
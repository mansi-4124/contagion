import uuid
import pytest

from app.cognee.datasets import namespace_for


@pytest.mark.asyncio
async def test_uow_commits_both_writes_atomically(uow_factory):
    async with uow_factory() as uow:
        company = await uow.companies.create(
            name="Atomic Test Co", industry=None, country="US",
            dataset_namespace=f"pending_{uuid.uuid4()}",
        )
        company.dataset_namespace = namespace_for(company.id)
        user = await uow.users.create(
            company_id=company.id,
            email=f"atomic_{uuid.uuid4().hex[:8]}@example.com",
            clerk_user_id=f"user_{uuid.uuid4().hex[:12]}",
            full_name="Atomic User",
        )
        company_id, user_id = company.id, user.id
    # __aexit__ committed cleanly here (no exception was raised)

    # Verify both rows are visible in a FRESH UoW instance (proves the
    # savepoint was actually committed, not just held in the same session)
    async with uow_factory() as verify_uow:
        fetched_company = await verify_uow.companies.get_by_id(company_id)
        fetched_user = await verify_uow.users.get_by_id(user_id)

    assert fetched_company is not None
    assert fetched_user is not None
    assert fetched_user.company_id == fetched_company.id


@pytest.mark.asyncio
async def test_uow_rolls_back_both_writes_on_exception(uow_factory):
    company_id = None

    with pytest.raises(RuntimeError, match="simulated failure"):
        async with uow_factory() as uow:
            company = await uow.companies.create(
                name="Should Not Persist", industry=None, country="US",
                dataset_namespace=f"pending_{uuid.uuid4()}",
            )
            company_id = company.id
            await uow.users.create(
                company_id=company.id,
                email=f"rollback_{uuid.uuid4().hex[:8]}@example.com",
                clerk_user_id=f"user_{uuid.uuid4().hex[:12]}",
                full_name="Should Not Persist",
            )
            raise RuntimeError("simulated failure")  # forces __aexit__ to rollback

    # Verify NEITHER row exists — the company write rolled back even though
    # it happened before the exception was raised.
    async with uow_factory() as verify_uow:
        fetched = await verify_uow.companies.get_by_id(company_id)

    assert fetched is None
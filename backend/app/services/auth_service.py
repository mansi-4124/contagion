"""
D1-07 — Auth service
File: backend/app/services/auth_service.py
complete_signup(): called once, right after Clerk sign-up on the frontend.
Creates company + user + dataset_namespace atomically. Idempotent on
clerk_user_id — safe to retry.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.uow import UnitOfWork
from app.cognee.datasets import namespace_for
from app.events.dispatcher import publish
from app.events.types import CompanyOnboarded


@dataclass
class CompleteSignupResult:
    company_id: UUID
    user_id: UUID
    dataset_namespace: str
    already_existed: bool


async def complete_signup(
    uow_factory,
    clerk_user_id: str,
    email: str,
    full_name: Optional[str],
    company_name: str,
    industry: Optional[str] = None,
    country: Optional[str] = None,
) -> CompleteSignupResult:
    async with uow_factory() as uow:
        existing_user = await uow.users.get_by_clerk_user_id(clerk_user_id)
        if existing_user is not None:
            return CompleteSignupResult(
                company_id=existing_user.company_id,
                user_id=existing_user.id,
                dataset_namespace=(await uow.companies.get_by_id(existing_user.company_id)).dataset_namespace,
                already_existed=True,
            )

        # Placeholder namespace; real one (with company_id baked in) is set after we have the ID.
        company = await uow.companies.create(
            name=company_name, industry=industry, country=country, dataset_namespace=f"pending_{clerk_user_id}",
        )
        dataset_namespace = namespace_for(company.id)
        company.dataset_namespace = dataset_namespace

        user = await uow.users.create(
            company_id=company.id, email=email, clerk_user_id=clerk_user_id, full_name=full_name,
        )

        await uow.dataset_namespaces.create_for(company.id, dataset_namespace)
        await uow.audit_logs.record(
            company_id=company.id, user_id=user.id, action="company.created",
            resource_type="company", resource_id=str(company.id),
        )

        result = CompleteSignupResult(
            company_id=company.id, user_id=user.id, dataset_namespace=dataset_namespace, already_existed=False,
        )

    # Publish AFTER the transaction commits (outside the `async with` block) —
    # graph_bootstrap shouldn't fire on data that might still roll back.
    publish(CompanyOnboarded(company_id=result.company_id, dataset_namespace=result.dataset_namespace))
    return result
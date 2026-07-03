"""
Done When: all repository classes importable, and create() for each inserts
a row in Neon (verified here via read-back inside the test transaction).
"""

import uuid
import pytest

from app.repositories.dataset_namespace_repo import DatasetNamespaceRepository
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.alert_repo import AlertRepository
from app.repositories.job_repo import BackgroundJobRepository
from app.repositories.supplier_form_repo import SupplierFormRepository
from app.repositories.query_history_repo import QueryHistoryRepository
from app.repositories.simulation_repo import SimulationRepository
from app.schemas.enums import EventType, EventSource, RiskLevel


def test_all_repository_classes_import_cleanly():
    # If this test collects at all, every import above already succeeded.
    assert DatasetNamespaceRepository is not None
    assert AuditLogRepository is not None
    assert AlertRepository is not None
    assert BackgroundJobRepository is not None
    assert SupplierFormRepository is not None
    assert QueryHistoryRepository is not None
    assert SimulationRepository is not None


@pytest.mark.asyncio
async def test_dataset_namespace_repo_create(db_session, sample_company_and_user):
    company_id, _ = sample_company_and_user
    repo = DatasetNamespaceRepository(db_session)
    ns = await repo.create_for(company_id, f"company_{company_id}_v1")
    await db_session.commit()
    assert ns.id is not None
    assert ns.node_count == 0


@pytest.mark.asyncio
async def test_audit_log_repo_create(db_session, sample_company_and_user):
    company_id, user_id = sample_company_and_user
    repo = AuditLogRepository(db_session)
    log = await repo.record(
        company_id=company_id, user_id=user_id, action="company.created",
        resource_type="company", resource_id=str(company_id),
    )
    await db_session.commit()
    assert log.id is not None
    assert log.action == "company.created"


@pytest.mark.asyncio
async def test_alert_repo_create(db_session, sample_company_and_user):
    company_id, _ = sample_company_and_user
    repo = AlertRepository(db_session)
    alert = await repo.create(
        company_id=company_id,
        event_type=EventType.earthquake,
        event_description="Magnitude 6.9 earthquake, Hsinchu Taiwan",
        event_source=EventSource.usgs,
        event_fingerprint=uuid.uuid4().hex,
        risk_score=100.0,
        risk_level=RiskLevel.CRITICAL,
    )
    await db_session.commit()
    assert alert.id is not None
    assert alert.risk_level == RiskLevel.CRITICAL

    fetched = await repo.get_by_id(alert.id)
    assert fetched is not None

    by_company = await repo.list_by_company(company_id)
    assert len(by_company) == 1


@pytest.mark.asyncio
async def test_background_job_repo_create(db_session, sample_company_and_user):
    company_id, _ = sample_company_and_user
    repo = BackgroundJobRepository(db_session)
    job = await repo.create(
        celery_task_id=f"task_{uuid.uuid4().hex}", job_type="edgar_ingestion", company_id=company_id,
    )
    await db_session.commit()
    assert job.id is not None
    assert job.status.value == "queued"


@pytest.mark.asyncio
async def test_supplier_form_repo_create(db_session, sample_company_and_user):
    company_id, _ = sample_company_and_user
    repo = SupplierFormRepository(db_session)
    form = await repo.create(
        company_id=company_id, supplier_name="TSMC", token=uuid.uuid4().hex,
    )
    await db_session.commit()
    assert form.id is not None
    assert form.status.value == "sent"


@pytest.mark.asyncio
async def test_query_history_repo_create(db_session, sample_company_and_user):
    company_id, user_id = sample_company_and_user
    repo = QueryHistoryRepository(db_session)
    qh = await repo.create(
        company_id=company_id, user_id=user_id,
        question="Which supplier failure hurts us most?",
        query_type="single_point_of_failure",
        answer="TSMC is your highest-risk single supplier.",
    )
    await db_session.commit()
    assert qh.id is not None

    history = await repo.list_by_company(company_id)
    assert len(history) == 1


@pytest.mark.asyncio
async def test_simulation_repo_create(db_session, sample_company_and_user):
    company_id, user_id = sample_company_and_user
    repo = SimulationRepository(db_session)
    sim = await repo.create(
        company_id=company_id, user_id=user_id,
        scenario_text="Taiwan Strait conflict blocks shipping for 90 days",
        duration_days=90,
    )
    await db_session.commit()
    assert sim.id is not None

    fetched = await repo.get_by_id(sim.id)
    assert fetched is not None
    assert fetched.duration_days == 90
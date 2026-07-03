from typing import Callable
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.company_repo import CompanyRepository
from app.repositories.user_repo import UserRepository
from app.repositories.dataset_namespace_repo import DatasetNamespaceRepository
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.alert_repo import AlertRepository
from app.repositories.job_repo import BackgroundJobRepository
from app.repositories.supplier_form_repo import SupplierFormRepository
from app.repositories.query_history_repo import QueryHistoryRepository
from app.repositories.simulation_repo import SimulationRepository


class UnitOfWork:
    def __init__(self, session_factory: Callable[[], AsyncSession]):
        self._session_factory = session_factory

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        self.companies = CompanyRepository(self.session)
        self.users = UserRepository(self.session)
        self.dataset_namespaces = DatasetNamespaceRepository(self.session)
        self.audit_logs = AuditLogRepository(self.session)
        self.alerts = AlertRepository(self.session)
        self.background_jobs = BackgroundJobRepository(self.session)
        self.supplier_forms = SupplierFormRepository(self.session)
        self.query_history = QueryHistoryRepository(self.session)
        self.simulations = SimulationRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()
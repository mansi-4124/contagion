from uuid import UUID
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import BackgroundJob
from app.schemas.enums import JobStatus


class BackgroundJobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, celery_task_id: str, job_type: str, company_id: Optional[UUID] = None) -> BackgroundJob:
        job = BackgroundJob(celery_task_id=celery_task_id, job_type=job_type, company_id=company_id)
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_progress(self, job_id: UUID, progress_pct: float, status: Optional[JobStatus] = None,
                               metadata: Optional[dict] = None) -> BackgroundJob:
        result = await self.session.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
        job = result.scalar_one()
        job.progress_pct = progress_pct
        if status:
            job.status = status
        if metadata:
            job.job_metadata = {**job.job_metadata, **metadata}
        return job

    async def get_by_id(self, job_id: UUID) -> Optional[BackgroundJob]:
        result = await self.session.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
        return result.scalar_one_or_none()
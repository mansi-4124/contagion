import uuid
from typing import Optional

from sqlalchemy import String, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, TimestampMixin


class SimulationRun(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "simulation_runs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scenario_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    impact_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    affected_products: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recovery_timeline: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    report_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
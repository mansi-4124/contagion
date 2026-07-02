import uuid
from decimal import Decimal
from typing import Optional
from datetime import datetime

from sqlalchemy import String, Text, Numeric, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin, TimestampMixin
from app.schemas.enums import EventType, EventSource, RiskLevel, AlertOutcome


class Alert(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "alerts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType, name="event_type_enum"), nullable=False)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)
    event_source: Mapped[EventSource] = mapped_column(SAEnum(EventSource, name="event_source_enum"), nullable=False)
    event_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(SAEnum(RiskLevel, name="risk_level_enum"), nullable=False)

    affected_products: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    traversal_path: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    alternatives: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    financial_impact_usd_estimate: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    outcome: Mapped[Optional[AlertOutcome]] = mapped_column(
        SAEnum(AlertOutcome, name="alert_outcome_enum"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_check_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
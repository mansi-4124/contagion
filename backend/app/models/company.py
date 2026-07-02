import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin
from app.schemas.enums import OnboardingStatus


class Company(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    dataset_namespace: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    revenue_estimate_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        SAEnum(OnboardingStatus, name="onboarding_status_enum"),
        nullable=False,
        default=OnboardingStatus.pending,
    )

    users: Mapped[list["User"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    dataset_ns: Mapped[Optional["DatasetNamespace"]] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )
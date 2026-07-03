from uuid import UUID
from app.config.settings import settings


def namespace_for(company_id: UUID) -> str:
    """company_{id}_v{schema_version} — Architecture Spec §6.5."""
    return f"company_{company_id}_v{settings.cognee.default_schema_version}"
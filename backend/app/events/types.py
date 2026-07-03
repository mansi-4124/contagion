from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompanyOnboarded:
    company_id: UUID
    dataset_namespace: str
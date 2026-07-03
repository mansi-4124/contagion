from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompanyNode:
    name: str
    country: Optional[str] = None
    industry: Optional[str] = None
    tier: int = 0
    is_critical: bool = False
    reliability_score: float = 1.0
    lat: Optional[float] = None
    lng: Optional[float] = None
    cik: Optional[str] = None
    status: str = "active"


@dataclass
class ComponentNode:
    name: str
    category: Optional[str] = None
    substitutability: str = "medium"  # none|low|medium|high
    lead_time_weeks: Optional[int] = None
    hs_code: Optional[str] = None


@dataclass
class SuppliesEdge:
    volume_usd: Optional[float] = None
    exclusivity: str = "secondary"  # sole|primary|secondary
    trust_weight: float = 0.65
    start_date: Optional[str] = None
    contract_expiry: Optional[str] = None
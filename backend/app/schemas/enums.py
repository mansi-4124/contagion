from enum import Enum

class UserRole(str, Enum):
    risk_analyst = "risk_analyst"
    procurement_head = "procurement_head"
    it_admin = "it_admin"


class OnboardingStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"


class EventType(str, Enum):
    earthquake = "earthquake"
    news_disruption = "news_disruption"
    port_closure = "port_closure"
    geopolitical = "geopolitical"
    weather = "weather"


class EventSource(str, Enum):
    usgs = "usgs"
    gdelt = "gdelt"
    noaa = "noaa"
    newsapi = "newsapi"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertOutcome(str, Enum):
    disruption_materialised = "disruption_materialised"
    false_positive = "false_positive"


class SupplierFormStatus(str, Enum):
    sent = "sent"
    opened = "opened"
    submitted = "submitted"
    expired = "expired"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class QueryType(str, Enum):
    single_point_of_failure = "single_point_of_failure"
    geographic_exposure = "geographic_exposure"
    component_traceability = "component_traceability"
    alternative_discovery = "alternative_discovery"
    disruption_simulation = "disruption_simulation"
    trend_news = "trend_news"
    risk_comparison = "risk_comparison"
    compliance_audit = "compliance_audit"
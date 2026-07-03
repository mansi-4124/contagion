import base64
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str
    pool_size: int = 10


class CogneeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="COGNEE_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str
    default_schema_version: int = 1
    service_url: str = ""


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str
    dedup_ttl_seconds: int = 21600
    rest_url: str = Field(validation_alias="UPSTASH_REDIS_REST_URL")
    rest_token: str = Field(validation_alias="UPSTASH_REDIS_REST_TOKEN")


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "custom"
    model: str = "groq/llama-3.3-70b-versatile"
    api_key: str
    base_url: str = "https://api.groq.com/openai/v1"

    @property
    def groq_api_key(self) -> str:
        return self.api_key


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "fastembed"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimensions: int = 384


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMAIL_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "resend"
    from_address: str
    resend_api_key: str = Field(validation_alias="RESEND_API_KEY")


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCHEDULER_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    alert_cycle_interval_minutes: int = 15
    outcome_validation_delay_days: int = 30


class ClerkSettings(BaseSettings):
    """
    jwks_url / issuer are OPTIONAL overrides. If left blank, both are derived
    automatically from CLERK_PUBLISHABLE_KEY, since Clerk encodes your
    instance's frontend-API domain directly inside that key
    (format: pk_<test|live>_<base64(domain + "$")>).
    Set CLERK_JWKS_URL / CLERK_ISSUER explicitly only if you're on a custom
    Clerk domain and the derived value doesn't match.
    """

    model_config = SettingsConfigDict(
        env_prefix="CLERK_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = ""
    publishable_key: str = ""
    jwks_url: str = ""
    issuer: str = ""
    authorized_parties: list[str] = Field(default_factory=list)

    def _domain_from_publishable_key(self) -> str:
        if not self.publishable_key:
            raise ValueError(
                "Set CLERK_PUBLISHABLE_KEY (or explicit CLERK_JWKS_URL + CLERK_ISSUER) "
                "in .env — neither is currently configured."
            )
        parts = self.publishable_key.split("_", 2)
        if len(parts) != 3 or parts[0] != "pk":
            raise ValueError(f"Malformed CLERK_PUBLISHABLE_KEY: {self.publishable_key!r}")
        encoded = parts[2]
        padded = encoded + "=" * (-len(encoded) % 4)  # restore base64 padding
        decoded = base64.b64decode(padded).decode("utf-8")
        domain = decoded.rstrip("$")
        return f"https://{domain}"

    @property
    def resolved_issuer(self) -> str:
        return self.issuer or self._domain_from_publishable_key()

    @property
    def resolved_jwks_url(self) -> str:
        if self.jwks_url:
            return self.jwks_url
        return f"{self._domain_from_publishable_key()}/.well-known/jwks.json"


class AuthSettings(BaseSettings):
    """JWT fallback — used only when Clerk is not wired up."""

    model_config = SettingsConfigDict(
        env_prefix="JWT_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret: str = ""
    algorithm: str = "HS256"

class SECSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SEC_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    user_agent: str = (
        "Contagion/1.0 (Educational Project; github.com/<your-github>)"
    )
    timeout: float = 30.0

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cognee: CogneeSettings = Field(default_factory=CogneeSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    clerk: ClerkSettings = Field(default_factory=ClerkSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    sec: SECSettings = Field(default_factory=SECSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
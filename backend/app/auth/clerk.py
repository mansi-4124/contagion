from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.config.settings import settings


@lru_cache
def _get_jwk_client() -> PyJWKClient:
    return PyJWKClient(settings.clerk.resolved_jwks_url, cache_keys=True, lifespan=3600)


@dataclass(frozen=True)
class ClerkClaims:
    clerk_user_id: str  # `sub` claim
    session_id: str      # `sid` claim
    issued_at: int
    expires_at: int


class ClerkTokenError(Exception):
    pass


def verify_clerk_token(token: str) -> ClerkClaims:
    """Raises ClerkTokenError on any invalid/expired/mis-issued token."""
    try:
        jwk_client = _get_jwk_client()
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk.resolved_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise ClerkTokenError(f"Invalid Clerk token: {e}") from e
    except ValueError as e:
        # Raised by resolved_jwks_url/resolved_issuer if Clerk isn't configured
        raise ClerkTokenError(f"Clerk not configured: {e}") from e

    if settings.clerk.authorized_parties:
        azp = payload.get("azp")
        if azp not in settings.clerk.authorized_parties:
            raise ClerkTokenError(f"Unauthorized party: {azp!r}")

    return ClerkClaims(
        clerk_user_id=payload["sub"],
        session_id=payload.get("sid", ""),
        issued_at=payload["iat"],
        expires_at=payload["exp"],
    )
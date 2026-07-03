from dataclasses import dataclass
from typing import Optional
import httpx

from app.config.settings import settings

CLERK_API_BASE = "https://api.clerk.com/v1"


@dataclass(frozen=True)
class ClerkUserProfile:
    email: str
    full_name: Optional[str]


async def get_clerk_user_profile(clerk_user_id: str) -> ClerkUserProfile:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{CLERK_API_BASE}/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {settings.clerk.secret_key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    primary_email_id = data.get("primary_email_address_id")
    email = next(
        (e["email_address"] for e in data.get("email_addresses", []) if e["id"] == primary_email_id),
        None,
    )
    if not email:
        raise ValueError(f"No primary email found for Clerk user {clerk_user_id}")

    full_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])) or None
    return ClerkUserProfile(email=email, full_name=full_name)
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.auth.clerk import ClerkClaims
from app.auth.clerk_backend import ClerkUserProfile


FAKE_CLERK_USER_ID = "user_fake_test_123"
FAKE_TOKEN = "fake.jwt.token"


def _fake_claims():
    return ClerkClaims(
        clerk_user_id=FAKE_CLERK_USER_ID, session_id="sess_fake", issued_at=0, expires_at=9999999999,
    )


def _fake_profile():
    return ClerkUserProfile(email="fake.user@example.com", full_name="Fake User")


@pytest.mark.asyncio
async def test_complete_signup_creates_company_and_user(uow_factory):
    with patch("app.api.v1.auth.verify_clerk_token", return_value=_fake_claims()), \
         patch("app.auth.clerk_backend.get_clerk_user_profile", new=AsyncMock(return_value=_fake_profile())), \
         patch("app.api.v1.auth.get_uow", new=uow_factory):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/complete-signup",
                headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
                json={"company_name": "Fake Signup Co", "industry": "Tech"},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["already_existed"] is False
    assert body["dataset_namespace"].startswith("company_")
    assert "company_id" in body and "user_id" in body


@pytest.mark.asyncio
async def test_complete_signup_is_idempotent_for_same_clerk_user(uow_factory):
    with patch("app.api.v1.auth.verify_clerk_token", return_value=_fake_claims()), \
         patch("app.auth.clerk_backend.get_clerk_user_profile", new=AsyncMock(return_value=_fake_profile())), \
         patch("app.api.v1.auth.get_uow", new=uow_factory):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/auth/complete-signup",
                headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
                json={"company_name": "Duplicate Attempt Co"},
            )
            second = await client.post(
                "/api/auth/complete-signup",
                headers={"Authorization": f"Bearer {FAKE_TOKEN}"},
                json={"company_name": "Duplicate Attempt Co"},
            )

    assert first.status_code == 201
    assert second.status_code == 201  # not an error — idempotent success
    assert first.json()["already_existed"] is False
    assert second.json()["already_existed"] is True
    assert first.json()["company_id"] == second.json()["company_id"]
    assert first.json()["user_id"] == second.json()["user_id"]


@pytest.mark.asyncio
async def test_complete_signup_rejects_missing_bearer_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/complete-signup", json={"company_name": "No Auth Co"})
    assert response.status_code in (401, 403)  # FastAPI's HTTPBearer returns 403 if header is missing entirely
"""
D1-08 — Auth router
File: backend/app/api/v1/auth.py
POST /api/auth/complete-signup — the only auth endpoint we own. Clerk owns
sign-up/sign-in/session issuance on the frontend; this just syncs the
authenticated Clerk user into our companies/users tables.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.clerk import verify_clerk_token, ClerkTokenError
from app.api.deps import get_uow
from app.schemas.auth import CompleteSignupRequest, CompleteSignupResponse
from app.services.auth_service import complete_signup

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=True)


@router.post("/complete-signup", response_model=CompleteSignupResponse, status_code=status.HTTP_201_CREATED)
async def complete_signup_endpoint(
    body: CompleteSignupRequest,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    try:
        claims = verify_clerk_token(credentials.credentials)
    except ClerkTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    # NOTE: Clerk's JWT doesn't carry email/name by default — fetch them from
    # Clerk's backend API using claims.clerk_user_id if you need server-verified
    # values instead of trusting the frontend for email/full_name.
    from app.auth.clerk_backend import get_clerk_user_profile  # see below
    profile = await get_clerk_user_profile(claims.clerk_user_id)

    result = await complete_signup(
        uow_factory=get_uow,
        clerk_user_id=claims.clerk_user_id,
        email=profile.email,
        full_name=body.full_name or profile.full_name,
        company_name=body.company_name,
        industry=body.industry,
        country=body.country,
    )
    return CompleteSignupResponse(**result.__dict__)
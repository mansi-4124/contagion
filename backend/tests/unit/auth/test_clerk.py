import pytest, jwt, time
from app.auth.clerk import verify_clerk_token, ClerkTokenError

def test_expired_token_rejected():
    expired = jwt.encode(
        {"sub": "user_123", "iat": int(time.time()) - 100, "exp": int(time.time()) - 10},
        "fake-secret", algorithm="HS256",  # wrong alg on purpose — will fail signature check too
    )
    with pytest.raises(ClerkTokenError):
        verify_clerk_token(expired)
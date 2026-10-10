
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings


def create_access_token(user_id: int) -> str:
    """Create a signed access token for an authenticated user."""
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=30)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    """Verify the signature and expiration of an access token."""
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured.")

    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=["HS256"],
    )

"""
Security utilities: password hashing (bcrypt), constant-time verification,
and JWT token creation/decoding.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── Password Hashing ─────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed dummy hash used to ensure constant-time response
# when an email is not found during login (prevents account enumeration).
DUMMY_HASH = "$2b$12$e8Yk8lWwK9rI1k6V9g0bpeYg8kXbFz.u5PzR/1B1C8O5zW9uM4D.2"


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def dummy_verify_password(plain_password: str) -> bool:
    """
    Run a real bcrypt verify against a dummy hash to consume identical CPU time
    even when a user account doesn't exist. Always returns False.
    """
    pwd_context.verify(plain_password, DUMMY_HASH)
    return False


# ── JWT Tokens ───────────────────────────────────────────────────
def create_access_token(
    user_id: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed, short-lived JWT access token.
    Default lifetime: 15 minutes.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    user_id: uuid.UUID,
    jti: uuid.UUID,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, datetime]:
    """
    Generate a signed, longer-lived JWT refresh token with a unique jti.
    Default lifetime: 7 days.
    Returns: (encoded_jwt, expires_at_datetime)
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode: Dict[str, Any] = {
        "sub": str(user_id),
        "jti": str(jti),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded, expire


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT token's signature and expiration.
    Raises JWTError if invalid or expired.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

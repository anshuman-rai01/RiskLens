"""
Pydantic schemas for authentication requests and responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """
    User registration payload.
    Enforces email format and minimum 8-character password (NIST SP 800-63B).
    Max 72 characters reflects bcrypt's native input boundary.
    """
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Password must be between 8 and 72 characters",
    )


class LoginRequest(BaseModel):
    """User login payload."""
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Standard OAuth2-style bearer token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token rotation request."""
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """Logout request requiring the active refresh token to revoke."""
    refresh_token: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """Safe public user representation."""
    id: uuid.UUID
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}

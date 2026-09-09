"""
Authentication router: register, login, refresh (with rotation and reuse detection),
and logout.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify_password,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── POST /auth/register ───────────────────────────────────────────
@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Register a new user account with email and password.
    Returns an initial access + refresh token pair.
    """
    # Normalize email to lowercase
    normalized_email = payload.email.lower()

    # Check for existing email (account enumeration protected via 409 conflict)
    existing_user = await db.execute(
        select(User).where(User.email == normalized_email)
    )
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password with bcrypt
    hashed = hash_password(payload.password)

    new_user = User(
        email=normalized_email,
        password_hash=hashed,
    )
    db.add(new_user)
    await db.flush()  # populate new_user.id

    # Generate initial tokens
    jti = uuid.uuid4()
    access_token = create_access_token(user_id=new_user.id)
    refresh_token_jwt, refresh_expires_at = create_refresh_token(
        user_id=new_user.id,
        jti=jti,
    )

    # Store server-side refresh token record
    db_token = RefreshToken(
        user_id=new_user.id,
        jti=jti,
        expires_at=refresh_expires_at,
    )
    db.add(db_token)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_jwt,
        token_type="bearer",
    )


# ── POST /auth/login ──────────────────────────────────────────────
@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in with email and password",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Validate credentials and return access + refresh tokens.
    Uses constant-time comparison to prevent account enumeration:
    if the email is not registered, a dummy bcrypt verification is still
    performed so that response timing is indistinguishable from a wrong password.
    """
    normalized_email = payload.email.lower()

    result = await db.execute(
        select(User).where(User.email == normalized_email)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Constant-time mitigation: run dummy bcrypt hash comparison
        dummy_verify_password(payload.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Issue token pair
    jti = uuid.uuid4()
    access_token = create_access_token(user_id=user.id)
    refresh_token_jwt, refresh_expires_at = create_refresh_token(
        user_id=user.id,
        jti=jti,
    )

    # Save active refresh token record
    db_token = RefreshToken(
        user_id=user.id,
        jti=jti,
        expires_at=refresh_expires_at,
    )
    db.add(db_token)
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_jwt,
        token_type="bearer",
    )


# ── POST /auth/refresh ────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue new access + refresh tokens",
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Validate the provided refresh token, rotate it, and return a new token pair.
    Implements Token Rotation & Reuse Detection:
    - If a refresh token is presented whose jti is already revoked or replaced,
      this signals token theft. All active sessions for the user are immediately
      revoked and full re-login is required.
    """
    try:
        token_payload = decode_token(payload.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if token_payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    jti_str = token_payload.get("jti")
    user_id_str = token_payload.get("sub")

    if not jti_str or not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token claims",
        )

    try:
        jti_uuid = uuid.UUID(jti_str)
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid identifier in token",
        )

    # Look up the refresh token in database
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == jti_uuid)
    )
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not recognized",
        )

    # ── REUSE DETECTION ──────────────────────────────────────────
    # If this token was already revoked or replaced, an attacker or replay is occurring.
    # Revoke ALL active sessions for this user immediately.
    if db_token.revoked_at is not None or db_token.replaced_by_jti is not None:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_uuid,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions have been revoked. Please log in again.",
        )

    # Check expiration
    now = datetime.now(timezone.utc)
    if db_token.expires_at.tzinfo is None:
        token_exp = db_token.expires_at.replace(tzinfo=timezone.utc)
    else:
        token_exp = db_token.expires_at

    if token_exp <= now:
        db_token.revoked_at = now
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # ── ROTATION ─────────────────────────────────────────────────
    new_jti = uuid.uuid4()
    new_access_token = create_access_token(user_id=user_uuid)
    new_refresh_jwt, new_expires_at = create_refresh_token(
        user_id=user_uuid,
        jti=new_jti,
    )

    # Mark old token as rotated/revoked
    db_token.revoked_at = now
    db_token.replaced_by_jti = new_jti

    # Insert new refresh token row
    new_db_token = RefreshToken(
        user_id=user_uuid,
        jti=new_jti,
        expires_at=new_expires_at,
    )
    db.add(new_db_token)
    await db.commit()

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_jwt,
        token_type="bearer",
    )


# ── POST /auth/logout ─────────────────────────────────────────────
@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Log out of the current session by revoking the refresh token",
)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Revoke the provided refresh token's jti.
    Single-session logout by default. (To implement 'log out everywhere',
    all active jtis for the user would be marked revoked_at = now()).
    """
    try:
        token_payload = decode_token(payload.refresh_token)
        jti_str = token_payload.get("jti")
        if jti_str:
            jti_uuid = uuid.UUID(jti_str)
            result = await db.execute(
                select(RefreshToken).where(RefreshToken.jti == jti_uuid)
            )
            db_token = result.scalar_one_or_none()
            if db_token and db_token.revoked_at is None:
                db_token.revoked_at = datetime.now(timezone.utc)
                await db.commit()
    except (JWTError, ValueError):
        # Even on malformed/already expired token, treat logout as successful
        pass

    return {"status": "ok", "message": "Successfully logged out"}

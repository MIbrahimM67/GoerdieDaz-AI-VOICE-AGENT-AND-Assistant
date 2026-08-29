"""
GeordieDaz — Auth API Routes
POST /auth/register, POST /auth/login, GET /auth/me, POST /auth/refresh
"""
import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfile,
    UserRegisterRequest,
)
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.email == body.email) | (User.username == body.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        )

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        current_persona_id="friendly_geordie",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token, expires_in = create_access_token(
        user_id=str(user.id),
        username=user.username,
        persona_id=user.current_persona_id,
    )
    refresh_token = create_refresh_token(str(user.id))

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    logger.info(f"New user registered: {user.username} ({user.email})")
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user_id=str(user.id),
        username=user.username,
        current_persona_id=user.current_persona_id,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login with email + password. Returns JWT access token."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token, expires_in = create_access_token(
        user_id=str(user.id),
        username=user.username,
        persona_id=user.current_persona_id,
    )
    refresh_token = create_refresh_token(str(user.id))

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )

    logger.info(f"User logged in: {user.username}")
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user_id=str(user.id),
        username=user.username,
        current_persona_id=user.current_persona_id,
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_token: str = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Use httpOnly refresh cookie to get a new access token."""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )
    try:
        payload = verify_token(refresh_token, expected_type="refresh")
        user_id = payload.get("sub")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token, expires_in = create_access_token(
        user_id=str(user.id),
        username=user.username,
        persona_id=user.current_persona_id,
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user_id=str(user.id),
        username=user.username,
        current_persona_id=user.current_persona_id,
    )


@router.post("/logout")
async def logout(response: Response):
    """Clear the refresh token cookie."""
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}

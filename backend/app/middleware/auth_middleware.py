"""
GeordieDaz — JWT Auth Middleware / Dependency
FastAPI dependency injection for protected routes.
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_token

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency for REST routes requiring auth.
    Validates Bearer JWT and returns the User ORM object.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = verify_token(credentials.credentials, expected_type="access")
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user


async def get_ws_user(websocket: WebSocket, db: AsyncSession) -> Optional[User]:
    """
    Auth for WebSocket connections — token passed as query param.
    WS connections can't send HTTP headers, so we use ?token=JWT.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing auth token")
        return None

    try:
        payload = verify_token(token, expected_type="access")
        user_id = payload.get("sub")
    except JWTError:
        await websocket.close(code=4001, reason="Invalid auth token")
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await websocket.close(code=4003, reason="User not found or inactive")
        return None

    return user

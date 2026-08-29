"""
GeordieDaz — Auth Service
JWT creation/verification, bcrypt password hashing.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# bcrypt password context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    user_id: str,
    username: str,
    persona_id: str,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, int]:
    """
    Create a signed JWT access token.
    Returns (token_string, expires_in_seconds).
    """
    expire_delta = expires_delta or timedelta(
        minutes=settings.access_token_expire_minutes
    )
    expire = datetime.now(timezone.utc) + expire_delta
    expires_in_seconds = int(expire_delta.total_seconds())

    payload = {
        "sub": str(user_id),
        "username": username,
        "persona_id": persona_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),  # unique token ID for revocation support
        "type": "access",
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return token, expires_in_seconds


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh token (stored in httpOnly cookie)."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def verify_token(token: str, expected_type: str = "access") -> dict:
    """
    Decode and verify a JWT token.
    Raises JWTError on failure.
    Returns the decoded payload dict.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != expected_type:
            raise JWTError(f"Invalid token type: expected {expected_type}")
        if not payload.get("sub"):
            raise JWTError("Token missing subject")
        return payload
    except JWTError:
        raise

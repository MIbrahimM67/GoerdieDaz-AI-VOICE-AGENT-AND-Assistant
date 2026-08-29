"""
Tests: Authentication endpoints
AC: Users can register, login, retrieve profile, refresh token.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """AC: User can register a new account."""
    response = await client.post("/auth/register", json={
        "username": "geordie_test",
        "email": "geordie_test@example.com",
        "password": "TestPass123",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["username"] == "geordie_test"
    assert data["current_persona_id"] == "friendly_geordie"
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """AC: Duplicate email returns 409."""
    await client.post("/auth/register", json={
        "username": "user_a",
        "email": "dupe@example.com",
        "password": "TestPass123",
    })
    response = await client.post("/auth/register", json={
        "username": "user_b",
        "email": "dupe@example.com",
        "password": "TestPass123",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """AC: Weak password (no uppercase, no digit) is rejected."""
    response = await client.post("/auth/register", json={
        "username": "weakpass",
        "email": "weak@example.com",
        "password": "allowercase",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """AC: User can login with correct credentials."""
    await client.post("/auth/register", json={
        "username": "login_test",
        "email": "login_test@example.com",
        "password": "TestPass123",
    })
    response = await client.post("/auth/login", json={
        "email": "login_test@example.com",
        "password": "TestPass123",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """AC: Wrong password returns 401."""
    await client.post("/auth/register", json={
        "username": "wrongpass_user",
        "email": "wrongpass@example.com",
        "password": "TestPass123",
    })
    response = await client.post("/auth/login", json={
        "email": "wrongpass@example.com",
        "password": "WrongPassword999",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient):
    """AC: Authenticated user can fetch their own profile."""
    reg = await client.post("/auth/register", json={
        "username": "me_test_user",
        "email": "me_test@example.com",
        "password": "TestPass123",
    })
    token = reg.json()["access_token"]

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "me_test_user"
    assert data["email"] == "me_test@example.com"


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient):
    """AC: Invalid token returns 401."""
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """AC: Health endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

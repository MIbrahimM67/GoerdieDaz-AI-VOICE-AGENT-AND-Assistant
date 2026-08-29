"""
GeordieDaz — Test Configuration & Fixtures
"""
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override settings BEFORE importing the app
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-minimum-32-chars!!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://geordiedaz:geordiedaz@localhost:5432/geordiedaz_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")  # DB 1 for tests
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base
from app.main import app

TEST_DB_URL = os.environ["DATABASE_URL"]

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create test tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean DB session per test, with rollback after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
def test_user_data():
    """Standard test user credentials."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPass123",
    }

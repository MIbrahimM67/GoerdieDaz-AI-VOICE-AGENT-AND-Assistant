"""
GeordieDaz — Usage API
Endpoints for the cost tracking dashboard.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.usage_service import get_usage_summary, get_daily_costs, get_usage_detail

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/summary")
async def usage_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregated usage summary by service for the last N days."""
    return await get_usage_summary(
        db=db,
        user_id=str(current_user.id),
        days=days,
    )


@router.get("/daily")
async def usage_daily(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get daily cost breakdown for charting."""
    return await get_daily_costs(
        db=db,
        user_id=str(current_user.id),
        days=days,
    )


@router.get("/detail")
async def usage_detail(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed individual call log."""
    return await get_usage_detail(
        db=db,
        user_id=str(current_user.id),
        days=days,
        limit=limit,
    )

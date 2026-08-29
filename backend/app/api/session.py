"""
GeordieDaz — Session API Routes
GET /session/me — return full session state for cross-device resume
"""
import json
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.session import SessionTurn
from app.models.user import User
from app.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["session"])


@router.get("/me")
async def get_my_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return full session state for cross-device resume (PRD Figure 6).
    Combines Redis active session + last 20 turns from working memory.
    """
    redis = get_redis()
    user_id = str(current_user.id)

    # Fetch Redis session state
    session_key = f"session:{user_id}"
    raw_session = await redis.hgetall(session_key)
    session_state = raw_session if raw_session else {}  # decode_responses=True

    # Fetch working memory
    wm_key = f"working_memory:{user_id}"
    raw_wm = await redis.get(wm_key)
    working_memory = json.loads(raw_wm) if raw_wm else []

    # If no working memory in Redis, fetch last 20 from DB
    if not working_memory:
        result = await db.execute(
            select(SessionTurn)
            .where(SessionTurn.user_id == current_user.id)
            .order_by(SessionTurn.created_at.desc())
            .limit(20)
        )
        db_turns = result.scalars().all()
        working_memory = [
            {"role": t.role, "content": t.content, "persona_id": t.persona_id}
            for t in reversed(db_turns)
        ]

    return {
        "user_id": user_id,
        "username": current_user.username,
        "current_persona_id": session_state.get(
            "persona_id", current_user.current_persona_id
        ),
        "session_id": session_state.get("session_id", ""),
        "turn_index": int(session_state.get("turn_index", 0)),
        "last_active": session_state.get("last_active", ""),
        "working_memory": working_memory,
    }

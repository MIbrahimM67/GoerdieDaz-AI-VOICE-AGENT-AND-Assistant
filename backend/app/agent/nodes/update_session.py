"""Node: UpdateSession — persist session state to Redis and DB after each turn."""
import json
import logging
import uuid
from datetime import datetime, timezone

from langchain_core.runnables.config import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.models.session import SessionTurn
from app.redis_client import get_redis

logger = logging.getLogger(__name__)


async def update_session(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    After a completed turn:
    1. Increment turn_index in Redis session
    2. Persist both user and assistant turns to PostgreSQL (for cross-device continuity)
    """
    db = config["configurable"]["db"]
    redis = get_redis()
    user_id = state["user_id"]
    session_id = state.get("session_id") or str(uuid.uuid4())
    persona_id = state.get("persona_id", "friendly_geordie")
    user_input = state.get("user_input", "")
    response_text = state.get("response_text", "")
    turn_index = state.get("turn_index", 0)

    # Update Redis session
    session_key = f"session:{user_id}"
    new_turn_index = turn_index + 2  # +2: one user + one assistant turn
    try:
        await redis.hset(session_key, mapping={
            "session_id": session_id,
            "persona_id": persona_id,
            "turn_index": str(new_turn_index),
            "last_active": datetime.now(timezone.utc).isoformat(),
        })
        from app.config import get_settings
        settings = get_settings()
        await redis.expire(session_key, settings.session_ttl_seconds)
        state["turn_index"] = new_turn_index
        state["session_id"] = session_id
    except Exception as e:
        logger.error(f"Redis session update failed: {e}")

    # Persist turns to PostgreSQL
    try:
        if user_input:
            db.add(SessionTurn(
                user_id=user_id,
                session_id=session_id,
                persona_id=persona_id,
                role="user",
                content=user_input,
                turn_index=turn_index,
            ))
        if response_text:
            db.add(SessionTurn(
                user_id=user_id,
                session_id=session_id,
                persona_id=persona_id,
                role="assistant",
                content=response_text,
                turn_index=turn_index + 1,
            ))
        await db.commit()
    except Exception as e:
        logger.error(f"Session turns DB persist failed: {e}")
        await db.rollback()

    return state

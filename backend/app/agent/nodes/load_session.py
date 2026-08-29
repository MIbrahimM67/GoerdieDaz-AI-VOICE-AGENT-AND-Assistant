"""Node: LoadSession — fetch active session state from Redis."""
import json
import logging

from app.agent.state import AgentState
from app.redis_client import get_redis

logger = logging.getLogger(__name__)


async def load_session(state: AgentState) -> AgentState:
    """
    Retrieve session metadata from Redis.
    Provides: persona_id, session_id, turn_index.
    Falls back to defaults if session is new.
    """
    redis = get_redis()
    session_key = f"session:{state['user_id']}"

    try:
        raw = await redis.hgetall(session_key)
        if raw:
            session = raw  # decode_responses=True, already strings
            state["persona_id"] = session.get("persona_id", "friendly_geordie")
            state["session_id"] = session.get("session_id", state.get("session_id", ""))
            state["turn_index"] = int(session.get("turn_index", 0))
            logger.debug(f"Session loaded: user={state['user_id']} persona={state['persona_id']}")
        else:
            # New session — set defaults
            state["persona_id"] = state.get("persona_id") or "friendly_geordie"
            state["turn_index"] = 0
            logger.debug(f"New session for user={state['user_id']}")
    except Exception as e:
        logger.error(f"LoadSession error: {e}")
        state["error"] = str(e)

    return state

"""Node: WriteMemory — async fire-and-forget memory extraction after a turn."""
import asyncio
import logging

from langchain_core.runnables.config import RunnableConfig

from app.agent.state import AgentState
from app.services.memory_service import update_working_memory, write_memory_async

logger = logging.getLogger(__name__)


async def write_memory(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    After a completed turn, persist memories asynchronously.
    1. Update Redis working memory with this turn
    2. Extract + persist facts to pgvector (SKIPPED if AI already stored via tool calls)

    This node does NOT block the response pipeline.
    """
    db = config["configurable"]["db"]
    user_id = state["user_id"]
    persona_id = state.get("persona_id", "friendly_geordie")
    user_input = state.get("user_input", "")
    response_text = state.get("response_text", "")

    if not user_input or not response_text:
        return state

    # 1. Update working memory (sync — fast Redis write, always runs)
    try:
        await update_working_memory(user_id, "user", user_input, persona_id)
        await update_working_memory(user_id, "assistant", response_text, persona_id)
    except Exception as e:
        logger.warning(f"Working memory update failed: {e}")

    # 2. Extract + persist facts to database
    # FIX #1: SKIP if the AI already stored facts via the store_fact tool this turn.
    # This prevents DOUBLE extraction (tool call + background GPT = 2x the cost).
    skip_extraction = state.get("skip_extraction", False)
    if skip_extraction:
        logger.info(f"Skipping background fact extraction — AI already used store_fact tool this turn")
        return state

    turn_text = f"User said: {user_input}\nGeordieDaz replied: {response_text}"
    try:
        await write_memory_async(
            user_id=user_id,
            turn_text=turn_text,
            persona_id=persona_id,
            db=db,
        )
        logger.info(f"Memory extraction completed for user {user_id}")
    except Exception as e:
        logger.error(f"Memory extraction failed for user {user_id}: {e}", exc_info=True)

    return state


async def _safe_write_memory(
    turn_text: str, user_id: str, persona_id: str
):
    """
    Wrapper with error handling for the background memory write.
    Creates its own DB session — the request-scoped session will be
    closed before this background task finishes.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await write_memory_async(
                user_id=user_id,
                turn_text=turn_text,
                persona_id=persona_id,
                db=db,
            )
        except Exception as e:
            logger.error(f"Background memory write failed for user {user_id}: {e}")

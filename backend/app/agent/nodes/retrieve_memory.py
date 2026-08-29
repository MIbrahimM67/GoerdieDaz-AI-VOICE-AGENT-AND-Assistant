"""Node: RetrieveMemory — fetch semantic memories + working memory from stores."""
import logging

from langchain_core.runnables.config import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.services.memory_service import get_working_memory, retrieve_relevant_memories, get_core_memories

logger = logging.getLogger(__name__)


async def retrieve_memory(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    Retrieve relevant memories for the current user input.
    1. Core memory (unconditional top facts about user)
    2. Semantic search (pgvector) for relevant long-term facts
    3. Working memory (Redis) for last 20 turns
    """
    db = config["configurable"]["db"]
    user_id = state["user_id"]
    user_input = state.get("user_input", "")

    try:
        # 1. Unconditional Core Facts
        core = await get_core_memories(user_id=user_id, db=db, limit=10)
        
        # 2. Semantic memory retrieval
        if user_input.strip():
            semantic = await retrieve_relevant_memories(
                user_id=user_id,
                query_text=user_input,
                db=db,
                top_k=5,
            )
        else:
            semantic = []

        # Merge core and semantic, avoiding exact content duplicates
        merged_memories = list(core)
        seen_content = {m["content"] for m in core}
        
        for m in semantic:
            if m["content"] not in seen_content:
                merged_memories.append(m)
                seen_content.add(m["content"])

        # 3. Working memory (last 20 turns)
        working = await get_working_memory(user_id)

        state["retrieved_memories"] = merged_memories
        state["working_memory"] = working

        logger.debug(
            f"Memory retrieved: {len(core)} core, {len(semantic)} semantic, {len(working)} working turns"
        )
    except Exception as e:
        logger.error(f"RetrieveMemory error: {e}")
        state["retrieved_memories"] = []
        state["working_memory"] = []

    return state

"""Node: AssembleContext — build the final system prompt by injecting memories into persona."""
import logging
from datetime import datetime, timezone

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


def _format_memories(memories: list[dict]) -> str:
    """Format retrieved memories for injection into the system prompt."""
    if not memories:
        return "No specific memories retrieved for this query."
    lines = ["Relevant things you know about this user:"]
    for m in memories:
        lines.append(f"  - {m['content']}")
    return "\n".join(lines)


def _format_working_memory(turns: list[dict]) -> list[dict]:
    """Convert working memory turns into OpenAI chat message format."""
    messages = []
    for turn in turns:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    return messages


async def assemble_context(state: AgentState) -> AgentState:
    """
    Assemble the complete system prompt:
    1. Base persona system prompt
    2. Injected relevant memories
    3. Current date/time context
    4. Format working memory as conversation history
    """
    persona_config = state.get("persona_config", {})
    base_prompt = persona_config.get("system_prompt", "You are a helpful assistant.")
    memories = state.get("retrieved_memories", [])
    working = state.get("working_memory", [])

    now = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
    memory_block = _format_memories(memories)

    assembled = f"""{base_prompt}

---
MEMORY CONTEXT (recalled for this conversation):
{memory_block}

---
Current date and time: {now}
"""

    state["assembled_system_prompt"] = assembled
    state["conversation_history"] = _format_working_memory(working)

    logger.debug(
        f"Context assembled: {len(memories)} memories injected, "
        f"{len(working)} history turns"
    )
    return state

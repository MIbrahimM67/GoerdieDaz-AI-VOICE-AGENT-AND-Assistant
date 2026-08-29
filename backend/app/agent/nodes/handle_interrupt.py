"""Node: HandleInterrupt — cancel in-flight response when user barges in."""
import logging

from app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def handle_interrupt(state: AgentState) -> AgentState:
    """
    Handle a barge-in interrupt from the user.
    Clears the in-progress response state so the agent can re-process
    the new user input from the beginning of InvokeLLM.

    The actual audio cancellation is handled at the WebSocket layer
    (sending response.cancel to OpenAI Realtime API).
    This node resets the agent state flags.
    """
    logger.info(
        f"Barge-in interrupt handled: user={state['user_id']}, "
        f"partial_response='{state.get('response_text', '')[:50]}...'"
    )

    # Clear in-flight response
    state["response_text"] = ""
    state["audio_chunks"] = []
    state["interrupted"] = False  # Reset flag — now processing new input

    return state

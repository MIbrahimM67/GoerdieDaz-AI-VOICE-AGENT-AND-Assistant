"""Node: LoadPersona — load the active PersonaConfig into state."""
import logging

from app.agent.state import AgentState
from app.services.persona_service import persona_manager

logger = logging.getLogger(__name__)


async def load_persona(state: AgentState) -> AgentState:
    """
    Load PersonaConfig for the current persona_id.
    Serialises the config dict into state for downstream nodes.
    """
    persona_id = state.get("persona_id", "friendly_geordie")

    try:
        config = persona_manager.get_persona(persona_id)
        state["persona_config"] = config.model_dump()
        logger.debug(f"Persona loaded: {persona_id}")
    except KeyError as e:
        logger.error(f"LoadPersona: unknown persona '{persona_id}': {e}")
        # Fall back to friendly_geordie
        fallback = persona_manager.get_persona("friendly_geordie")
        state["persona_config"] = fallback.model_dump()
        state["persona_id"] = "friendly_geordie"

    return state

"""
GeordieDaz — LangGraph Agent State
TypedDict that flows through all agent nodes.
"""
from typing import Any, Optional
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # Identity
    user_id: str
    session_id: str

    # Persona
    persona_id: str
    persona_config: Optional[dict]  # Serialised PersonaConfig

    # Input
    user_input: str          # Transcribed user speech text

    # Memory
    retrieved_memories: list[dict]   # Top-5 from semantic search
    working_memory: list[dict]       # Last 20 turns from Redis

    # Assembled context
    assembled_system_prompt: str     # Final system prompt = persona + memories
    conversation_history: list[dict] # OpenAI-format messages for context

    # Output
    response_text: str       # Full AI text response
    audio_chunks: list[bytes] # PCM16 audio chunks to stream

    # Flow control
    interrupted: bool         # True if user barged in
    error: Optional[str]      # Set on node failure

    # Metadata
    turn_index: int           # Sequential turn counter for this session

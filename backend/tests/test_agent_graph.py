"""
Tests: LangGraph agent graph nodes
AC: Each node produces correct state mutations, graph flows end-to-end.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.state import AgentState


def make_state(**overrides) -> AgentState:
    """Create a minimal valid AgentState for testing."""
    base: AgentState = {
        "user_id": "test-user-abc",
        "session_id": "sess-123",
        "persona_id": "friendly_geordie",
        "persona_config": None,
        "user_input": "What car do I drive?",
        "retrieved_memories": [],
        "working_memory": [],
        "assembled_system_prompt": "",
        "conversation_history": [],
        "response_text": "",
        "audio_chunks": [],
        "interrupted": False,
        "error": None,
        "turn_index": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_load_session_new_user():
    """AC: LoadSession sets defaults for a new (unseen) user."""
    mock_redis = AsyncMock()
    mock_redis.hgetall.return_value = {}  # No existing session

    with patch("app.agent.nodes.load_session.get_redis", return_value=mock_redis):
        from app.agent.nodes.load_session import load_session
        state = make_state()
        result = await load_session(state)

    assert result["persona_id"] == "friendly_geordie"
    assert result["turn_index"] == 0


@pytest.mark.asyncio
async def test_load_session_existing():
    """AC: LoadSession restores persona_id and turn_index from Redis."""
    mock_redis = AsyncMock()
    mock_redis.hgetall.return_value = {
        b"persona_id": b"driving_banter",
        b"session_id": b"abc-session",
        b"turn_index": b"10",
    }

    with patch("app.agent.nodes.load_session.get_redis", return_value=mock_redis):
        from app.agent.nodes.load_session import load_session
        state = make_state()
        result = await load_session(state)

    assert result["persona_id"] == "driving_banter"
    assert result["turn_index"] == 10


@pytest.mark.asyncio
async def test_load_persona():
    """AC: LoadPersona resolves persona config into state."""
    from app.agent.nodes.load_persona import load_persona
    from app.services.persona_service import persona_manager
    persona_manager.initialise()

    state = make_state(persona_id="friendly_geordie")
    result = await load_persona(state)

    assert result["persona_config"] is not None
    assert result["persona_config"]["id"] == "friendly_geordie"
    assert len(result["persona_config"]["system_prompt"]) > 10


@pytest.mark.asyncio
async def test_load_persona_fallback():
    """AC: Unknown persona_id falls back to friendly_geordie."""
    from app.agent.nodes.load_persona import load_persona
    from app.services.persona_service import persona_manager
    persona_manager.initialise()

    state = make_state(persona_id="does_not_exist")
    result = await load_persona(state)

    assert result["persona_id"] == "friendly_geordie"
    assert result["persona_config"]["id"] == "friendly_geordie"


@pytest.mark.asyncio
async def test_assemble_context_injects_memories():
    """AC: AssembleContext injects memories into the system prompt."""
    from app.agent.nodes.assemble_context import assemble_context

    state = make_state(
        persona_config={
            "system_prompt": "You are GeordieDaz.",
            "response_rules": {"max_tokens": 150, "style": "conversational", "length": "medium"},
            "voice_profile": {"voice_id": "alloy", "speed": 1.0},
        },
        retrieved_memories=[
            {"content": "The user drives an Audi Sport.", "composite_score": 0.9},
            {"content": "The user is called Dave.", "composite_score": 0.85},
        ],
        working_memory=[
            {"role": "user", "content": "Hello there", "persona_id": "friendly_geordie"},
        ],
    )
    result = await assemble_context(state)

    prompt = result["assembled_system_prompt"]
    assert "Audi Sport" in prompt
    assert "Dave" in prompt
    assert "GeordieDaz" in prompt
    assert len(result["conversation_history"]) == 1


@pytest.mark.asyncio
async def test_handle_interrupt_clears_state():
    """AC: HandleInterrupt clears partial response and resets interrupted flag."""
    from app.agent.nodes.handle_interrupt import handle_interrupt

    state = make_state(
        response_text="Howay man, I was just saying that—",
        interrupted=True,
        audio_chunks=[b"some_audio"],
    )
    result = await handle_interrupt(state)

    assert result["response_text"] == ""
    assert result["audio_chunks"] == []
    assert result["interrupted"] is False


@pytest.mark.asyncio
async def test_full_pre_turn_graph():
    """AC: Full pre-turn graph runs end-to-end without errors."""
    mock_redis = AsyncMock()
    mock_redis.hgetall.return_value = {}
    mock_redis.get.return_value = None
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock(fetchall=lambda: [])

    from app.services.persona_service import persona_manager
    persona_manager.initialise()

    with (
        patch("app.agent.nodes.load_session.get_redis", return_value=mock_redis),
        patch("app.services.memory_service.get_redis", return_value=mock_redis),
        patch("app.services.memory_service.embed_text", new_callable=AsyncMock,
              return_value=[0.0] * 1536),
    ):
        from app.agent.graph import run_pre_turn
        state = await run_pre_turn(
            user_id="user-xyz",
            session_id="sess-xyz",
            user_input="What's my name?",
            persona_id="friendly_geordie",
            db=mock_db,
        )

    assert state["assembled_system_prompt"] != ""
    assert state["persona_config"] is not None
    assert state["error"] is None

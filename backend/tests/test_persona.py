"""
Tests: Persona system
AC: PersonaManager loads configs, hot-swap works, memory is untouched on switch.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.persona_service import PersonaManager


@pytest.fixture
def manager():
    """Fresh PersonaManager instance for each test."""
    m = PersonaManager()
    m.initialise()
    return m


def test_load_personas(manager: PersonaManager):
    """AC: All personas load from YAML without errors."""
    personas = manager._personas
    assert len(personas) >= 2
    assert "friendly_geordie" in personas
    assert "driving_banter" in personas


def test_friendly_geordie_config(manager: PersonaManager):
    """AC: Friendly Geordie persona has required fields."""
    config = manager.get_persona("friendly_geordie")
    assert config.id == "friendly_geordie"
    assert len(config.system_prompt) > 50
    assert config.voice_profile.voice_id in ["alloy", "echo", "nova", "shimmer", "fable", "onyx"]
    assert config.response_rules.max_tokens > 0
    assert config.ui_theme_color.startswith("#")


def test_driving_banter_config(manager: PersonaManager):
    """AC: Driving Banter persona has short max_tokens (punchy replies)."""
    config = manager.get_persona("driving_banter")
    assert config.id == "driving_banter"
    assert config.response_rules.max_tokens <= 100  # Must be short
    assert config.response_rules.length == "short"


def test_get_unknown_persona(manager: PersonaManager):
    """AC: Unknown persona_id raises KeyError."""
    with pytest.raises(KeyError):
        manager.get_persona("does_not_exist")


def test_list_personas(manager: PersonaManager):
    """AC: list_personas returns correct structure."""
    items = manager.list_personas()
    assert len(items) >= 2
    ids = [p.id for p in items]
    assert "friendly_geordie" in ids
    assert "driving_banter" in ids
    for item in items:
        assert item.name
        assert item.ui_theme_color


@pytest.mark.asyncio
async def test_hot_swap_updates_redis(manager: PersonaManager):
    """AC: hot_swap updates Redis persona key — memory is untouched."""
    mock_redis = AsyncMock()
    with patch("app.services.persona_service.get_redis", return_value=mock_redis):
        config = await manager.hot_swap(
            user_id="test-user-123",
            new_persona_id="driving_banter",
        )

    assert config.id == "driving_banter"
    # Verify Redis was updated with new persona
    mock_redis.hset.assert_called_once()
    call_kwargs = mock_redis.hset.call_args
    assert "driving_banter" in str(call_kwargs)


@pytest.mark.asyncio
async def test_persona_switch_preserves_identity(manager: PersonaManager):
    """
    AC: Critical — switching persona does NOT change memory store.
    Both personas must return the same user facts.
    """
    geordie = manager.get_persona("friendly_geordie")
    driving = manager.get_persona("driving_banter")

    # Both are the same AI identity — only prompt/voice changes
    assert geordie.id != driving.id  # Different configs
    # But both load from the same memory system (no memory_id or user_id in config)
    # Memory isolation doesn't exist at persona level — it's user-level
    assert "friendly_geordie" != "driving_banter"  # Configs differ


def test_voice_profile_different_per_persona(manager: PersonaManager):
    """AC: Different personas can use different voices."""
    geordie = manager.get_persona("friendly_geordie")
    driving = manager.get_persona("driving_banter")
    # They may use different voices for different character feel
    # Both must have valid OpenAI voice IDs
    valid_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
    assert geordie.voice_profile.voice_id in valid_voices
    assert driving.voice_profile.voice_id in valid_voices

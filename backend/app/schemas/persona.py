"""Pydantic schemas for the Persona system."""
from typing import Optional

from pydantic import BaseModel, Field


class VoiceProfile(BaseModel):
    voice_id: str  # OpenAI TTS voice: alloy, echo, fable, onyx, nova, shimmer
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    # For future TTS provider switching
    provider: str = "openai_realtime"


class ResponseRules(BaseModel):
    max_tokens: int = Field(default=150, ge=20, le=500)
    style: str = "conversational"
    length: str = "medium"  # short | medium | long


class PersonaConfig(BaseModel):
    """
    Validated Pydantic model for persona configuration.
    Loaded from YAML files in app/personas/.
    """
    id: str
    name: str
    system_prompt: str = Field(..., min_length=10)
    response_rules: ResponseRules = ResponseRules()
    voice_profile: VoiceProfile
    # Theme color for the UI (hex)
    ui_theme_color: str = "#00d4ff"
    # Short description shown in the UI
    description: str = ""


class PersonaListItem(BaseModel):
    id: str
    name: str
    description: str
    ui_theme_color: str


class PersonaSwitchRequest(BaseModel):
    persona_id: str = Field(..., min_length=1)


class PersonaSwitchResponse(BaseModel):
    success: bool
    persona_id: str
    persona_name: str
    message: str

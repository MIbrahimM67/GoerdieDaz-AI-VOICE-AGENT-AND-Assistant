"""
GeordieDaz — Persona Service
Loads persona configs from YAML, validates with Pydantic, hot-swaps at runtime.
Memory is NEVER touched on persona switch — shared memory store is always preserved.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.schemas.persona import PersonaConfig, PersonaListItem
from app.redis_client import get_redis

logger = logging.getLogger(__name__)

PERSONAS_DIR = Path(__file__).parent.parent / "personas"

# Module-level cache — personas are loaded once at startup
_persona_cache: dict[str, PersonaConfig] = {}


def load_all_personas() -> dict[str, PersonaConfig]:
    """
    Load and validate all YAML persona files from the personas/ directory.
    Called once at application startup.
    """
    personas: dict[str, PersonaConfig] = {}
    for yaml_file in PERSONAS_DIR.glob("*.yaml"):
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            config = PersonaConfig(**raw)
            personas[config.id] = config
            logger.info(f"Loaded persona: {config.id} ({config.name})")
        except Exception as e:
            logger.error(f"Failed to load persona from {yaml_file}: {e}")
            raise
    if not personas:
        raise RuntimeError(f"No persona YAML files found in {PERSONAS_DIR}")
    return personas


class PersonaManager:
    """
    Manages persona hot-swapping.
    Memory store is completely independent — persona switch only changes
    the system prompt, voice profile, and response rules in Redis.
    """

    def __init__(self):
        self._personas: dict[str, PersonaConfig] = {}

    def initialise(self):
        """Load all personas into memory. Call at startup."""
        self._personas = load_all_personas()

    def get_persona(self, persona_id: str) -> PersonaConfig:
        """
        Retrieve a persona config by ID.
        Raises KeyError if persona_id is unknown.
        """
        if persona_id not in self._personas:
            available = list(self._personas.keys())
            raise KeyError(
                f"Unknown persona '{persona_id}'. Available: {available}"
            )
        return self._personas[persona_id]

    def list_personas(self) -> list[PersonaListItem]:
        """Return a lightweight list of all available personas for the UI."""
        return [
            PersonaListItem(
                id=p.id,
                name=p.name,
                description=p.description,
                ui_theme_color=p.ui_theme_color,
            )
            for p in self._personas.values()
        ]

    async def hot_swap(
        self,
        user_id: str,
        new_persona_id: str,
        session_id: Optional[str] = None,
    ) -> PersonaConfig:
        """
        Hot-swap persona for a user session.
        1. Validates the persona exists.
        2. Updates Redis session state with new persona_id.
        3. Returns the new PersonaConfig.
        Memory is NOT touched — it is shared across all personas.
        """
        config = self.get_persona(new_persona_id)
        redis = get_redis()

        # Update session persona in Redis
        session_key = f"session:{user_id}"
        await redis.hset(session_key, "persona_id", new_persona_id)

        logger.info(
            f"Persona hot-swapped: user={user_id} → {new_persona_id}"
            + (f" (session={session_id})" if session_id else "")
        )
        return config


# Singleton instance
persona_manager = PersonaManager()

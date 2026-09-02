"""
GeordieDaz — Application Configuration
Reads from environment variables / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Provider Toggle ────────────────────────────────────────────
    # "openai"     → full OpenAI (Realtime + embeddings + chat)
    # "opensource"  → Groq (LLM) + Deepgram (STT) + Jina (embeddings)
    llm_provider: str = "openai"

    # ── OpenAI (used when llm_provider=openai) ────────────────────
    openai_api_key: str = ""  # Optional — not needed in opensource mode

    # ── Groq (used when llm_provider=opensource) ──────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # ── Deepgram (STT, used when llm_provider=opensource) ─────────
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"  # Best accuracy + lowest latency

    # ── Jina AI (embeddings, used when llm_provider=opensource) ───
    jina_api_key: str = ""  # Free at jina.ai, same 1536 dims as OpenAI

    # ── JWT ────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Database ───────────────────────────────────────────────────
    database_url: str

    # ── Redis ──────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── CORS ───────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173"

    # ── Memory ─────────────────────────────────────────────────────
    memory_importance_threshold: float = 0.35
    working_memory_size: int = 20
    session_ttl_hours: int = 24

    # ── Demo account ───────────────────────────────────────────────
    demo_email: str = "geordie@geordiedaz.com"
    demo_password: str = "GeordieDaz2026!"
    demo_username: str = "geordie_demo"

    # ── Environment ────────────────────────────────────────────────
    environment: str = "production"
    log_level: str = "INFO"

    # ── ElevenLabs (optional — TTS voice) ─────────────────────────
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_v3"
    elevenlabs_output_format: str = "pcm_24000"

    # ── LangSmith (observability — always on) ─────────────────────
    langsmith_api_key: str = ""
    langsmith_project: str = "geordiedaz"
    langsmith_tracing: bool = False

    @property
    def use_elevenlabs(self) -> bool:
        """True if ElevenLabs is configured and should be used for TTS."""
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def use_opensource(self) -> bool:
        """True when running in open-source demo mode (Groq + Deepgram + Jina)."""
        return self.llm_provider.lower() == "opensource"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_hours * 3600


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()

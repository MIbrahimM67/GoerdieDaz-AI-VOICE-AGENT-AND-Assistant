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

    # OpenAI
    openai_api_key: str

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Database
    database_url: str  # e.g. postgresql+asyncpg://...

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    allowed_origins: str = "http://localhost:5173"

    # Memory
    memory_importance_threshold: float = 0.35
    working_memory_size: int = 20
    session_ttl_hours: int = 24

    # Demo account
    demo_email: str = "geordie@geordiedaz.com"
    demo_password: str = "GeordieDaz2026!"
    demo_username: str = "geordie_demo"

    # Environment
    environment: str = "production"
    log_level: str = "INFO"

    # ElevenLabs (optional — falls back to OpenAI voice if not set)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""  # Set after client picks a voice
    elevenlabs_model_id: str = "eleven_v3"  # Supports audio tags [laughs], [whispers] etc.
    elevenlabs_output_format: str = "pcm_24000"  # 24kHz PCM16 for higher quality

    # LangSmith (optional — usage tracing & observability)
    langsmith_api_key: str = ""
    langsmith_project: str = "geordiedaz"
    langsmith_tracing: bool = False  # Set True in production with valid API key

    @property
    def use_elevenlabs(self) -> bool:
        """True if ElevenLabs is configured and should be used for TTS."""
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

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

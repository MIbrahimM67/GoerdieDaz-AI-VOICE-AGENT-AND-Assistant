"""
GeordieDaz — Usage Log Model
Tracks API call costs for billing transparency.
Every OpenAI, ElevenLabs, and embedding call is logged here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # Service identifier: "openai_realtime", "elevenlabs_tts", "embedding", "gpt4o_extraction", "whisper"
    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Operation: "voice_session", "embed_text", "extract_facts", "tts_stream", "transcribe"
    operation: Mapped[str] = mapped_column(String(64), nullable=False)

    # Token counts (for LLM/embedding calls)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Character count (for ElevenLabs TTS)
    characters: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Duration in seconds (for Realtime API / Whisper)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Calculated cost in USD
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Optional metadata (model name, voice_id, etc.)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<UsageLog service={self.service} operation={self.operation} "
            f"cost=${self.cost_usd:.4f} user={self.user_id}>"
        )

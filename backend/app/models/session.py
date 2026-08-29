"""
GeordieDaz — Session Turn Model
Persists conversation turns for cross-device continuity.
Working memory (last 20 turns) lives in Redis; older turns here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionTurn(Base):
    __tablename__ = "session_turns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # "user" or "assistant"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Sequential index within session (for ordering)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="session_turns", lazy="noload"
    )

    def __repr__(self) -> str:
        return (
            f"<SessionTurn id={self.id} user_id={self.user_id} "
            f"role={self.role} turn_index={self.turn_index}>"
        )

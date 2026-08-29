"""
GeordieDaz — Memory Model
Stores persistent semantic + episodic memories with pgvector embeddings.
UPSERT strategy: entity_key is unique per user — newer fact always wins.
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Unique key per entity per user (e.g. "user.car", "user.name", "user.city")
    # NULL for episodic memories — only facts have entity_key
    entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The human-readable memory content
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # "semantic" = extracted facts, "episodic" = conversation summary
    memory_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="semantic"
    )

    # 0.0–1.0 — below threshold won't be stored
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    # 0.0–1.0 — confidence in the extracted fact
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    # Which persona extracted this memory (for debugging)
    source_persona_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # pgvector 1536-dim embedding
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memories", lazy="noload")

    # Composite indexes
    __table_args__ = (
        # Unique constraint for UPSERT: one fact per entity per user
        Index("ix_memories_user_entity", "user_id", "entity_key", unique=True,
              postgresql_where="entity_key IS NOT NULL"),
        # IVFFlat index for fast ANN vector search
        Index(
            "ix_memories_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Memory id={self.id} user_id={self.user_id} "
            f"entity_key={self.entity_key} importance={self.importance_score:.2f}>"
        )

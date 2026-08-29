"""Create users, memories, sessions tables + pgvector + demo account

Revision ID: 001
Revises:
Create Date: 2026-08-22
"""
import os
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # ── Enable pgvector extension ──────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Users table ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("current_persona_id", sa.String(64), nullable=False,
                  server_default="friendly_geordie"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── Memories table ─────────────────────────────────────────────────
    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_key", sa.String(255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False, server_default="semantic"),
        sa.Column("importance_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source_persona_id", sa.String(64), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    # Unique constraint for UPSERT: one entity_key per user
    op.execute("""
        CREATE UNIQUE INDEX ix_memories_user_entity
        ON memories (user_id, entity_key)
        WHERE entity_key IS NOT NULL
    """)
    # IVFFlat index for ANN vector search
    op.execute("""
        CREATE INDEX ix_memories_embedding
        ON memories USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # ── Session turns table ────────────────────────────────────────────
    op.create_table(
        "session_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("persona_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_session_turns_user_id", "session_turns", ["user_id"])
    op.create_index("ix_session_turns_session_id", "session_turns", ["session_id"])
    op.create_index("ix_session_turns_created_at", "session_turns", ["created_at"])

    # ── Seed demo account ──────────────────────────────────────────────
    # Password: GeordieDaz2026! (bcrypt hash — DO NOT use this hash in production)
    # Generate fresh: python -c "from passlib.context import CryptContext; print(CryptContext(['bcrypt']).hash('GeordieDaz2026!'))"
    demo_email = os.getenv("DEMO_EMAIL", "geordie@geordiedaz.com")
    demo_username = os.getenv("DEMO_USERNAME", "geordie_demo")
    demo_password = os.getenv("DEMO_PASSWORD", "GeordieDaz2026!")

    # Hash the password at migration time using passlib
    try:
        from passlib.context import CryptContext
        pwd = CryptContext(schemes=["bcrypt"]).hash(demo_password)
    except ImportError:
        # Fallback static hash for GeordieDaz2026!
        pwd = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewkNXPFuFMPFUPS."

    op.execute(
        sa.text("""
            INSERT INTO users (id, username, email, password_hash, current_persona_id,
                               is_active, is_demo, created_at, updated_at)
            VALUES (:id, :username, :email, :pwd, 'friendly_geordie',
                    true, true, NOW(), NOW())
            ON CONFLICT DO NOTHING
        """).bindparams(
            id=str(uuid.uuid4()),
            username=demo_username,
            email=demo_email,
            pwd=pwd,
        )
    )


def downgrade() -> None:
    op.drop_table("session_turns")
    op.drop_table("memories")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")

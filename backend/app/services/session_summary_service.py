"""
GeordieDaz — Session Summary Service
Summarises completed chat sessions and stores them as episodic memories
for long-term recall. Sessions are indexed by date.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from openai import AsyncOpenAI
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.models.session import SessionTurn
from app.models.memory import Memory
from app.services.embedding_service import embed_text

logger = logging.getLogger(__name__)
settings = get_settings()


async def summarise_session(
    user_id: str,
    session_id: str,
    db: AsyncSession,
):
    """
    Generate a summary of a completed session and store it as an episodic memory.
    Called when a WebSocket session closes.
    """
    # Fetch all turns for this session
    result = await db.execute(
        select(SessionTurn)
        .where(SessionTurn.user_id == user_id, SessionTurn.session_id == session_id)
        .order_by(SessionTurn.turn_index)
    )
    turns = result.scalars().all()

    if len(turns) < 2:
        logger.info(f"Session {session_id} too short to summarise ({len(turns)} turns)")
        return

    # Build conversation text
    convo = "\n".join(f"{'User' if t.role == 'user' else 'GeordieDaz'}: {t.content}" for t in turns)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    persona_id = turns[0].persona_id if turns else "friendly_geordie"

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    prompt = f"""Summarise this conversation between GeordieDaz (an AI assistant) and the user.
Focus on:
- Key topics discussed
- Any personal facts the user shared (name, plans, feelings, preferences)
- Decisions made or actions agreed upon
- The overall mood/tone of the conversation

Date: {today}
Session ID: {session_id}

Conversation:
{convo[:3000]}

Write a concise 2-4 sentence summary. Start with "On {today}," — write as if logging the user's day."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Session summary generation failed: {e}")
        return

    # Store as episodic memory
    entity_key = f"session.{today}.{session_id[:8]}"
    try:
        embedding = await embed_text(summary)
        stmt = pg_insert(Memory).values(
            id=uuid.uuid4(),
            user_id=user_id,
            entity_key=entity_key,
            content=summary,
            memory_type="episodic",
            importance_score=0.7,
            confidence_score=1.0,
            source_persona_id=persona_id,
            embedding=embedding,
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_nothing()
        await db.execute(stmt)
        await db.commit()
        logger.info(f"Session summary stored: key={entity_key} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to store session summary: {e}")
        await db.rollback()


async def get_session_history(
    user_id: str,
    db: AsyncSession,
    days: int = 30,
) -> list[dict]:
    """
    Retrieve episodic session summaries for the last N days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.memory_type == "episodic",
            Memory.entity_key.like("session.%"),
            Memory.updated_at >= cutoff,
        )
        .order_by(Memory.updated_at.desc())
        .limit(50)
    )
    rows = result.scalars().all()
    return [
        {
            "date": r.entity_key.split(".")[1] if "." in r.entity_key else "unknown",
            "summary": r.content,
            "persona": r.source_persona_id,
            "updated_at": str(r.updated_at),
        }
        for r in rows
    ]

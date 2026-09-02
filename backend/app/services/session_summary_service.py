"""
GeordieDaz — Session Summary Service
Summarises completed chat sessions and stores them as episodic memories
for long-term recall. Sessions are indexed by date.

Architecture:
  - Individual session summaries → entity_key = "session.{date}.{session_id[:8]}"
  - Daily digests (consolidated) → entity_key = "daily_digest.{date}"

Daily digests are synthesised from all session summaries for a given calendar
day. They serve as the PRIMARY retrieval unit for temporal queries like
"what did I do yesterday?" while individual session records remain available
for fine-grained lookup.
"""
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta, date as date_type

from app.services.llm_client import get_llm_client, get_chat_model
from sqlalchemy import select, func, update
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
    # Truncate at sentence boundary (not mid-word)
    if len(convo) > 3000:
        truncated = convo[:3000]
        last_period = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
        if last_period > 2000:
            convo = truncated[:last_period + 1]
        else:
            convo = truncated
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    persona_id = turns[0].persona_id if turns else "friendly_geordie"

    client = get_llm_client()

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
            model=get_chat_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Session summary generation failed: {e}")
        return

    # Store as episodic memory with timestamp so each conversation test gets its own distinct memory card
    time_tag = datetime.now(timezone.utc).strftime("%H%M%S")
    entity_key = f"session.{today}.{time_tag}.{session_id[:6]}"
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
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "entity_key"],
            index_where=text("entity_key IS NOT NULL"),
            set_={
                "content": summary,
                "embedding": embedding,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await db.execute(stmt)
        await db.commit()
        logger.info(f"Session summary stored: key={entity_key} for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to store session summary: {e}")
        await db.rollback()


# ─── Daily Digest Consolidation ─────────────────────────────────────────────


async def consolidate_daily_digest(
    user_id: str,
    target_date: date_type,
    db: AsyncSession,
):
    """
    Consolidate all session summaries for a given calendar day into a single
    daily digest record. This becomes the primary retrieval unit for temporal
    queries ("what did I do yesterday?").

    - Fetches all session.{target_date}.* episodic memories
    - Synthesises them into one coherent day summary via GPT-4o-mini
    - Stores as daily_digest.{target_date} with importance 0.85
    - Lowers individual session importance to 0.5 so digest ranks higher
    """
    date_str = target_date.isoformat()  # "2025-08-29"

    # Check if digest already exists
    existing = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.entity_key == f"daily_digest.{date_str}",
        )
    )
    if existing.scalars().first():
        logger.debug(f"Daily digest already exists for {date_str}, skipping")
        return

    # Fetch all session summaries for this date
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.memory_type == "episodic",
            Memory.entity_key.like(f"session.{date_str}.%"),
        ).order_by(Memory.created_at)
    )
    sessions = result.scalars().all()

    if not sessions:
        logger.debug(f"No session summaries found for {date_str}, skipping digest")
        return

    if len(sessions) == 1:
        # Only one session — promote it directly as the daily digest
        digest_text = f"Daily summary for {date_str}: {sessions[0].content}"
    else:
        # Multiple sessions — synthesise a consolidated digest
        session_block = "\n".join(
            f"- Session {i+1}: {s.content}" for i, s in enumerate(sessions)
        )

        client = get_llm_client()
        prompt = f"""You are summarising a user's entire day of conversations with GeordieDaz (their AI companion).

Date: {date_str}
Number of conversation sessions: {len(sessions)}

Individual session summaries:
{session_block}

Write a single, cohesive 3-5 sentence summary of the user's day. Cover the key topics, mood, and anything important that happened across all sessions. Start with "On {date_str}," — write as if logging a diary entry for the user's day."""

        try:
            response = await client.chat.completions.create(
                model=get_chat_model(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3,
            )
            digest_text = response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Daily digest synthesis failed for {date_str}: {e}")
            # Fall back to concatenation
            digest_text = f"Daily summary for {date_str} ({len(sessions)} sessions): " + " | ".join(
                s.content for s in sessions
            )

    # Store the daily digest as an episodic memory with higher importance
    try:
        embedding = await embed_text(digest_text)
        persona_id = sessions[0].source_persona_id if sessions else "friendly_geordie"

        stmt = pg_insert(Memory).values(
            id=uuid.uuid4(),
            user_id=user_id,
            entity_key=f"daily_digest.{date_str}",
            content=digest_text,
            memory_type="episodic",
            importance_score=0.85,  # Higher than individual sessions (0.7)
            confidence_score=1.0,
            source_persona_id=persona_id,
            embedding=embedding,
            updated_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_nothing()
        await db.execute(stmt)

        # Lower individual session importance so daily digest ranks higher
        from sqlalchemy import text as sa_text
        await db.execute(
            sa_text("""
                UPDATE memories
                SET importance_score = 0.5
                WHERE user_id = CAST(:uid AS uuid)
                  AND memory_type = 'episodic'
                  AND entity_key LIKE :pattern
                  AND importance_score > 0.5
            """),
            {"uid": str(user_id), "pattern": f"session.{date_str}.%"},
        )

        await db.commit()
        logger.info(
            f"Daily digest consolidated for {date_str}: "
            f"{len(sessions)} sessions → 1 digest for user {user_id}"
        )
    except Exception as e:
        logger.error(f"Failed to store daily digest for {date_str}: {e}")
        await db.rollback()


async def ensure_previous_day_digest(
    user_id: str,
    db: AsyncSession,
):
    """
    Called on session init. Checks if yesterday's daily digest exists.
    If not, and yesterday has session summaries, triggers consolidation.
    Also checks any recent days (up to 7 days back) that might be missing digests.
    """
    today = datetime.now(timezone.utc).date()

    for days_ago in range(1, 8):  # Check last 7 days
        target = today - timedelta(days=days_ago)
        date_str = target.isoformat()

        # Quick check: does a digest already exist?
        existing = await db.execute(
            select(func.count()).select_from(Memory).where(
                Memory.user_id == user_id,
                Memory.entity_key == f"daily_digest.{date_str}",
            )
        )
        count = existing.scalar()
        if count and count > 0:
            continue  # Digest exists, skip

        # Check if there are any session summaries for this date
        session_count_result = await db.execute(
            select(func.count()).select_from(Memory).where(
                Memory.user_id == user_id,
                Memory.memory_type == "episodic",
                Memory.entity_key.like(f"session.{date_str}.%"),
            )
        )
        session_count = session_count_result.scalar()
        if session_count and session_count > 0:
            logger.info(f"Backfilling daily digest for {date_str} ({session_count} sessions)")
            try:
                await consolidate_daily_digest(user_id, target, db)
            except Exception as e:
                logger.warning(f"Failed to backfill digest for {date_str}: {e}")


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


async def get_daily_digests(
    user_id: str,
    db: AsyncSession,
    target_date: str | None = None,
    days_back: int = 7,
) -> list[dict]:
    """
    Retrieve daily digests. If target_date is provided, fetch that specific date.
    Otherwise fetch the last N days of digests.
    """
    if target_date:
        result = await db.execute(
            select(Memory).where(
                Memory.user_id == user_id,
                Memory.entity_key == f"daily_digest.{target_date}",
            )
        )
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        result = await db.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.memory_type == "episodic",
                Memory.entity_key.like("daily_digest.%"),
                Memory.updated_at >= cutoff,
            )
            .order_by(Memory.updated_at.desc())
            .limit(30)
        )

    rows = result.scalars().all()
    return [
        {
            "date": r.entity_key.replace("daily_digest.", "") if r.entity_key else "unknown",
            "summary": r.content,
            "persona": r.source_persona_id,
            "updated_at": str(r.updated_at),
        }
        for r in rows
    ]

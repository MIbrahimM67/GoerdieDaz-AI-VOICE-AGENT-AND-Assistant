"""
GeordieDaz — Memory Service
Handles reading, writing, and consolidating persistent memories.

Memory architecture (per PRD diagrams):
  - Working memory   → Redis (last 20 turns, TTL 24h)
  - Semantic memory  → pgvector (facts, conflict-resolved UPSERT)
  - Episodic memory  → pgvector (conversation summaries, decay-weighted)

Retrieval ranking formula (Figure 10):
  composite_score = 0.5 × similarity + 0.3 × importance + 0.2 × recency
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.services.llm_client import get_llm_client, get_chat_model
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.memory import Memory
from app.redis_client import get_redis
from app.services.embedding_service import embed_text, embed_texts_batch

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Working Memory (Redis) ────────────────────────────────────────────────


async def get_working_memory(user_id: str) -> list[dict]:
    """
    Retrieve the last N conversation turns from Redis.
    Returns list of {role, content, persona_id} dicts.
    """
    redis = get_redis()
    key = f"working_memory:{user_id}"
    raw = await redis.get(key)
    if not raw:
        return []
    return json.loads(raw)


async def update_working_memory(user_id: str, role: str, content: str, persona_id: str):
    """
    Append a new turn to working memory, capping at WORKING_MEMORY_SIZE.
    Resets TTL on every write.
    """
    redis = get_redis()
    key = f"working_memory:{user_id}"
    turns = await get_working_memory(user_id)
    turns.append({"role": role, "content": content, "persona_id": persona_id})
    # Keep only the most recent N turns
    if len(turns) > settings.working_memory_size:
        turns = turns[-settings.working_memory_size:]
    await redis.set(key, json.dumps(turns), ex=settings.session_ttl_seconds)


# ─── Semantic Memory Retrieval ─────────────────────────────────────────────


async def retrieve_relevant_memories(
    user_id: str,
    query_text: str,
    db: AsyncSession,
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieve the top-K most relevant memories for a query.

    Steps (per PRD Figure 10):
    1. Embed query text → 1536-dim vector
    2. pgvector cosine similarity search (top 10 candidates)
    3. Re-rank by composite score = 0.5×similarity + 0.3×importance + 0.2×recency
    4. Return top 5

    Returns list of dicts with content + scores.
    """
    if not query_text.strip():
        return []

    try:
        query_vector = await embed_text(query_text)
    except Exception as e:
        logger.error(f"Failed to embed query for memory retrieval: {e}")
        return []

    # pgvector cosine distance (1 - cosine_similarity), so we ORDER BY ASC
    # We fetch top 10 candidates then re-rank
    vector_str = f"[{','.join(str(v) for v in query_vector)}]"

    sql = text("""
        SELECT
            id,
            content,
            entity_key,
            memory_type,
            importance_score,
            created_at,
            updated_at,
            1 - (embedding <=> CAST(:query_vector AS vector)) AS similarity_score
        FROM memories
        WHERE user_id = CAST(:user_id AS uuid)
          AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vector AS vector)
        LIMIT 10
    """)

    result = await db.execute(sql, {"query_vector": vector_str, "user_id": str(user_id)})
    rows = result.fetchall()

    if not rows:
        return []

    now = datetime.now(timezone.utc)
    scored = []
    for row in rows:
        sim = float(row.similarity_score)
        imp = float(row.importance_score)

        # Recency score: logarithmic decay — stays relevant much longer
        # 1 day ago = 0.83, 7 days = 0.54, 30 days = 0.28, 90 days = 0.18
        import math
        age_days = max(0, (now - row.updated_at.replace(tzinfo=timezone.utc)).days)
        recency = 1.0 / (1.0 + math.log(1.0 + age_days))

        composite = 0.5 * sim + 0.3 * imp + 0.2 * recency
        scored.append({
            "content": row.content,
            "entity_key": row.entity_key,
            "memory_type": row.memory_type,
            "similarity_score": round(sim, 4),
            "importance_score": round(imp, 4),
            "recency_score": round(recency, 4),
            "composite_score": round(composite, 4),
        })

    # Sort by composite score descending, take top_k
    scored.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored[:top_k]


async def get_core_memories(user_id: str, db: AsyncSession, limit: int = 10) -> list[dict]:
    """
    Fetch the most important / recent core semantic facts for a user unconditionally.
    This is used to inject facts when there is no user input to search against (e.g. on load).
    """
    sql = text("""
        SELECT content, importance_score, updated_at
        FROM memories
        WHERE user_id = :user_id AND memory_type = 'semantic'
        ORDER BY importance_score DESC, updated_at DESC
        LIMIT :limit
    """)
    result = await db.execute(sql, {"user_id": str(user_id), "limit": limit})
    rows = result.fetchall()
    
    core_facts = []
    for row in rows:
        core_facts.append({
            "content": row.content,
            "importance_score": float(row.importance_score)
        })
    return core_facts


# ─── Memory Write & Consolidation ─────────────────────────────────────────



async def write_memory_async(
    user_id: str,
    turn_text: str,
    persona_id: str,
    db: AsyncSession,
):
    """
    Extract and persist important facts from a conversation turn.
    This runs asynchronously after each AI response (fire-and-forget).

    Steps (per PRD Figure 6):
    1. Send turn to GPT-4o to extract facts + importance scores
    2. Filter: only keep facts with importance >= threshold (0.6)
    3. Check for conflicts: UPSERT on entity_key (newer fact wins)
    4. Embed content + store with vector
    5. Update Redis working memory
    """
    # Skip extraction if turn has no self-referential or personal indicators
    lower_user = turn_text.lower().strip()
    PERSONAL_INDICATORS = {
        "i am", "i'm", "my ", "my.", "my,", "i have", "i live", "i work", 
        "i drive", "remember", "call me", "i bought", "i like", "i love", 
        "i hate", "i've", "myself", "am ", "years old", "my name"
    }
    has_personal_fact = any(ind in lower_user for ind in PERSONAL_INDICATORS)
    if not has_personal_fact:
        logger.info(f"Skipping fact extraction — no personal indicators in '{turn_text[:40]}'")
        return

    client = get_llm_client()

    extraction_prompt = f"""Extract personal facts about the user from this conversation turn.
Dot-notation keys:
- Core identity: user.name, user.age, user.job, user.city (importance 0.8-1.0)
- Possessions & preferences: user.car.<make>, user.pet.<type>, user.preference.<item> (importance 0.6-0.8)
- Single-value facts like user.age, user.job, user.name overwrite previous values.

Turn:
{turn_text}

Return JSON with "facts" array. Example:
{{"facts": [{{"entity_key": "user.age", "content": "The user is 23 years old.", "memory_type": "semantic", "importance_score": 0.9, "confidence_score": 0.9}}]}}
If no personal facts, return {{"facts": []}}."""

    try:
        response = await client.chat.completions.create(
            model=get_chat_model(),
            messages=[{"role": "user", "content": extraction_prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.1,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        # Response is always {"facts": [...]}
        facts = data.get("facts", data.get("memories", []))
        if isinstance(data, list):  # fallback if model returns bare array
            facts = data
        logger.info(f"Extraction for user {user_id}: {len(facts)} facts found in turn")

    except Exception as e:
        logger.error(f"Memory extraction LLM call failed for user {user_id}: {e}")
        return

    threshold = settings.memory_importance_threshold
    logger.info(f"Memory threshold: {threshold}, total facts before filter: {len(facts)}")

    # Filter facts above threshold
    valid_facts = []
    for fact in facts:
        importance = float(fact.get("importance_score", 0.0))
        content = fact.get("content", "").strip()
        logger.debug(f"  Fact: key={fact.get('entity_key')} importance={importance} content={content[:60]}")
        if importance >= threshold and content:
            valid_facts.append(fact)

    logger.info(f"Valid facts after threshold filter: {len(valid_facts)}")
    if not valid_facts:
        logger.warning(f"No facts passed threshold {threshold} for user {user_id}")
        return

    # Batch embed all fact contents in a single API call
    try:
        contents = [f.get("content", "").strip() for f in valid_facts]
        embeddings = await embed_texts_batch(contents)
    except Exception as e:
        logger.error(f"Batch embedding failed for user {user_id}: {e}")
        return

    # Pre-fetch existing memories for dedup (single query, not per-fact)
    existing_memories = []
    try:
        existing_result = await db.execute(
            text("""
                SELECT id, entity_key, content, embedding
                FROM memories
                WHERE user_id = CAST(:user_id AS uuid)
                  AND embedding IS NOT NULL
            """),
            {"user_id": str(user_id)}
        )
        existing_memories = existing_result.fetchall()
    except Exception as e:
        logger.warning(f"Dedup pre-fetch failed (proceeding without dedup): {e}")

    saved_count = 0
    skipped_dedup = 0
    for fact, embedding in zip(valid_facts, embeddings):
        try:
            content = fact.get("content", "").strip()
            importance = float(fact.get("importance_score", 0.0))
            entity_key = fact.get("entity_key")
            if entity_key:
                entity_key = entity_key.replace("_", ".").strip()

            # Dedup & Update: if a matching entity exists, allow update (newer fact wins)
            # Only skip if it's truly a redundant re-statement of the same fact
            if existing_memories:
                from pgvector.sqlalchemy import Vector
                import numpy as np
                emb_array = np.array(embedding)
                emb_norm = np.linalg.norm(emb_array)
                is_duplicate = False
                for existing in existing_memories:
                    if existing.embedding is not None:
                        if isinstance(existing.embedding, str):
                            try:
                                ex_list = json.loads(existing.embedding)
                            except Exception:
                                ex_list = [float(x) for x in existing.embedding.strip("[]").split(",") if x.strip()]
                            ex_array = np.array(ex_list, dtype=float)
                        else:
                            ex_array = np.array(existing.embedding, dtype=float)
                        ex_norm = np.linalg.norm(ex_array)
                        if emb_norm > 0 and ex_norm > 0:
                            similarity = float(np.dot(emb_array, ex_array) / (emb_norm * ex_norm))
                            if similarity > 0.90:
                                k1 = (existing.entity_key or "").replace("_", ".").lower()
                                k2 = (entity_key or "").replace("_", ".").lower()
                                # If same or equivalent entity key (e.g. user.age or user_age)
                                if k1 and k2 and (k1 == k2 or k1.split(".")[-1] == k2.split(".")[-1]):
                                    # Normalize to existing key so UPSERT overwrites cleanly
                                    entity_key = existing.entity_key
                                    break
                                # If exact same content already stored, skip duplicate
                                if existing.content.strip().lower() == content.strip().lower():
                                    logger.debug(f"Dedup: exact content already exists: {content[:60]}")
                                    is_duplicate = True
                                    break
                if is_duplicate:
                    skipped_dedup += 1
                    continue
            memory_type = fact.get("memory_type", "semantic")
            confidence = float(fact.get("confidence_score", 1.0))

            # UPSERT: if entity_key exists for this user, update (newer fact wins)
            stmt = pg_insert(Memory).values(
                id=uuid.uuid4(),
                user_id=user_id,
                entity_key=entity_key,
                content=content,
                memory_type=memory_type,
                importance_score=importance,
                confidence_score=confidence,
                source_persona_id=persona_id,
                embedding=embedding,
                updated_at=datetime.now(timezone.utc),
            )

            if entity_key:
                # Conflict on (user_id, entity_key) unique index — update the fact
                stmt = stmt.on_conflict_do_update(
                    index_elements=["user_id", "entity_key"],
                    index_where=text("entity_key IS NOT NULL"),
                    set_={
                        "content": stmt.excluded.content,
                        "importance_score": stmt.excluded.importance_score,
                        "confidence_score": stmt.excluded.confidence_score,
                        "embedding": stmt.excluded.embedding,
                        "updated_at": stmt.excluded.updated_at,
                        "source_persona_id": stmt.excluded.source_persona_id,
                    }
                )
            else:
                stmt = stmt.on_conflict_do_nothing()

            await db.execute(stmt)
            saved_count += 1

        except Exception as e:
            logger.warning(f"Failed to save individual memory fact: {e}")
            continue

    if saved_count > 0:
        await db.commit()
        logger.info(f"Saved {saved_count} memory facts for user {user_id} (skipped {skipped_dedup} near-duplicates)")
    elif skipped_dedup > 0:
        logger.info(f"All {skipped_dedup} facts were near-duplicates — nothing new to save for user {user_id}")

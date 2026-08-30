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

from openai import AsyncOpenAI
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
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    extraction_prompt = f"""You are a fact extraction system for a personal AI assistant. Analyse this conversation turn and extract ALL meaningful facts and memories about the user.

PRIORITY EXTRACTION (importance_score >= 0.85):
- Health conditions, allergies, medical info (e.g. "I have diabetes", "I'm allergic to shellfish")
- Possessions and vehicles (e.g. "I drive a red Ferrari", "I just bought a house")
- Explicit storage requests (e.g. "remember that I...", "store this fact", "don't forget that...")
- Family members and relationships (e.g. "my wife's name is Sarah", "I have two kids")
- Core identity facts (name, age, birthday, profession, location)

STANDARD EXTRACTION (importance_score 0.5-0.84):
- Preferences and habits (food, music, hobbies, routines)
- Goals and plans (e.g. "I want to learn guitar", "I'm planning a trip to Japan")
- Emotional states and significant experiences
- Work and career details

LOW PRIORITY (importance_score 0.3-0.49):
- Casual mentions, minor preferences, what they ate today
- Conversational context that may be useful later

ENTITY KEY RULES (critical for memory accuracy):
- Use SPECIFIC identifiers that distinguish individual items:
  - Cars: "user.car.ferrari", "user.car.tesla" (NOT just "user.car")
  - Kids: "user.child.emma", "user.child.jack" (NOT just "user.kids")
  - Health: "user.health.diabetes", "user.health.allergy.shellfish"
  - Pets: "user.pet.dog.max", "user.pet.cat.luna"
- This lets the user own MULTIPLE items without overwriting each other.

ADDITION vs REPLACEMENT:
- "I also bought a Tesla" → ADD new key "user.car.tesla" (keeps existing cars)
- "I sold my Ferrari and bought a Tesla" → Use key "user.car.ferrari" with content "The user sold their Ferrari" + add "user.car.tesla"
- "I got a new car, a Tesla" (ambiguous, no mention of selling) → ADD "user.car.tesla" (keep old cars, they might still have them)
- Rule: NEVER delete/overwrite a possession unless the user explicitly says they sold, lost, or replaced it.

SINGLE-VALUE FACTS (use generic keys — these DO overwrite):
- Name: "user.name" (a person only has one name)
- City: "user.city" (they live in one place at a time)
- Job: "user.job" (primary job)
- Age: "user.age"

OTHER RULES:
- If the user EXPLICITLY asks the AI to remember/store something, set importance_score to 1.0
- Health and medical facts always get importance >= 0.9
- Extract facts even from casual mentions — "yeah I drive a Ferrari" is just as important as "I drive a Ferrari"

Conversation turn:
{turn_text}

Return a JSON object with a single key "facts" containing an array. Each item must have:
- "entity_key": snake_case identifier following the rules above. Use null for episodic/one-off memories.
- "content": the fact as a clear, complete sentence (e.g. "The user drives a red Ferrari." or "The user has Type 2 diabetes.")
- "memory_type": "semantic" for durable facts, "episodic" for transient context
- "importance_score": float 0.0-1.0
- "confidence_score": float 0.0-1.0

If no facts can be extracted, return {{"facts": []}}.
Return ONLY valid JSON object with a "facts" key, no markdown, no explanation."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            response_format={"type": "json_object"},
            max_tokens=800,
            temperature=0.1,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        # Response is always {"facts": [...]}
        facts = data.get("facts", data.get("memories", []))
        if isinstance(data, list):  # fallback if model returns bare array
            facts = data
        logger.info(f"Extraction for user {user_id}: {len(facts)} facts found in turn")

        # Log usage for cost tracking (non-fatal)
        try:
            usage = response.usage
            if usage:
                from app.services.usage_service import log_usage
                await log_usage(
                    db=db,
                    user_id=user_id,
                    service="gpt4o_extraction",
                    operation="extract_facts",
                    tokens_in=usage.prompt_tokens,
                    tokens_out=usage.completion_tokens,
                    metadata={"model": "gpt-4o-mini", "facts_found": len(facts)},
                )
        except Exception as usage_err:
            logger.debug(f"Usage logging failed (non-fatal): {usage_err}")

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

            # Dedup: skip if a very similar fact already exists (cosine > 0.92)
            # This prevents near-duplicate facts from piling up
            if existing_memories:
                from pgvector.sqlalchemy import Vector
                import numpy as np
                emb_array = np.array(embedding)
                emb_norm = np.linalg.norm(emb_array)
                is_duplicate = False
                for existing in existing_memories:
                    if existing.embedding is not None:
                        ex_array = np.array(existing.embedding)
                        ex_norm = np.linalg.norm(ex_array)
                        if emb_norm > 0 and ex_norm > 0:
                            similarity = float(np.dot(emb_array, ex_array) / (emb_norm * ex_norm))
                            if similarity > 0.92:
                                # If same entity_key, allow update (UPSERT handles it)
                                if entity_key and existing.entity_key == entity_key:
                                    break
                                # Different key or null key but same content — skip
                                if not entity_key or existing.entity_key != entity_key:
                                    logger.debug(f"Dedup: skipping near-duplicate (sim={similarity:.3f}): {content[:60]}")
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

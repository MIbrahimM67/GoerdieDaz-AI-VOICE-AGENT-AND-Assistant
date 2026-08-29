"""Full pipeline test with print at every step."""
import asyncio
import json
import uuid
import sys
sys.path.insert(0, '.')

from datetime import datetime, timezone
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.config import get_settings
from app.models.memory import Memory
from app.services.embedding_service import embed_texts_batch

settings = get_settings()

async def test():
    user_id = "eeae307e-744e-4bcd-af34-beb4ea90c96f"
    turn_text = "User said: Hey mate, I drive a red Ferrari and I have diabetes\nGeordieDaz replied: Oh that sounds canny!"

    # Step 1: Extract facts
    print("[1] Extracting facts from GPT...")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Extract facts from: {turn_text}\n\nReturn JSON array with entity_key, content, memory_type, importance_score, confidence_score."}],
        response_format={"type": "json_object"},
        max_tokens=500,
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    data = json.loads(raw)
    facts = data if isinstance(data, list) else data.get("facts", data.get("memories", []))
    print(f"    Got {len(facts)} facts")

    # Step 2: Filter
    valid = [f for f in facts if float(f.get("importance_score", 0)) >= 0.5]
    print(f"[2] {len(valid)} facts pass threshold")
    
    if not valid:
        print("    No valid facts! Exiting.")
        return

    # Step 3: Embed
    print("[3] Embedding facts...")
    contents = [f["content"] for f in valid]
    embeddings = await embed_texts_batch(contents)
    print(f"    Got {len(embeddings)} embeddings, dim={len(embeddings[0])}")

    # Step 4: Insert directly
    print("[4] Inserting into DB...")
    async with AsyncSessionLocal() as db:
        for fact, emb in zip(valid, embeddings):
            entity_key = fact.get("entity_key")
            content = fact["content"]
            importance = float(fact.get("importance_score", 0.5))
            confidence = float(fact.get("confidence_score", 1.0))
            memory_type = fact.get("memory_type", "semantic")
            
            print(f"    Inserting: {entity_key} = {content}")
            
            try:
                stmt = pg_insert(Memory).values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    entity_key=entity_key,
                    content=content,
                    memory_type=memory_type,
                    importance_score=importance,
                    confidence_score=confidence,
                    source_persona_id="friendly_geordie",
                    embedding=emb,
                    updated_at=datetime.now(timezone.utc),
                )
                
                if entity_key:
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["user_id", "entity_key"],
                        index_where=text("entity_key IS NOT NULL"),
                        set_={
                            "content": stmt.excluded.content,
                            "importance_score": stmt.excluded.importance_score,
                            "embedding": stmt.excluded.embedding,
                            "updated_at": stmt.excluded.updated_at,
                        }
                    )
                
                await db.execute(stmt)
                print(f"    -> execute() OK")
            except Exception as e:
                print(f"    -> FAILED: {type(e).__name__}: {e}")
        
        print("[5] Committing...")
        try:
            await db.commit()
            print("    -> COMMITTED!")
        except Exception as e:
            print(f"    -> COMMIT FAILED: {type(e).__name__}: {e}")

    # Step 6: Verify
    print("[6] Verifying...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT entity_key, content FROM memories WHERE user_id = :uid ORDER BY updated_at DESC"), {"uid": user_id})
        rows = result.fetchall()
        print(f"    Found {len(rows)} memories:")
        for r in rows:
            print(f"      {r[0]}: {r[1]}")

if __name__ == "__main__":
    asyncio.run(test())

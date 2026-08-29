"""
GeordieDaz — Memory Debug Viewer
Run: python debug_memory.py
"""
import asyncio
import sys
import os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, '.')

from app.database import engine
from sqlalchemy import text

async def view_all_memories():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT entity_key, content, importance_score, confidence_score, 
                   memory_type, source_persona_id, updated_at
            FROM memories 
            ORDER BY updated_at DESC
        """))
        rows = result.fetchall()
        
        if not rows:
            print("\n  *** BRAIN IS EMPTY - No memories stored yet ***\n")
            return
        
        print(f"\n{'='*80}")
        print(f"  GEORDIEDAZ BRAIN DUMP - {len(rows)} memories stored")
        print(f"{'='*80}\n")
        
        for i, row in enumerate(rows, 1):
            entity_key = row[0] or "(no key)"
            content = row[1]
            importance = row[2]
            confidence = row[3]
            mem_type = row[4]
            persona = row[5] or "unknown"
            updated = row[6]
            
            imp_bar = "#" * int(importance * 10) + "." * (10 - int(importance * 10))
            
            print(f"  [{i}] {entity_key}")
            print(f"      Content:    {content}")
            print(f"      Importance: [{imp_bar}] {importance:.2f}")
            print(f"      Confidence: {confidence:.2f}")
            print(f"      Type:       {mem_type}")
            print(f"      Persona:    {persona}")
            print(f"      Updated:    {updated}")
            print()
        
        print(f"{'='*80}\n")

    # Also check working memory in Redis
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings
        settings = get_settings()
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        keys = await r.keys("working_memory:*")
        if keys:
            print(f"  WORKING MEMORY (Redis) - {len(keys)} keys")
            print(f"  {'-'*40}")
            for key in keys:
                turns = await r.lrange(key, 0, -1)
                print(f"  {key}: {len(turns)} turns")
                for t in turns[-4:]:
                    print(f"    > {t[:120]}...")
            print()
        else:
            print("  WORKING MEMORY (Redis): empty\n")
        await r.close()
    except Exception as e:
        print(f"  Redis check failed: {e}\n")

if __name__ == "__main__":
    asyncio.run(view_all_memories())

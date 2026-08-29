"""Direct test of write_memory_async to find the exact error."""
import asyncio
import sys
sys.path.insert(0, '.')

from app.database import AsyncSessionLocal
from app.services.memory_service import write_memory_async

async def test():
    turn_text = "User said: Hey mate, I drive a red Ferrari and I have diabetes\nGeordieDaz replied: Oh that sounds canny! A Ferrari, proper mint! And diabetes - we'll look after that together, pet."
    user_id = "eeae307e-744e-4bcd-af34-beb4ea90c96f"
    
    print(f"Testing write_memory_async directly...")
    print(f"Turn: {turn_text[:80]}...")
    
    async with AsyncSessionLocal() as db:
        try:
            await write_memory_async(
                user_id=user_id,
                turn_text=turn_text,
                persona_id="friendly_geordie",
                db=db,
            )
            print("\nwrite_memory_async completed!")
        except Exception as e:
            print(f"\nFAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    # Now check if anything was stored
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        result = await db.execute(text("SELECT entity_key, content, importance_score FROM memories ORDER BY updated_at DESC LIMIT 10"))
        rows = result.fetchall()
        if rows:
            print(f"\nStored {len(rows)} memories:")
            for r in rows:
                print(f"  {r[0]}: {r[1]} (importance: {r[2]})")
        else:
            print("\nNo memories stored.")

if __name__ == "__main__":
    asyncio.run(test())

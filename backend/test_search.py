"""Test search_memory retrieval directly."""
import asyncio, sys
sys.path.insert(0, '.')

from app.database import AsyncSessionLocal
from app.services.memory_service import retrieve_relevant_memories

async def test():
    user_id = "eeae307e-744e-4bcd-af34-beb4ea90c96f"
    queries = ["what car do I drive", "car", "Ferrari", "health", "diabetes"]
    
    async with AsyncSessionLocal() as db:
        for q in queries:
            results = await retrieve_relevant_memories(user_id, q, db, top_k=5)
            print(f"Query: '{q}' -> {len(results)} results")
            for r in results:
                print(f"  [{r['composite_score']:.3f}] {r['content']}")
            print()

if __name__ == "__main__":
    asyncio.run(test())

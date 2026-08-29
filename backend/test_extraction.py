"""Direct test with inline debugging to see exactly where it fails."""
import asyncio
import json
import sys
sys.path.insert(0, '.')

from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()

async def test():
    turn_text = "User said: Hey mate, I drive a red Ferrari and I have diabetes\nGeordieDaz replied: Oh that sounds canny! A Ferrari, proper mint! And diabetes - we'll look after that together, pet."

    extraction_prompt = f"""You are a fact extraction system for a personal AI assistant. Analyse this conversation turn and extract ALL meaningful facts.

Conversation turn:
{turn_text}

Return a JSON array. Each item must have:
- "entity_key": snake_case identifier (e.g. "user.car.ferrari", "user.health.diabetes")
- "content": the fact as a clear sentence
- "memory_type": "semantic" for durable facts, "episodic" for transient context
- "importance_score": float 0.0-1.0
- "confidence_score": float 0.0-1.0

Return ONLY valid JSON array, no markdown, no explanation."""

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    print("Calling GPT-4o-mini for extraction...")
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": extraction_prompt}],
        response_format={"type": "json_object"},
        max_tokens=800,
        temperature=0.1,
    )
    
    raw = response.choices[0].message.content
    print(f"\nRaw GPT response:\n{raw}")
    
    data = json.loads(raw)
    print(f"\nParsed type: {type(data)}")
    print(f"Parsed data: {json.dumps(data, indent=2)}")
    
    facts = data if isinstance(data, list) else data.get("facts", data.get("memories", []))
    print(f"\nExtracted {len(facts)} facts")
    
    threshold = settings.memory_importance_threshold
    print(f"Importance threshold: {threshold}")
    
    for i, fact in enumerate(facts):
        imp = float(fact.get("importance_score", 0))
        print(f"  [{i}] key={fact.get('entity_key')} imp={imp} pass={'YES' if imp >= threshold else 'NO'}: {fact.get('content')}")

if __name__ == "__main__":
    asyncio.run(test())

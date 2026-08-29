"""Quick test: call run_post_turn directly to see if it errors."""
import asyncio
import sys
sys.path.insert(0, '.')

from app.database import AsyncSessionLocal
from app.agent.graph import run_post_turn

async def test():
    async with AsyncSessionLocal() as db:
        state = {
            "user_id": "eeae307e-744e-4bcd-af34-beb4ea90c96f",
            "session_id": "test-session",
            "persona_id": "friendly_geordie",
            "persona_config": {},
            "user_input": "Hey mate, I drive a red Ferrari and I have diabetes",
            "response_text": "Oh that sounds canny! A red Ferrari, proper mint that! And I hear you about the diabetes - we'll keep an eye on that together, pet.",
            "assembled_system_prompt": "You are GeordieDaz.",
        }
        try:
            result = await run_post_turn(state, db)
            print(f"\nSUCCESS! Post-turn result: {result}")
        except Exception as e:
            print(f"\nFAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())

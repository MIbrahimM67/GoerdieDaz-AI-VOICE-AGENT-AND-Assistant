"""Test: voice via URL param + nested audio format."""
import asyncio, json, sys
sys.path.insert(0, ".")
from app.config import get_settings
settings = get_settings()
HEADERS = {"Authorization": f"Bearer {settings.openai_api_key}"}

TESTS = [
    {
        "name": "voice via URL param",
        "url": "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini&voice=alloy",
        "session": {"type": "realtime", "instructions": "Say hello.", "tools": [], "tool_choice": "auto"},
    },
    {
        "name": "nested audio object",
        "url": "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini",
        "session": {
            "type": "realtime",
            "instructions": "Say hello.",
            "audio": {"input": {"transcription": {"model": "whisper-1"}}, "output": {"voice": "alloy"}},
            "tools": [], "tool_choice": "auto",
        },
    },
    {
        "name": "bare minimum + check default session",
        "url": "wss://api.openai.com/v1/realtime?model=gpt-realtime-mini",
        "session": {"type": "realtime", "instructions": "Say hello.", "tools": [], "tool_choice": "auto"},
    },
]

async def test_one(cfg):
    import websockets
    try:
        async with websockets.connect(cfg["url"], additional_headers=HEADERS, ping_interval=20) as ws:
            created = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            if created.get("type") == "error":
                print(f"  CONNECT ERROR: {created.get('error',{}).get('message','?')}")
                return
            # Print the default session from session.created
            sess = created.get("session", {})
            print(f"  Default voice={sess.get('voice','?')} transcription={sess.get('input_audio_transcription','?')} vad={sess.get('turn_detection',{}).get('type','?')}")
            
            await ws.send(json.dumps({"type": "session.update", "session": cfg["session"]}))
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            if msg.get("type") == "error":
                print(f"  SESSION ERROR: {msg.get('error',{}).get('message','?')[:80]}")
            else:
                print(f"  SUCCESS: {msg['type']}")
                sess2 = msg.get("session", {})
                print(f"  Updated voice={sess2.get('voice','?')} transcription={sess2.get('input_audio_transcription','?')}")
    except Exception as e:
        print(f"  EXCEPTION: {str(e)[:80]}")

async def main():
    for t in TESTS:
        print(f"\n--- {t['name']} ---")
        await test_one(t)

asyncio.run(main())

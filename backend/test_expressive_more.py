"""
Generate 3 more samples with the B_very_expressive settings the user liked.
"""
import asyncio, json, base64, wave, time, os

try:
    import websockets
except ImportError:
    os.system("pip install websockets")
    import websockets

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
VOICE_ID = "zik8E6YgP11SlhQImASg"
MODEL_ID = "eleven_multilingual_v2"

# B_very_expressive — the settings the user liked
VOICE_SETTINGS = {
    "stability": 0.40,
    "similarity_boost": 0.80,
    "style": 0.35,
    "use_speaker_boost": False,
    "speed": 0.88,
}
CHUNK_SCHEDULE = [120, 160, 250]

SENTENCES = [
    "Wey aye, man... that's proper canny news, that is. You've done yourself proud there, bonny lad. Tell you what, the Toon would be buzzing for you tonight!",
    "Ah, divvent worry about that, pet. We all have days like that, don't we? Just take it easy, have yourself a nice cuppa, and tomorrow's a brand new day, mind.",
    "Howay, let me tell you something... life's too short to be stressing about the little things, like. You're doing champion, and don't let anyone tell you otherwise, right?",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison", "accent_tests")
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def generate(text, filename):
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id={MODEL_ID}&output_format=pcm_24000"

    audio_chunks = []
    t_start = time.time()
    t_first = None

    try:
        async with websockets.connect(
            url,
            additional_headers={"xi-api-key": API_KEY},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            bos = {
                "text": " ",
                "voice_settings": VOICE_SETTINGS,
                "generation_config": {"chunk_length_schedule": CHUNK_SCHEDULE},
                "xi_api_key": API_KEY,
            }
            await ws.send(json.dumps(bos))
            await ws.send(json.dumps({"text": text}))
            await ws.send(json.dumps({"text": ""}))

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    data = json.loads(msg)
                    if data.get("audio"):
                        if t_first is None:
                            t_first = time.time()
                        audio_chunks.append(base64.b64decode(data["audio"]))
                    if data.get("isFinal"):
                        break
                except asyncio.TimeoutError:
                    break
                except websockets.exceptions.ConnectionClosed:
                    break
    except Exception as e:
        print(f"  FAILED: {e}")
        return

    pcm = b"".join(audio_chunks)
    fpath = os.path.join(OUTPUT_DIR, filename)
    with wave.open(fpath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)

    ttfb = (t_first - t_start) * 1000 if t_first else 0
    dur = (len(pcm) / 2) / 24000
    print(f"  OK: {filename} | TTFB={ttfb:.0f}ms | Duration={dur:.1f}s")


async def main():
    print("B_very_expressive — 3 More Samples")
    print("stability=0.40 | similarity=0.80 | style=0.35 | speed=0.88 | boost=OFF")
    print()

    for i, text in enumerate(SENTENCES):
        print(f'Sample {i+1}: "{text[:60]}..."')
        await generate(text, f"expressive_sample_{i+1}.wav")
        await asyncio.sleep(1)
        print()

    print(f"Files: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())

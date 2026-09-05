"""
Retry failed accent tests with proper timeout handling.
"""
import asyncio, json, base64, wave, time, os

try:
    import websockets
except ImportError:
    os.system("pip install websockets")
    import websockets

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
MODEL_ID = "eleven_multilingual_v2"

TEXT = "Now look here, pet... how's your day been treating you, eh? Tell you what, I'm all ears, mind. There's nowt better than a proper good natter, is there?"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison", "accent_tests")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TESTS = [
    # (voice_id, voice_label, settings_dict, filename)
    ("zik8E6YgP11SlhQImASg", "GeordieDaz", {
        "stability": 0.65, "similarity_boost": 0.82, "style": 0.25,
        "use_speaker_boost": False, "speed": 0.90,
    }, "geordiedaz_A_current.wav"),
    ("zik8E6YgP11SlhQImASg", "GeordieDaz", {
        "stability": 0.45, "similarity_boost": 0.85, "style": 0.30,
        "use_speaker_boost": False, "speed": 0.90,
    }, "geordiedaz_D_sweetspot.wav"),
    ("JBFqnCBsd6RMkjVDRZzb", "George Storyteller", {
        "stability": 0.40, "similarity_boost": 0.80, "style": 0.35,
        "use_speaker_boost": False, "speed": 0.88,
    }, "george_storyteller_expressive.wav"),
    ("JBFqnCBsd6RMkjVDRZzb", "George Storyteller", {
        "stability": 0.45, "similarity_boost": 0.85, "style": 0.30,
        "use_speaker_boost": False, "speed": 0.90,
    }, "george_storyteller_sweetspot.wav"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel Broadcaster", {
        "stability": 0.40, "similarity_boost": 0.80, "style": 0.35,
        "use_speaker_boost": False, "speed": 0.88,
    }, "daniel_broadcaster_expressive.wav"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel Broadcaster", {
        "stability": 0.45, "similarity_boost": 0.85, "style": 0.30,
        "use_speaker_boost": False, "speed": 0.90,
    }, "daniel_broadcaster_sweetspot.wav"),
]


async def generate(voice_id, voice_label, settings, filename):
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={MODEL_ID}&output_format=pcm_24000"

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
                "voice_settings": settings,
                "generation_config": {"chunk_length_schedule": [120, 160, 250]},
                "xi_api_key": API_KEY,
            }
            await ws.send(json.dumps(bos))
            await ws.send(json.dumps({"text": TEXT}))
            await ws.send(json.dumps({"text": ""}))

            # Read with timeout
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
        print(f"  FAILED [{voice_label}]: {e}")
        return False

    if not audio_chunks:
        print(f"  FAILED [{voice_label}]: No audio received")
        return False

    pcm = b"".join(audio_chunks)
    fpath = os.path.join(OUTPUT_DIR, filename)
    with wave.open(fpath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)

    ttfb = (t_first - t_start) * 1000 if t_first else 0
    dur = (len(pcm) / 2) / 24000
    print(f"  OK: {filename} | {voice_label} | TTFB={ttfb:.0f}ms | Duration={dur:.1f}s")
    return True


async def main():
    print("Accent Authenticity Test — Retry")
    print()

    for voice_id, voice_label, settings, filename in TESTS:
        s = settings
        print(f"  Generating: {filename}")
        print(f"    Voice={voice_label} | stab={s['stability']} sim={s['similarity_boost']} style={s['style']} speed={s['speed']}")
        ok = await generate(voice_id, voice_label, settings, filename)
        if not ok:
            # Retry once
            print(f"    Retrying...")
            await asyncio.sleep(2)
            await generate(voice_id, voice_label, settings, filename)
        print()
        await asyncio.sleep(1)  # Brief pause between API calls

    print(f"Files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())

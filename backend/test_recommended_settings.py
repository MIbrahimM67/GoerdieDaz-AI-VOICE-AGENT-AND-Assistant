"""
Quick test — generate 2 samples with the community-recommended settings.
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

# Community-recommended "Natural Radio Host" settings
VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.82,
    "style": 0.25,
    "use_speaker_boost": False,
    "speed": 0.90,
}
CHUNK_SCHEDULE = [120, 160, 250]

SENTENCES = [
    "Now look here, pet... how's your day been treating you, eh? Tell you what, I'm all ears, mind. There's nowt better than a proper good natter, is there?",
    "Howay man, that's properly canny news, that is! You've done yourself proper proud there, bonny lad. The Toon would be buzzing for you, like.",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison")
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def generate(text, output_name):
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id={MODEL_ID}&output_format=pcm_24000"

    audio_chunks = []
    t_start = time.time()
    t_first = None

    async with websockets.connect(url, additional_headers={"xi-api-key": API_KEY}) as ws:
        bos = {
            "text": " ",
            "voice_settings": VOICE_SETTINGS,
            "generation_config": {"chunk_length_schedule": CHUNK_SCHEDULE},
            "xi_api_key": API_KEY,
        }
        await ws.send(json.dumps(bos))
        await ws.send(json.dumps({"text": text}))
        await ws.send(json.dumps({"text": ""}))

        async for msg in ws:
            data = json.loads(msg)
            if data.get("audio"):
                if t_first is None:
                    t_first = time.time()
                audio_chunks.append(base64.b64decode(data["audio"]))
            if data.get("isFinal"):
                break

    t_end = time.time()
    pcm = b"".join(audio_chunks)
    fpath = os.path.join(OUTPUT_DIR, output_name)
    with wave.open(fpath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)

    ttfb = (t_first - t_start) * 1000 if t_first else 0
    total = (t_end - t_start) * 1000
    dur = (len(pcm) / 2) / 24000
    print(f"  {output_name}: TTFB={ttfb:.0f}ms | Total={total:.0f}ms | Duration={dur:.2f}s")


async def main():
    print("Community-Recommended Settings Test")
    print(f"  Model: {MODEL_ID}")
    print(f"  Settings: stability={VOICE_SETTINGS['stability']}, similarity={VOICE_SETTINGS['similarity_boost']}, style={VOICE_SETTINGS['style']}, speed={VOICE_SETTINGS['speed']}, boost=OFF")
    print(f"  Chunk schedule: {CHUNK_SCHEDULE}")
    print()

    for i, text in enumerate(SENTENCES):
        print(f'Sentence {i+1}: "{text[:60]}..."')
        await generate(text, f"recommended_settings_test_{i+1}.wav")
        print()


if __name__ == "__main__":
    asyncio.run(main())

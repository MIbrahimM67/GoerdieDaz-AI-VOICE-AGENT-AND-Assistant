"""
ElevenLabs Model A/B/C Comparison Test
Generates the same sentence across 3 models so the client can hear the difference.
Outputs WAV files for side-by-side comparison.
"""
import asyncio
import json
import base64
import wave
import struct
import time
import os

try:
    import websockets
except ImportError:
    os.system("pip install websockets")
    import websockets

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
VOICE_ID = "zik8E6YgP11SlhQImASg"  # NewGeodieDaz (current Instant Voice Clone)

# Also test with the dedicated Geordie voice
VOICE_ID_GEORDIE = "QmpNl8yfFeqrwz75IL4C"  # geordie (en-geordie native model)

MODELS = [
    ("eleven_flash_v2_5", "Flash v2.5 (Current — Speed-optimized)"),
    ("eleven_multilingual_v2", "Multilingual v2 (Recommended — Accent-faithful)"),
    # v3 conversational uses a different endpoint, test via REST
]

TEST_SENTENCES = [
    "Now look here, pet... how's your day been treating you, eh? Tell you what, I'm all ears, mind.",
    "Howay man, that's proper canny, that is. You've done yourself proud there, bonny lad.",
    "Wey aye, we'll get that sorted for you, no bother at all. The Toon's looking canny good tonight.",
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def pcm16_to_wav(pcm_data: bytes, sample_rate: int = 24000, output_path: str = "output.wav"):
    """Convert raw PCM16 bytes to a WAV file."""
    num_samples = len(pcm_data) // 2
    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    duration_sec = num_samples / sample_rate
    return duration_sec


async def generate_with_model(model_id: str, voice_id: str, text: str, voice_settings: dict = None):
    """Stream text to ElevenLabs WS and collect all audio chunks."""
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={model_id}&output_format=pcm_24000"

    if voice_settings is None:
        voice_settings = {
            "stability": 0.88,
            "similarity_boost": 0.85,
            "style": 0.0,
            "use_speaker_boost": False,
            "speed": 0.90,
        }

    audio_chunks = []
    t_start = time.time()
    t_first_chunk = None

    try:
        async with websockets.connect(url, additional_headers={"xi-api-key": API_KEY}) as ws:
            # BOS
            bos = {
                "text": " ",
                "voice_settings": voice_settings,
                "generation_config": {"chunk_length_schedule": [50, 90, 140]},
                "xi_api_key": API_KEY,
            }
            await ws.send(json.dumps(bos))

            # Send full text + EOS
            await ws.send(json.dumps({"text": text}))
            await ws.send(json.dumps({"text": ""}))

            # Receive audio
            async for msg in ws:
                data = json.loads(msg)
                if data.get("audio"):
                    if t_first_chunk is None:
                        t_first_chunk = time.time()
                    audio_chunks.append(base64.b64decode(data["audio"]))
                if data.get("isFinal"):
                    break

    except Exception as e:
        print(f"  ERROR: {e}")
        return None, 0, 0

    t_end = time.time()
    pcm_data = b"".join(audio_chunks)
    ttfb = (t_first_chunk - t_start) * 1000 if t_first_chunk else 0
    total_time = (t_end - t_start) * 1000

    return pcm_data, ttfb, total_time


async def test_v3_rest(voice_id: str, text: str):
    """Test eleven_v3 via REST API (not WS-compatible for real-time)."""
    import urllib.request
    import urllib.error

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_24000"
    headers = {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
    }
    body = json.dumps({
        "text": text,
        "model_id": "eleven_v3",
        "voice_settings": {
            "stability": 0.88,
            "similarity_boost": 0.85,
            "style": 0.0,
            "use_speaker_boost": False,
            "speed": 0.90,
        },
    }).encode("utf-8")

    t_start = time.time()
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            pcm_data = resp.read()
        t_end = time.time()
        total_time = (t_end - t_start) * 1000
        return pcm_data, total_time, total_time
    except Exception as e:
        print(f"  v3 REST ERROR: {e}")
        return None, 0, 0


async def main():
    print("=" * 70)
    print("ElevenLabs Model A/B/C Comparison Test")
    print("=" * 70)
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    test_text = TEST_SENTENCES[0]
    print(f'Test sentence: "{test_text}"')
    print()

    results = []

    # Test each WS-compatible model with the primary voice
    for model_id, model_name in MODELS:
        print(f"─── Testing: {model_name} (voice: NewGeodieDaz) ───")
        pcm, ttfb, total = await generate_with_model(model_id, VOICE_ID, test_text)
        if pcm:
            fname = f"geordiedaz_{model_id}.wav"
            fpath = os.path.join(OUTPUT_DIR, fname)
            duration = pcm16_to_wav(pcm, output_path=fpath)
            print(f"  TTFB: {ttfb:.0f}ms | Total: {total:.0f}ms | Duration: {duration:.2f}s | File: {fname}")
            results.append((model_name, "NewGeodieDaz", ttfb, total, duration, fname))
        else:
            print("  FAILED")
        print()

    # Test each WS-compatible model with the Geordie Classic voice
    for model_id, model_name in MODELS:
        print(f"─── Testing: {model_name} (voice: Geordie Classic) ───")
        pcm, ttfb, total = await generate_with_model(model_id, VOICE_ID_GEORDIE, test_text)
        if pcm:
            fname = f"geordie_classic_{model_id}.wav"
            fpath = os.path.join(OUTPUT_DIR, fname)
            duration = pcm16_to_wav(pcm, output_path=fpath)
            print(f"  TTFB: {ttfb:.0f}ms | Total: {total:.0f}ms | Duration: {duration:.2f}s | File: {fname}")
            results.append((model_name, "Geordie Classic", ttfb, total, duration, fname))
        else:
            print("  FAILED")
        print()

    # Test v3 (REST only — not real-time) with primary voice
    print(f"─── Testing: Eleven v3 Flagship (REST, voice: NewGeodieDaz) ───")
    pcm, ttfb, total = await test_v3_rest(VOICE_ID, test_text)
    if pcm:
        fname = "geordiedaz_eleven_v3.wav"
        fpath = os.path.join(OUTPUT_DIR, fname)
        duration = pcm16_to_wav(pcm, output_path=fpath)
        print(f"  Total: {total:.0f}ms | Duration: {duration:.2f}s | File: {fname}")
        results.append(("Eleven v3 (Flagship REST)", "NewGeodieDaz", 0, total, duration, fname))
    else:
        print("  FAILED (may require Scale plan)")
    print()

    # Generate all 3 test sentences with the recommended model
    print("─── Generating all 3 test sentences with Multilingual v2 ───")
    for i, sentence in enumerate(TEST_SENTENCES):
        pcm, ttfb, total = await generate_with_model("eleven_multilingual_v2", VOICE_ID, sentence)
        if pcm:
            fname = f"multilingual_v2_sentence_{i+1}.wav"
            fpath = os.path.join(OUTPUT_DIR, fname)
            duration = pcm16_to_wav(pcm, output_path=fpath)
            print(f"  Sentence {i+1}: TTFB={ttfb:.0f}ms | Total={total:.0f}ms | Duration={duration:.2f}s | {fname}")
    print()

    # Summary
    print("=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Model':<45} {'Voice':<18} {'TTFB':<10} {'Total':<10} {'Duration':<10}")
    print("-" * 93)
    for name, voice, ttfb, total, dur, fname in results:
        print(f"{name:<45} {voice:<18} {ttfb:>6.0f}ms  {total:>6.0f}ms  {dur:>6.2f}s")
    print()
    print(f"Audio files saved to: {OUTPUT_DIR}")
    print("Play them back-to-back to compare accent fidelity, warmth, and consistency.")


if __name__ == "__main__":
    asyncio.run(main())

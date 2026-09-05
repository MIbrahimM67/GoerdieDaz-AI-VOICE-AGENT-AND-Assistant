"""
Pitch shift test — generate the same sentence then pitch it down
to find the right "deeper, mouth-closed, bold" feel.
"""
import asyncio, json, base64, wave, time, os, struct, math

try:
    import websockets
except ImportError:
    os.system("pip install websockets")
    import websockets

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
VOICE_ID = "zik8E6YgP11SlhQImASg"
MODEL_ID = "eleven_multilingual_v2"

VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.82,
    "style": 0.25,
    "use_speaker_boost": False,
    "speed": 0.90,
}
CHUNK_SCHEDULE = [120, 160, 250]

TEXT = "Now look here, pet... how's your day been treating you, eh? Tell you what, I'm all ears, mind. There's nowt better than a proper good natter, is there?"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def pitch_shift_pcm(pcm_data: bytes, semitones: float, sample_rate: int = 24000) -> bytes:
    """
    Pitch-shift PCM16 audio by resampling.
    Negative semitones = deeper voice.
    Uses linear interpolation for decent quality.
    """
    # Decode PCM16 to samples
    n_samples = len(pcm_data) // 2
    samples = struct.unpack(f'<{n_samples}h', pcm_data)
    
    # Calculate the resampling ratio
    # To lower pitch: we stretch the audio (more samples) then truncate to original duration
    ratio = 2.0 ** (semitones / 12.0)  # >1 = higher pitch, <1 = lower pitch
    
    # New length after pitch shift (keeping same duration)
    new_length = int(n_samples / ratio)
    
    # Resample using linear interpolation
    output = []
    for i in range(new_length):
        src_pos = i * ratio
        src_idx = int(src_pos)
        frac = src_pos - src_idx
        
        if src_idx + 1 < n_samples:
            val = samples[src_idx] * (1.0 - frac) + samples[src_idx + 1] * frac
        elif src_idx < n_samples:
            val = samples[src_idx]
        else:
            val = 0
        
        # Clamp to int16 range
        val = max(-32768, min(32767, int(val)))
        output.append(val)
    
    return struct.pack(f'<{len(output)}h', *output)


def save_wav(pcm_data: bytes, filepath: str, sample_rate: int = 24000):
    with wave.open(filepath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    dur = (len(pcm_data) / 2) / sample_rate
    return dur


async def generate_base():
    """Generate the base audio from ElevenLabs."""
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream-input?model_id={MODEL_ID}&output_format=pcm_24000"

    audio_chunks = []
    async with websockets.connect(url, additional_headers={"xi-api-key": API_KEY}) as ws:
        bos = {
            "text": " ",
            "voice_settings": VOICE_SETTINGS,
            "generation_config": {"chunk_length_schedule": CHUNK_SCHEDULE},
            "xi_api_key": API_KEY,
        }
        await ws.send(json.dumps(bos))
        await ws.send(json.dumps({"text": TEXT}))
        await ws.send(json.dumps({"text": ""}))

        async for msg in ws:
            data = json.loads(msg)
            if data.get("audio"):
                audio_chunks.append(base64.b64decode(data["audio"]))
            if data.get("isFinal"):
                break

    return b"".join(audio_chunks)


async def main():
    print("Generating base audio from ElevenLabs...")
    base_pcm = await generate_base()
    print(f"  Base audio: {len(base_pcm)} bytes")
    print()

    # Save original
    dur = save_wav(base_pcm, os.path.join(OUTPUT_DIR, "pitch_original.wav"))
    print(f"  pitch_original.wav (no shift): {dur:.2f}s")

    # Generate pitch-shifted versions
    shifts = [
        (-1.0, "pitch_down_1_semitone.wav",   "1 semitone down (subtle)"),
        (-1.5, "pitch_down_1.5_semitones.wav", "1.5 semitones down (noticeable)"),
        (-2.0, "pitch_down_2_semitones.wav",   "2 semitones down (deeper)"),
        (-2.5, "pitch_down_2.5_semitones.wav", "2.5 semitones down (bold/chest)"),
        (-3.0, "pitch_down_3_semitones.wav",   "3 semitones down (very deep)"),
    ]

    for semitones, filename, desc in shifts:
        shifted = pitch_shift_pcm(base_pcm, semitones)
        dur = save_wav(shifted, os.path.join(OUTPUT_DIR, filename))
        print(f"  {filename}: {dur:.2f}s — {desc}")

    print()
    print("Done! Listen to each and pick the depth that matches Alan Robson.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Accent authenticity test — multiple approaches to get genuine Geordie prosody:
1. Lower stability (more tonal variation / sing-song)
2. Higher style (more expressive delivery)  
3. Try British voices (George, Daniel) that may have better UK prosody base
4. Combine: British voice base + Geordie vocabulary + low stability
"""
import asyncio, json, base64, wave, time, os

try:
    import websockets
except ImportError:
    os.system("pip install websockets")
    import websockets

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
MODEL_ID = "eleven_multilingual_v2"

# Voices to test
VOICES = {
    "geordiedaz": "zik8E6YgP11SlhQImASg",       # Current clone
    "george_storyteller": "JBFqnCBsd6RMkjVDRZzb", # British warm storyteller
    "daniel_broadcaster": "onwK4e9ZLuTAKqWW03F9", # British broadcaster
}

# Different settings combos to test
SETTINGS_COMBOS = {
    "A_current": {
        "desc": "Current settings (baseline)",
        "stability": 0.65, "similarity_boost": 0.82, "style": 0.25,
        "use_speaker_boost": False, "speed": 0.90,
    },
    "B_very_expressive": {
        "desc": "Very low stability = maximum tonal rise/fall",
        "stability": 0.40, "similarity_boost": 0.80, "style": 0.35,
        "use_speaker_boost": False, "speed": 0.88,
    },
    "C_theatrical": {
        "desc": "High style = theatrical/performative delivery",
        "stability": 0.50, "similarity_boost": 0.78, "style": 0.45,
        "use_speaker_boost": False, "speed": 0.88,
    },
    "D_sweet_spot": {
        "desc": "Community sweet spot for accent prosody",
        "stability": 0.45, "similarity_boost": 0.85, "style": 0.30,
        "use_speaker_boost": False, "speed": 0.90,
    },
}

TEXT = "Now look here, pet... how's your day been treating you, eh? Tell you what, I'm all ears, mind. There's nowt better than a proper good natter, is there? Howay, let's hear what's on your mind, bonny lad."

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "model_comparison", "accent_tests")
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def generate(voice_id, settings, output_name):
    url = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id={MODEL_ID}&output_format=pcm_24000"

    vs = {
        "stability": settings["stability"],
        "similarity_boost": settings["similarity_boost"],
        "style": settings["style"],
        "use_speaker_boost": settings["use_speaker_boost"],
        "speed": settings["speed"],
    }

    audio_chunks = []
    t_start = time.time()
    t_first = None

    try:
        async with websockets.connect(url, additional_headers={"xi-api-key": API_KEY}) as ws:
            bos = {
                "text": " ",
                "voice_settings": vs,
                "generation_config": {"chunk_length_schedule": [120, 160, 250]},
                "xi_api_key": API_KEY,
            }
            await ws.send(json.dumps(bos))
            await ws.send(json.dumps({"text": TEXT}))
            await ws.send(json.dumps({"text": ""}))

            async for msg in ws:
                data = json.loads(msg)
                if data.get("audio"):
                    if t_first is None:
                        t_first = time.time()
                    audio_chunks.append(base64.b64decode(data["audio"]))
                if data.get("isFinal"):
                    break
    except Exception as e:
        print(f"  FAILED: {e}")
        return

    t_end = time.time()
    pcm = b"".join(audio_chunks)
    fpath = os.path.join(OUTPUT_DIR, output_name)
    with wave.open(fpath, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)

    ttfb = (t_first - t_start) * 1000 if t_first else 0
    dur = (len(pcm) / 2) / 24000
    print(f"  OK: {output_name} | TTFB={ttfb:.0f}ms | Duration={dur:.1f}s")


async def main():
    print("=" * 70)
    print("ACCENT AUTHENTICITY TEST")
    print("=" * 70)
    print()

    # Test 1: GeordieDaz clone with different settings
    print("--- GeordieDaz Clone — Settings Variations ---")
    for combo_name, settings in SETTINGS_COMBOS.items():
        print(f"  [{combo_name}] {settings['desc']}")
        print(f"    stability={settings['stability']}, similarity={settings['similarity_boost']}, style={settings['style']}, speed={settings['speed']}")
        await generate(VOICES["geordiedaz"], settings, f"geordiedaz_{combo_name}.wav")
        print()

    # Test 2: British voices with the most expressive settings
    print("--- British Pre-Built Voices (Settings B: Very Expressive) ---")
    expressive = SETTINGS_COMBOS["B_very_expressive"]
    for voice_name in ["george_storyteller", "daniel_broadcaster"]:
        vid = VOICES[voice_name]
        print(f"  [{voice_name}]")
        await generate(vid, expressive, f"{voice_name}_expressive.wav")
        print()

    # Test 3: British voices with sweet spot settings
    print("--- British Pre-Built Voices (Settings D: Sweet Spot) ---")
    sweet = SETTINGS_COMBOS["D_sweet_spot"]
    for voice_name in ["george_storyteller", "daniel_broadcaster"]:
        vid = VOICES[voice_name]
        print(f"  [{voice_name}]")
        await generate(vid, sweet, f"{voice_name}_sweetspot.wav")
        print()

    print("=" * 70)
    print(f"All files saved to: {OUTPUT_DIR}")
    print("Listen and compare the tonal rise/fall patterns!")


if __name__ == "__main__":
    asyncio.run(main())

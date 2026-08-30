import os
import requests

API_KEY = "sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a"
VOICE_ID = "niBvU6AgoHXAukAUYWI3"

# eleven_v3 supports audio tags like [laughs], [whispers], [sighs] etc.
# eleven_flash_v2_5 does NOT support audio tags — it reads them as text!
MODEL_ID = "eleven_v3"

url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

headers = {
    "Accept": "audio/mpeg",
    "Content-Type": "application/json",
    "xi-api-key": API_KEY
}

output_dir = r"h:\AI AGENT\geordiedaz\generated_voice"
os.makedirs(output_dir, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
#  FRIENDLY GEORDIE — Warm, caring, late-night radio companion
# ═══════════════════════════════════════════════════════════════

friendly_tests = [
    {
        "name": "friendly_01_welcome.mp3",
        "text": (
            "Alreet pet, how's it gannin? [chuckles softly] "
            "Howay, divvent fash yersel about owt tonight, bonny lad... "
            "Just sit back, relax, and let wor Geordie Daz sort everything out for ya. "
            "It's proper canny out there, like."
        ),
        "stability": 0.55,
        "similarity": 0.80,
    },
    {
        "name": "friendly_02_caring.mp3",
        "text": (
            "[warmly] Wey aye man, I remember you mentioning that the other day! "
            "That's proper mint news, that is... am dead chuffed for ya, bonny lad. "
            "[sighs contentedly] Sometimes the good things just take a bit of time, y'kna? "
            "Shy bairns get nowt, and you went and grabbed it! Class."
        ),
        "stability": 0.55,
        "similarity": 0.80,
    },
]

# ═══════════════════════════════════════════════════════════════
#  DRIVING BANTER — Savage, sarcastic, unfiltered Geordie roasting
# ═══════════════════════════════════════════════════════════════

banter_tests = [
    {
        "name": "banter_01_roasting.mp3",
        "text": (
            "HOWAY MAN! [laughs] What the bloody hell was THAT?! "
            "Ya nearly took that wing mirror off, ya daft ha'peth! "
            "Honestly bonny lad, wor nana could parallel park better than you, "
            "and she's been deed for twenty bloody year!"
        ),
        "stability": 0.30,
        "similarity": 0.80,
    },
    {
        "name": "banter_02_savage.mp3",
        "text": (
            "[sarcastically] Oh aye, BRILLIANT driving there wor kid... "
            "hadaway and shite! [laughs] "
            "That roundabout had ONE job, and you still buggered it up! "
            "For fuck's sake man, divvent be shy — put ya foot doon! "
            "This isn't a bloody funeral procession!"
        ),
        "stability": 0.25,
        "similarity": 0.80,
    },
]

# ═══════════════════════════════════════════════════════════════
#  GENERATE ALL TEST AUDIOS
# ═══════════════════════════════════════════════════════════════

all_tests = friendly_tests + banter_tests

for test in all_tests:
    print(f"\n{'-'*60}")
    print(f"Generating: {test['name']}")
    print(f"Text: {test['text'][:80]}...")
    
    data = {
        "text": test["text"],
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": test["stability"],
            "similarity_boost": test["similarity"],
        }
    }
    
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 200:
        output_path = os.path.join(output_dir, test["name"])
        with open(output_path, "wb") as f:
            f.write(response.content)
        size_kb = os.path.getsize(output_path) / 1024
        print(f"OK - Saved to {output_path} ({size_kb:.1f} KB)")
    else:
        print(f"FAIL - Error {response.status_code}: {response.text}")

print(f"\n{'='*60}")
print(f"Done! All files saved to: {output_dir}")

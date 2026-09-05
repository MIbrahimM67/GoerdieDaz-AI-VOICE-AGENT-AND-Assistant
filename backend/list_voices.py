import requests, json

url = 'https://api.elevenlabs.io/v1/voices'
headers = {'xi-api-key': 'sk_39e7eb21ffc62606d2313322dd40fde288a90d5b683a423a'}
resp = requests.get(url, headers=headers)
voices = resp.json().get('voices', [])
for v in voices:
    labels = v.get('labels', {})
    vid = v['voice_id']
    name = v['name']
    accent = labels.get('accent', '?')
    age = labels.get('age', '?')
    gender = labels.get('gender', '?')
    desc = labels.get('description', labels.get('descriptive', '?'))
    print(f"{vid} | {name:25s} | accent={accent:15s} | age={age:12s} | gender={gender:8s} | desc={desc}")

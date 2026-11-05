# save as ping2.py
import os, json, urllib.request, urllib.error
from dotenv import load_dotenv
load_dotenv(override=True)

key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
model = os.getenv("GEMINI_MODEL", "")
print("model repr:", repr(model), "| key length:", len(key))

def try_model(m):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    data = json.dumps({"contents": [{"parts": [{"text": "Reply with PONG."}]}]}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
        print(f"[OK]  {m}:", r["candidates"][0]["content"]["parts"][0]["text"].strip())
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {m}:", e.read().decode()[:400])

for m in [model, "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash"]:
    if m:
        try_model(m)
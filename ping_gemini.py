import os, json, urllib.request
from dotenv import load_dotenv
load_dotenv(override=True)

key = os.getenv("GEMINI_API_KEY", "").strip().strip("'\"")
model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
data = json.dumps({"contents": [{"parts": [{"text": "Reply with PONG."}]}]}).encode()
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
print(json.loads(urllib.request.urlopen(req, timeout=20).read())["candidates"][0]["content"]["parts"][0]["text"])
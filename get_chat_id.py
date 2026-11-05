import os, json, urllib.request
from dotenv import load_dotenv
load_dotenv(override=True)
t = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip("'\"")
d = json.loads(urllib.request.urlopen(f"https://api.telegram.org/bot{t}/getUpdates", timeout=20).read())
for u in d.get("result", []):
    m = u.get("message") or {}
    print(m.get("chat", {}).get("id"), m.get("chat", {}).get("first_name"))
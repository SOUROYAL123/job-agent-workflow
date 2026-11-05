import os, urllib.request, urllib.parse, urllib.error
from dotenv import load_dotenv
load_dotenv(override=True)

t = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip("'\"")
c = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip("'\"")
print("chat id set:", bool(c), "| chat id:", c)

url = f"https://api.telegram.org/bot{t}/sendMessage"
data = urllib.parse.urlencode({"chat_id": c, "text": "CareerOS test OK"}).encode()
try:
    print(urllib.request.urlopen(url, data, timeout=20).read().decode())
except urllib.error.HTTPError as e:
    print(f"[{e.code}]", e.read().decode())
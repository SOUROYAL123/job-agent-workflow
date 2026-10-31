"""Test the free fallback provider. Run: python check_fallback.py
Reads FALLBACK_BASE_URL, FALLBACK_API_KEY, FALLBACK_MODELS from .env. Never prints the key."""
import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
url = os.getenv("FALLBACK_BASE_URL", "").strip().rstrip("/")
key = os.getenv("FALLBACK_API_KEY", "").strip()
models = [m.strip() for m in os.getenv("FALLBACK_MODELS", "").split(",") if m.strip()]

if not url:
    raise SystemExit("FALLBACK_BASE_URL is blank in .env")
headers = {"Authorization": f"Bearer {key}"} if key else {}

try:
    r = requests.get(f"{url}/models", headers=headers, timeout=30)
    ids = [m.get("id") for m in r.json().get("data", [])] if r.status_code == 200 else []
    print(f"/models -> HTTP {r.status_code}, {len(ids)} model(s) listed")
    for i in ids[:40]:
        print("  ", i)
except Exception as exc:
    print("Could not list models:", str(exc)[:150])

for m in models:
    try:
        r = requests.post(f"{url}/chat/completions", headers=headers, timeout=60,
                          json={"model": m, "messages": [{"role": "user", "content": "Reply with the word ok"}]})
        if r.status_code == 200:
            print(f"[READY] {m}: {r.json()['choices'][0]['message']['content'].strip()[:30]}")
        else:
            print(f"[FAILED] {m}: HTTP {r.status_code} {r.text[:120]}")
    except Exception as exc:
        print(f"[FAILED] {m}: {str(exc)[:120]}")

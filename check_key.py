"""Quick Gemini key check. Run: py check_key.py   (never prints the full key)"""
import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv(override=True)
key = os.getenv("GEMINI_API_KEY", "")
model = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

if not key:
    raise SystemExit("PROBLEM: GEMINI_API_KEY is missing or empty in .env.")

print(f"Key length: {len(key)}  (normally ~39 for 'AIza' or ~53 for 'AQ.')")
print(f"Starts with: {key[:4]!r}")

if key != key.strip() or key[:1] in "\"'" or key[-1:] in "\"'":
    print("PROBLEM: the key has spaces or quote marks around it. Remove them in .env.")
elif not (key.startswith("AIza") or key.startswith("AQ.")):
    print("WARNING: unexpected key prefix. Double-check GEMINI_API_KEY in .env.")
else:
    print("Key format: OK")

client = genai.Client(api_key=key)  # keep a reference; do not chain it inline

for attempt in range(1, 4):
    try:
        reply = client.models.generate_content(
            model=model,
            contents="Reply with the word ok",
        ).text
        print("Gemini replied:", (reply or "").strip())
        print("KEY WORKS.")
        break
    except Exception as exc:
        msg = str(exc)
        if any(tok in msg for tok in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")):
            if attempt < 3:
                wait = 10 * attempt
                print(f"Model busy (503/429). Waiting {wait}s before retry {attempt + 1}/3...")
                time.sleep(wait)
                continue
            print("KEY AUTHENTICATED, but the model is temporarily overloaded. Try again in a few minutes:\n", msg[:300])
        else:
            print("KEY REJECTED or request failed:\n", msg[:300])
        break
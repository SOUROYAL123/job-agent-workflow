import os
from dotenv import load_dotenv
from google import genai

load_dotenv(override=True)
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise SystemExit("Missing GEMINI_API_KEY in .env")

client = genai.Client(api_key=api_key)

print("Scanning active models for your API key...\n")

try:
    all_models = [m.name.replace("models/", "") for m in client.models.list()]
except Exception as exc:
    print("Failed to list models:", exc)
    all_models = []

for name in all_models:
    # Skip non-text models like embeddings, image gen, audio, etc.
    if any(skip in name.lower() for skip in ["embed", "image", "tts", "whisper", "realtime", "aqa", "bison"]):
        continue

    try:
        reply = client.models.generate_content(model=name, contents="ok").text
        print(f"[READY] {name}")
    except Exception as exc:
        err = str(exc)
        if "429" in err:
            print(f"[QUOTA FULL] {name}")
        elif "404" in err:
            continue
        else:
            print(f"[SKIPPED] {name} ({err[:50]})")

print("\nScan complete.")
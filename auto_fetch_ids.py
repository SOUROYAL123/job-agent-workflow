#!/usr/bin/env python3
"""
auto_fetch_ids.py - Semi-automated credential resolver for CareerOS.
Fetches Telegram chat ID via API and updates .env directly.
"""

import json
import os
import re
import urllib.request
import webbrowser


def set_env_key(key: str, value: str, filepath: str = ".env"):
    """Inserts or replaces a key-value pair in .env."""
    lines = []
    found = False
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"export {key}="):
            new_lines.append(f'{key}="{value}"\n')
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f'{key}="{value}"\n')

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def fetch_telegram_chat_id(bot_token: str) -> str:
    """Queries Telegram API getUpdates to fetch user chat ID automatically."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            if not results:
                print("\n[!] No messages detected yet.")
                print(f"    Open your bot in Telegram, tap START, then press Enter.")
                input("Press Enter after sending a message to your bot...")
                return fetch_telegram_chat_id(bot_token)

            # Extract chat ID from latest message
            chat_id = str(results[-1]["message"]["chat"]["id"])
            return chat_id
    except Exception as e:
        print(f"[!] Could not query Telegram API: {e}")
        return ""


def main():
    print("=== CareerOS Automated Credential Resolver ===\n")

    # 1. Gemini Key
    print("1. Opening Google AI Studio to grab your Gemini API Key...")
    webbrowser.open("https://aistudio.google.com/app/apikey")
    gemini_key = input("Paste your Gemini API Key here: ").strip()
    if gemini_key:
        set_env_key("GEMINI_API_KEY", gemini_key)
        print(" -> GEMINI_API_KEY saved.")

    # 2. Telegram Token & Auto-Fetch Chat ID
    print("\n2. Telegram Setup:")
    webbrowser.open("https://t.me/BotFather")
    bot_token = input("Paste the Bot Token from @BotFather (or Enter to skip): ").strip()
    if bot_token:
        # Strip accidental brackets or quotes
        bot_token = re.sub(r"^<|>$", "", bot_token).strip()
        set_env_key("TELEGRAM_BOT_TOKEN", bot_token)
        set_env_key("ENABLE_TELEGRAM_ALERTS", "true")
        print(" -> Querying Telegram servers for your Chat ID...")
        chat_id = fetch_telegram_chat_id(bot_token)
        if chat_id:
            set_env_key("TELEGRAM_CHAT_ID", chat_id)
            print(f" -> Found and saved TELEGRAM_CHAT_ID: {chat_id}")

    # 3. Gmail App Password
    print("\n3. Gmail Credentials:")
    email_addr = input("Enter your Gmail address (or Enter to skip): ").strip()
    if email_addr:
        set_env_key("EMAIL_ADDRESS", email_addr)
        set_env_key("RECIPIENT_EMAIL", email_addr)
        print("Opening Google App Passwords...")
        webbrowser.open("https://myaccount.google.com/apppasswords")
        app_pw = input("Paste the 16-character App Password: ").strip().replace(" ", "")
        set_env_key("EMAIL_PASSWORD", app_pw)
        set_env_key("SEND_EMAIL_DIGEST", "true")
        print(" -> EMAIL_PASSWORD saved.")

    print("\n[Done] All accessible keys resolved and saved into .env.")
    print("Running ATS discovery to populate company slugs...")
    os.system("py ats_finder.py")


if __name__ == "__main__":
    main()

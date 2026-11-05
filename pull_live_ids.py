#!/usr/bin/env python3
"""
pull_live_ids.py - Live Parameter & ID Inspector for CareerOS.
Queries external endpoints, APIs, IMAP, and local SQLite databases
to extract and verify actual IDs, posting numbers, chat IDs, and model IDs.
"""

import imaplib
import json
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List

# ----------------------------------------------------------------------
# 1. ROBUST .ENV LOADER
# ----------------------------------------------------------------------
def load_env(filepath: str = ".env") -> Dict[str, str]:
    env_vars = {}
    if not os.path.exists(filepath):
        return env_vars
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export ") :].strip()
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    env_vars[k] = v
                    if k not in os.environ:
                        os.environ[k] = v
    return env_vars


ENV = load_env()
REPORT: Dict[str, Any] = {"inspected_at": datetime.now().isoformat()}

# ----------------------------------------------------------------------
# 2. TELEGRAM API: BOT ID, UPDATE IDs, USER/CHAT IDs
# ----------------------------------------------------------------------
def inspect_telegram():
    print("\n" + "=" * 70)
    print("1. TELEGRAM LIVE IDS & MESSAGES")
    print("=" * 70)

    token = ENV.get("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    configured_chat_id = ENV.get("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")

    REPORT["telegram"] = {
        "configured_chat_id": configured_chat_id,
        "token_prefix": token.split(":")[0] if ":" in token else "INVALID",
    }

    if not token or ":" not in token:
        print("[-] TELEGRAM_BOT_TOKEN is missing or malformed.")
        return

    # A. Probe getMe
    get_me_url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(get_me_url, headers={"User-Agent": "CareerOS-Inspector/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                res = data["result"]
                bot_id = res.get("id")
                bot_name = res.get("first_name")
                bot_user = res.get("username")
                print(f"[✓] Bot Identity Verified:")
                print(f"    - Bot ID:       {bot_id}")
                print(f"    - Bot Username: @{bot_user}")
                print(f"    - Bot Name:     {bot_name}")
                REPORT["telegram"]["bot"] = {"id": bot_id, "username": bot_user, "name": bot_name}
    except urllib.error.HTTPError as e:
        print(f"[-] Telegram getMe HTTP {e.code}: {e.reason}")
        return
    except Exception as e:
        print(f"[-] Telegram connection error: {e}")
        return

    # B. Probe getUpdates to discover real Chat IDs and Message IDs
    updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        req = urllib.request.Request(updates_url, headers={"User-Agent": "CareerOS-Inspector/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("result", [])
            print(f"\n[✓] Live Updates & Discovered Chats: {len(results)} events found")

            discovered_chats = {}
            for update in results:
                u_id = update.get("update_id")
                msg = update.get("message") or update.get("my_chat_member", {}).get("chat")
                if isinstance(msg, dict):
                    chat = msg.get("chat", msg)
                    c_id = str(chat.get("id", ""))
                    c_type = chat.get("type", "unknown")
                    username = chat.get("username", "")
                    first_name = chat.get("first_name", "")
                    discovered_chats[c_id] = {
                        "chat_id": c_id,
                        "type": c_type,
                        "username": username,
                        "name": first_name,
                        "last_update_id": u_id,
                    }

            if discovered_chats:
                print(f"    {'Discovered Chat ID':<20} | {'Type':<10} | {'Username':<18} | {'Matches .env?':<12}")
                print("    " + "-" * 66)
                for cid, cinfo in discovered_chats.items():
                    matches = "YES (MATCH)" if cid == configured_chat_id else "NO"
                    print(f"    {cid:<20} | {cinfo['type']:<10} | @{cinfo['username']:<17} | {matches}")
                REPORT["telegram"]["discovered_chats"] = list(discovered_chats.values())
            else:
                print(f"    [!] No user chat IDs found in bot update queue.")
                print(f"        Action required: Open Telegram, search @{bot_user}, and send '/start'.")
    except Exception as e:
        print(f"[-] Error fetching updates: {e}")


# ----------------------------------------------------------------------
# 3. GEMINI API: LIVE MODEL IDENTIFIERS
# ----------------------------------------------------------------------
def inspect_gemini():
    print("\n" + "=" * 70)
    print("2. GOOGLE GEMINI MODEL IDENTIFIERS")
    print("=" * 70)

    api_key = ENV.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        print("[-] GEMINI_API_KEY is not defined in .env")
        return

    print(f"[*] Configured API Key prefix: {api_key[:6]}... (Length: {len(api_key)})")
    if not api_key.startswith("AIzaSy"):
        print(f"    [!] Warning: Key starts with '{api_key[:6]}'. Standard Google AI Studio keys start with 'AIzaSy'.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Inspector/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            print(f"[✓] Successfully retrieved {len(models)} accessible model endpoints:")
            print(f"    {'Model ID Name':<38} | {'Input Token Limit':<18} | {'Display Name'}")
            print("    " + "-" * 80)

            valid_models = []
            for m in models:
                m_name = m.get("name", "").replace("models/", "")
                limit = m.get("inputTokenLimit", "N/A")
                d_name = m.get("displayName", "")
                if any(k in m_name for k in ["flash", "pro", "embedding"]):
                    print(f"    {m_name:<38} | {str(limit):<18} | {d_name}")
                    valid_models.append({"name": m_name, "input_limit": limit, "display": d_name})

            REPORT["gemini"] = {"status": "ACTIVE", "model_count": len(models), "key_models": valid_models}
    except urllib.error.HTTPError as e:
        print(f"[-] Gemini API returned HTTP {e.code}: {e.reason}")
        REPORT["gemini"] = {"status": f"HTTP_ERROR_{e.code}", "reason": e.reason}
    except Exception as e:
        print(f"[-] Gemini connection failure: {e}")
        REPORT["gemini"] = {"status": "CONNECTION_FAILED", "error": str(e)}


# ----------------------------------------------------------------------
# 4. ATS APIs: GREENHOUSE, LEVER, ASHBY JOB POSTING IDs
# ----------------------------------------------------------------------
def inspect_ats():
    print("\n" + "=" * 70)
    print("3. LIVE ATS JOB BOARD IDs & REAL VACANCY POSTING IDs")
    print("=" * 70)

    ats_report = {"greenhouse": {}, "lever": {}, "ashby": {}}

    # A. Greenhouse
    gh_slugs = [s.strip() for s in ENV.get("ATS_GREENHOUSE", "").split(",") if s.strip()]
    print(f"\n--- Greenhouse Boards ({len(gh_slugs)} configured) ---")
    print(f"{'Company Slug':<18} | {'Status':<10} | {'Live Postings':<14} | {'Sample Real Job IDs'}")
    print("-" * 80)

    for slug in gh_slugs:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data.get("jobs", [])
                sample_ids = [str(j.get("id")) for j in jobs[:3]]
                id_preview = ", ".join(sample_ids) if sample_ids else "None"
                print(f"{slug:<18} | {'ONLINE':<10} | {len(jobs):<14} | {id_preview}")
                ats_report["greenhouse"][slug] = {
                    "count": len(jobs),
                    "sample_ids": sample_ids,
                    "first_title": jobs[0].get("title") if jobs else None,
                }
        except Exception:
            print(f"{slug:<18} | {'OFFLINE':<10} | {'0':<14} | -")
            ats_report["greenhouse"][slug] = {"count": 0, "status": "unreachable"}

    # B. Lever
    lever_slugs = [s.strip() for s in ENV.get("ATS_LEVER", "").split(",") if s.strip()]
    print(f"\n--- Lever Boards ({len(lever_slugs)} configured) ---")
    print(f"{'Company Slug':<18} | {'Status':<10} | {'Live Postings':<14} | {'Sample Real Job UUIDs'}")
    print("-" * 80)

    for slug in lever_slugs:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                jobs = json.loads(resp.read().decode("utf-8"))
                sample_ids = [str(j.get("id"))[:8] + "..." for j in jobs[:3]]
                id_preview = ", ".join(sample_ids) if sample_ids else "None"
                print(f"{slug:<18} | {'ONLINE':<10} | {len(jobs):<14} | {id_preview}")
                ats_report["lever"][slug] = {
                    "count": len(jobs),
                    "sample_ids": [j.get("id") for j in jobs[:3]],
                    "first_title": jobs[0].get("text") if jobs else None,
                }
        except Exception:
            print(f"{slug:<18} | {'OFFLINE':<10} | {'0':<14} | -")
            ats_report["lever"][slug] = {"count": 0, "status": "unreachable"}

    # C. Ashby
    ashby_slugs = [s.strip() for s in ENV.get("ATS_ASHBY", "").split(",") if s.strip()]
    print(f"\n--- Ashby Boards ({len(ashby_slugs)} configured) ---")
    print(f"{'Company Slug':<18} | {'Status':<10} | {'Live Postings':<14} | {'Sample Real Job UUIDs'}")
    print("-" * 80)

    for slug in ashby_slugs:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = data.get("jobs", [])
                sample_ids = [str(j.get("id"))[:8] + "..." for j in jobs[:3]]
                id_preview = ", ".join(sample_ids) if sample_ids else "None"
                print(f"{slug:<18} | {'ONLINE':<10} | {len(jobs):<14} | {id_preview}")
                ats_report["ashby"][slug] = {
                    "count": len(jobs),
                    "sample_ids": [j.get("id") for j in jobs[:3]],
                    "first_title": jobs[0].get("title") if jobs else None,
                }
        except Exception:
            print(f"{slug:<18} | {'OFFLINE':<10} | {'0':<14} | -")
            ats_report["ashby"][slug] = {"count": 0, "status": "unreachable"}

    REPORT["ats"] = ats_report


# ----------------------------------------------------------------------
# 5. GMAIL IMAP: REAL MESSAGE NUMBERS & MAILBOX IDs
# ----------------------------------------------------------------------
def inspect_gmail():
    print("\n" + "=" * 70)
    print("4. GMAIL LIVE INBOX STATUS & MESSAGE NUMBERS")
    print("=" * 70)

    email_addr = ENV.get("EMAIL_ADDRESS", "").strip()
    email_pass = ENV.get("EMAIL_PASSWORD", "").replace(" ", "").strip()
    server = ENV.get("IMAP_SERVER", "imap.gmail.com").strip()

    if not email_addr or not email_pass:
        print("[-] EMAIL_ADDRESS or EMAIL_PASSWORD missing.")
        return

    try:
        mail = imaplib.IMAP4_SSL(server, 993)
        mail.login(email_addr, email_pass)
        status, count_data = mail.select("INBOX", readonly=True)
        total_msgs = int(count_data[0].decode()) if status == "OK" else 0

        # Search for unseen messages
        status_unseen, unseen_data = mail.search(None, "UNSEEN")
        unseen_ids = unseen_data[0].decode().split() if status_unseen == "OK" and unseen_data[0] else []

        print(f"[✓] Connected to mailbox for: {email_addr}")
        print(f"    - Mailbox Selected:       INBOX")
        print(f"    - Total Message Count:    {total_msgs}")
        print(f"    - Unread Messages:        {len(unseen_ids)}")
        if unseen_ids:
            print(f"    - Latest Unread Msg IDs:  {', '.join(unseen_ids[-5:])}")

        REPORT["gmail"] = {
            "account": email_addr,
            "total_messages": total_msgs,
            "unread_count": len(unseen_ids),
            "sample_unread_ids": unseen_ids[-5:],
        }
        mail.logout()
    except Exception as e:
        print(f"[-] Gmail IMAP login failed: {e}")
        REPORT["gmail"] = {"account": email_addr, "error": str(e)}


# ----------------------------------------------------------------------
# 6. LOCAL SQLITE DATABASE: REAL JOB IDs & COUNTS
# ----------------------------------------------------------------------
def inspect_sqlite():
    print("\n" + "=" * 70)
    print("5. LOCAL SQLITE DATABASE REAL DATA (jobs.db)")
    print("=" * 70)

    db_path = ENV.get("DB_PATH", "jobs.db").strip()
    if not os.path.exists(db_path):
        print(f"[-] SQLite database file '{db_path}' does not exist on disk yet.")
        REPORT["database"] = {"path": db_path, "status": "NOT_FOUND"}
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check tables
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"[✓] SQLite Database Found: {db_path}")
        print(f"    - Verified Tables: {', '.join(tables)}")

        db_stats = {"tables": tables}

        if "jobs" in tables:
            total_jobs = cur.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            scored_jobs = cur.execute("SELECT COUNT(*) FROM jobs WHERE scored = 1").fetchone()[0]
            top_jobs = cur.execute(
                "SELECT id, title, company, match_score FROM jobs WHERE scored = 1 ORDER BY match_score DESC LIMIT 3"
            ).fetchall()

            print(f"    - Total Saved Jobs:       {total_jobs}")
            print(f"    - Scored Jobs Count:      {scored_jobs}")

            if top_jobs:
                print("\n    Highest Scoring Record IDs in Database:")
                print(f"    {'DB ID':<8} | {'Score':<8} | {'Company':<22} | {'Job Title'}")
                print("    " + "-" * 65)
                for tj in top_jobs:
                    print(f"    {tj['id']:<8} | {tj['match_score']:<8} | {tj['company']:<22} | {tj['title']}")

            db_stats["jobs_count"] = total_jobs
            db_stats["scored_count"] = scored_jobs

        if "applications" in tables:
            total_apps = cur.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
            print(f"    - Total Applications:     {total_apps}")
            db_stats["applications_count"] = total_apps

        REPORT["database"] = db_stats
        conn.close()
    except Exception as e:
        print(f"[-] SQLite inspection error: {e}")
        REPORT["database"] = {"path": db_path, "error": str(e)}


# ----------------------------------------------------------------------
# 7. MAIN EXECUTOR & JSON EXPORT
# ----------------------------------------------------------------------
def main():
    print("=" * 70)
    print("CAREEROS REAL ID & PARAMETER VALUE EXTRACTOR")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    inspect_telegram()
    inspect_gemini()
    inspect_ats()
    inspect_gmail()
    inspect_sqlite()

    out_file = "live_system_ids.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(REPORT, f, indent=2)

    print("\n" + "=" * 70)
    print(f"[SUCCESS] Complete parameter audit exported to: {out_file}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

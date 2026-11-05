#!/usr/bin/env python3
"""
reextract_env_sources.py - Production Parameter & Source Extractor for CareerOS
- Safely extracts all parameters from .env
- Masks sensitive credentials in terminal output
- Resiliently probes ATS and remote feeds for live job IDs and counts
- Exports verified configuration to sources_verified.json and .env.sanitized
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any


def mask_secret(val: str, reveal_chars: int = 4) -> str:
    """Masks credentials to prevent sensitive leakage."""
    if not val or val == "REPLACE_WITH_ROTATED_SECRET":
        return "[NOT SET]"
    if len(val) <= reveal_chars * 2:
        return "*" * len(val)
    return f"{val[:reveal_chars]}...{'*' * 8}...{val[-reveal_chars:]}"


def parse_raw_env(filepath: str = ".env") -> Dict[str, str]:
    """Reads .env line-by-line from disk, preserving exact values."""
    env = {}
    path = Path(filepath)
    if not path.exists():
        print(f"[!] Error: '{filepath}' not found in {os.getcwd()}")
        return env

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("export "):
                stripped = stripped[len("export "):].strip()
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                env[k] = v
    return env


def split_items(val_str: str, delimiter: str = ",") -> List[str]:
    """Splits string by delimiter into a cleaned list."""
    if not val_str:
        return []
    return [i.strip() for i in val_str.split(delimiter) if i.strip()]


def probe_greenhouse(slug: str) -> Dict[str, Any]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            return {
                "status": "ONLINE",
                "count": len(jobs),
                "sample_ids": [str(j.get("id")) for j in jobs[:3]]
            }
    except Exception as e:
        return {"status": "OFFLINE", "count": 0, "sample_ids": [], "error": str(e)}


def probe_lever(slug: str) -> Dict[str, Any]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            jobs = json.loads(resp.read().decode())
            if not isinstance(jobs, list):
                jobs = []
            return {
                "status": "ONLINE",
                "count": len(jobs),
                "sample_ids": [str(j.get("id"))[:8] for j in jobs[:3] if isinstance(j, dict)]
            }
    except Exception as e:
        return {"status": "OFFLINE", "count": 0, "sample_ids": [], "error": str(e)}


def probe_ashby(slug: str) -> Dict[str, Any]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CareerOS-Scout/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            jobs = data.get("jobs", []) if isinstance(data, dict) else []
            return {
                "status": "ONLINE",
                "count": len(jobs),
                "sample_ids": [str(j.get("id"))[:8] for j in jobs[:3] if isinstance(j, dict)]
            }
    except Exception as e:
        return {"status": "OFFLINE", "count": 0, "sample_ids": [], "error": str(e)}


def main():
    env = parse_raw_env(".env")
    if not env:
        return

    print("=" * 80)
    print("CAREEROS: EXTRACTED REAL PARAMETERS & SOURCE VERIFICATION")
    print(f"File Path: {os.path.abspath('.env')}")
    print("=" * 80)

    # 1. Candidate Identity
    print("\n[1] CANDIDATE PROFILE & TARGETS")
    print("-" * 80)
    print(f"• Candidate Name:     {env.get('CANDIDATE_NAME', '[NOT SET]')}")
    print(f"• Base Location:      {env.get('CANDIDATE_BASE_LOCATION', '[NOT SET]')}")
    print(f"• Profile Vault File: {env.get('CANDIDATE_PROFILE_PATH', 'candidate_profile.txt')}")
    print(f"• Word Resume Model:  {env.get('MASTER_RESUME_DOCX', '[NOT SET]')}")
    print(f"• Target Locations:   {env.get('TARGET_LOCATIONS', '[NOT SET]')}")

    # 2. Search Portals & Scraper Configurations
    print("\n[2] AGGREGATED JOB BOARD SOURCES (JobSpy)")
    print("-" * 80)
    sites = split_items(env.get("SEARCH_SITES", "indeed,naukri,glassdoor"))
    queries = split_items(env.get("SEARCH_QUERIES", ""), delimiter="|")
    print(f"• Active Portals:     {', '.join(sites)}")
    print(f"• Query Matrix:       {len(queries)} defined queries:")
    for q in queries:
        print(f"    - \"{q}\"")
    print(f"• Window Lookback:    {env.get('HOURS_OLD', '96')} hours")
    print(f"• Results Wanted:     {env.get('RESULTS_WANTED', '50')} per query")
    print(f"• Site Job Cap:       {env.get('MAX_JOBS_PER_SCRAPE_SITE', '30')}")
    print(f"• Polling Delay:      {env.get('SCRAPE_DELAY_SECONDS', '3.0')}s")

    # 3. Direct ATS Feed Endpoints & Real-time Probe
    print("\n[3] DIRECT ATS SOURCES (Live API Verification)")
    print("-" * 80)
    gh_slugs = split_items(env.get("ATS_GREENHOUSE", ""))
    lever_slugs = split_items(env.get("ATS_LEVER", ""))
    ashby_slugs = split_items(env.get("ATS_ASHBY", ""))

    verified_ats = {"greenhouse": {}, "lever": {}, "ashby": {}}

    print(f"\n-> Probing {len(gh_slugs)} Greenhouse Endpoints:")
    for s in gh_slugs:
        res = probe_greenhouse(s)
        verified_ats["greenhouse"][s] = res
        samples = res.get("sample_ids", [])
        sample_str = f"(Sample IDs: {', '.join(samples)})" if samples else ("(No active listings)" if res["status"] == "ONLINE" else f"(Offline: {res.get('error', 'Error')})")
        print(f"   [{res['status']:<7}] {s:<15} | Active Jobs: {res['count']:<4} {sample_str}")

    print(f"\n-> Probing {len(lever_slugs)} Lever Endpoints:")
    for s in lever_slugs:
        res = probe_lever(s)
        verified_ats["lever"][s] = res
        samples = res.get("sample_ids", [])
        sample_str = f"(Sample UUIDs: {', '.join(samples)})" if samples else ("(No active listings)" if res["status"] == "ONLINE" else f"(Offline: {res.get('error', 'Error')})")
        print(f"   [{res['status']:<7}] {s:<15} | Active Jobs: {res['count']:<4} {sample_str}")

    print(f"\n-> Probing {len(ashby_slugs)} Ashby Endpoints:")
    for s in ashby_slugs:
        res = probe_ashby(s)
        verified_ats["ashby"][s] = res
        samples = res.get("sample_ids", [])
        sample_str = f"(Sample UUIDs: {', '.join(samples)})" if samples else ("(No active listings)" if res["status"] == "ONLINE" else f"(Offline: {res.get('error', 'Error')})")
        print(f"   [{res['status']:<7}] {s:<15} | Active Jobs: {res['count']:<4} {sample_str}")

    # 4. Remote & Ingestion Feeds
    print("\n[4] REMOTE FEEDS & EMAIL INGESTION")
    print("-" * 80)
    remote_active = env.get("ENABLE_REMOTE_FEEDS", "false").lower() == "true"
    print(f"• Remote Feeds Active: {remote_active} (Remotive, Jobicy)")
    print(f"• Ingestion Mailbox:   {env.get('EMAIL_ADDRESS', '[NOT SET]')}")
    print(f"• IMAP Server:         {env.get('IMAP_SERVER', 'imap.gmail.com')}:993")
    print(f"• Lookback History:    {env.get('IMAP_LOOKBACK_DAYS', '3')} days")

    # 5. Security & Sensitive Credentials Audit (Masked)
    print("\n[5] SECURITY AUDIT & CREDENTIAL STATUS (Masked for safety)")
    print("-" * 80)
    gemini_key = env.get("GEMINI_API_KEY", "")
    email_pass = env.get("EMAIL_PASSWORD", "")
    tg_token = env.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = env.get("TELEGRAM_CHAT_ID", "")

    print(f"• Gemini API Key:      {mask_secret(gemini_key)}")
    print(f"• Gmail App Password:  {mask_secret(email_pass)}")
    print(f"• Telegram Bot Token:  {mask_secret(tg_token)}")
    print(f"• Telegram Chat ID:    {tg_chat if tg_chat else '[NOT SET]'}")

    # 6. Export Verified JSON
    export_payload = {
        "candidate": {
            "name": env.get("CANDIDATE_NAME"),
            "location": env.get("CANDIDATE_BASE_LOCATION"),
            "roles": split_items(env.get("TARGET_ROLES", "")),
            "target_locations": split_items(env.get("TARGET_LOCATIONS", "")),
        },
        "search_matrix": {
            "portals": sites,
            "queries": queries,
            "hours_lookback": int(env.get("HOURS_OLD", 96)),
            "results_wanted": int(env.get("RESULTS_WANTED", 50)),
        },
        "ats_feeds": verified_ats,
        "scoring_thresholds": {
            "min_top_tier": int(env.get("MIN_SCORE_TOP_TIER", 80)),
            "min_digest": int(env.get("MIN_SCORE_DIGEST", 60)),
            "rerank_from": int(env.get("RERANK_FROM_SCORE", 35)),
        },
        "storage": {
            "db_path": env.get("DB_PATH", "jobs.db"),
            "excel_backup": env.get("EXCEL_BACKUP_PATH", "cloud_jobs_backup.xlsx"),
            "export_dir": env.get("EXCEL_EXPORT_DIR", "./exports"),
        }
    }

    out_json = "sources_verified.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2)

    # 7. Write Sanitized .env Template
    sanitized_env = Path(".env.sanitized")
    with open(".env", "r", encoding="utf-8") as fin, open(sanitized_env, "w", encoding="utf-8") as fout:
        for line in fin:
            if any(line.strip().startswith(sec) for sec in ["GEMINI_API_KEY=", "EMAIL_PASSWORD=", "TELEGRAM_BOT_TOKEN="]):
                key = line.split("=")[0].strip()
                fout.write(f'{key}="REPLACE_WITH_ROTATED_SECRET"\n')
            else:
                fout.write(line)

    print("\n" + "=" * 80)
    print(f"[✓] Active source telemetry saved to:  {out_json}")
    print(f"[✓] Sanitized template created at:     {sanitized_env}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

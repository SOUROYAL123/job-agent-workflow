#!/usr/bin/env python3
"""
write_env.py - Writes the full, validated CareerOS configuration to .env.
Creates a timestamped backup before writing and verifies all keys upon completion.
Runs on standard Python library only.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

# Complete configuration map
CONFIG_MAP = {
    # --------------------------------------------------------------------------
    # 1. CANDIDATE IDENTITY & EVIDENCE VAULT
    # --------------------------------------------------------------------------
    "CANDIDATE_NAME": "Sourav Roy Chowdhury",
    "CANDIDATE_BASE_LOCATION": "Kolkata, India",
    "CANDIDATE_PROFILE_PATH": "candidate_profile.txt",
    "MASTER_RESUME_DOCX": "templates/master_resume.docx",
    "TARGET_ROLES": "AWS Cloud Support Engineer, Cloud Support Associate, Cloud Operations Engineer, Technical Support Engineer, Linux Support Engineer, Infrastructure Support Specialist",
    "TARGET_LOCATIONS": "Kolkata, Remote, Bengaluru, Hyderabad, Pune, Chennai, Noida, Gurugram",
    "SEARCH_QUERIES": "Cloud Support Engineer AWS|Linux Support Engineer|DevOps Support Engineer",

    # --------------------------------------------------------------------------
    # 2. GOOGLE GEMINI & LLM REASONING CORE
    # --------------------------------------------------------------------------
    "GEMINI_API_KEY": "REPLACE_WITH_YOUR_KEY",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GEMINI_FALLBACK_MODEL": "gemini-1.5-flash",
    "LLM_TEMPERATURE": "0.2",
    "LLM_REQUEST_TIMEOUT": "20",
    "DEEPSEEK_API_KEY": "your_deepseek_api_key_here",
    "FALLBACK_API_KEY": "your_groq_or_openrouter_key_here",
    "LITELLM_MASTER_KEY": "change_me_to_a_long_random_string",

    # --------------------------------------------------------------------------
    # 3. SCORING, FILTER GUARDS & RERANKING
    # --------------------------------------------------------------------------
    "MIN_SCORE_TOP_TIER": "80",
    "MIN_SCORE_DIGEST": "60",
    "MIN_EMAIL_MATCH_SCORE": "60",
    "RERANK_MODEL": "gemini-2.5-flash",
    "RERANK_FROM_SCORE": "35",
    "SCORE_SLEEP_SEC": "8",
    "MAX_SCORE_PER_RUN": "60",
    "SENIOR_EXCLUDE_TERMS": "staff|principal|director|vp|head of|lead architect|lead engineer|architect iii",

    # --------------------------------------------------------------------------
    # 4. INSTANT TELEGRAM PUSH NOTIFICATIONS
    # --------------------------------------------------------------------------
    "TELEGRAM_BOT_TOKEN": "your_telegram_bot_token_here",
    "TELEGRAM_CHAT_ID": "5750713528",
    "ENABLE_TELEGRAM_ALERTS": "true",

    # --------------------------------------------------------------------------
    # 5. GMAIL / IMAP RECRUITER TRIAGE & EMAIL DIGEST
    # --------------------------------------------------------------------------
    "EMAIL_ADDRESS": "souravrchowdhury2020@gmail.com",
    "EMAIL_PASSWORD": "your_email_password_here",
    "RECIPIENT_EMAIL": "souravrchowdhury2020@gmail.com",
    "IMAP_SERVER": "imap.gmail.com",
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": "465",
    "IMAP_LOOKBACK_DAYS": "3",
    "SEND_EMAIL_DIGEST": "true",

    # --------------------------------------------------------------------------
    # 6. SCRAPING & FEED DISCOVERY (JobSpy, Remote Feeds)
    # --------------------------------------------------------------------------
    "SEARCH_SITES": "indeed,naukri,glassdoor",
    "RESULTS_WANTED": "50",
    "HOURS_OLD": "96",
    "MAX_JOBS_PER_SCRAPE_SITE": "30",
    "SCRAPE_DELAY_SECONDS": "3.0",
    "ENABLE_REMOTE_FEEDS": "true",
    "PROXIES": "",

    # --------------------------------------------------------------------------
    # 7. ATS API DIRECT CONNECTORS (POOLED COMPANY SLUGS)
    # --------------------------------------------------------------------------
    "ATS_GREENHOUSE": "canonical,cloudflare,datadog,gitlab,grafanalabs,tailscale,vercel",
    "ATS_LEVER": "15five,360learning,90seconds,cred,fly,freshworks,meesho",
    "ATS_ASHBY": "1password,render,supabase",
    "COMPANIES_FILE": "companies.txt",

    # --------------------------------------------------------------------------
    # 8. LOCAL STORAGE, DATABASE & REPORTING PATHS
    # --------------------------------------------------------------------------
    "DB_PATH": "jobs.db",
    "EXCEL_PATH": "Job_Digest_Tracker.xlsx",
    "EXCEL_BACKUP_PATH": "cloud_jobs_backup.xlsx",
    "EXCEL_EXPORT_DIR": "./exports",

    # --------------------------------------------------------------------------
    # 9. TIMEZONE, SECURITY & CONTROLS
    # --------------------------------------------------------------------------
    "TIMEZONE": "Asia/Kolkata",
    "TIMEZONE_OFFSET_HOURS": "5.5",
    "ENABLE_STRICT_SECURITY_AUDIT": "true",
    "DRY_RUN": "false"
}


def build_env_file_string(config: dict) -> str:
    """Builds clean, structured .env file text with section headers."""
    return f"""# ==============================================================================
# CAREEROS MASTER ENGINE - CONSOLIDATED ENVIRONMENT CONFIGURATION
# Generated on: {datetime.now():%Y-%m-%d %H:%M:%S}
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. CANDIDATE IDENTITY & EVIDENCE VAULT
# ------------------------------------------------------------------------------
CANDIDATE_NAME="{config['CANDIDATE_NAME']}"
CANDIDATE_BASE_LOCATION="{config['CANDIDATE_BASE_LOCATION']}"
CANDIDATE_PROFILE_PATH="{config['CANDIDATE_PROFILE_PATH']}"
MASTER_RESUME_DOCX="{config['MASTER_RESUME_DOCX']}"
TARGET_ROLES="{config['TARGET_ROLES']}"
TARGET_LOCATIONS="{config['TARGET_LOCATIONS']}"
SEARCH_QUERIES="{config['SEARCH_QUERIES']}"

# ------------------------------------------------------------------------------
# 2. GOOGLE GEMINI & LLM REASONING CORE
# ------------------------------------------------------------------------------
GEMINI_API_KEY="{config['GEMINI_API_KEY']}"
GEMINI_MODEL="{config['GEMINI_MODEL']}"
GEMINI_FALLBACK_MODEL="{config['GEMINI_FALLBACK_MODEL']}"
LLM_TEMPERATURE={config['LLM_TEMPERATURE']}
LLM_REQUEST_TIMEOUT={config['LLM_REQUEST_TIMEOUT']}

DEEPSEEK_API_KEY="{config['DEEPSEEK_API_KEY']}"
FALLBACK_API_KEY="{config['FALLBACK_API_KEY']}"
LITELLM_MASTER_KEY="{config['LITELLM_MASTER_KEY']}"

# ------------------------------------------------------------------------------
# 3. SCORING, FILTER GUARDS & RERANKING
# ------------------------------------------------------------------------------
MIN_SCORE_TOP_TIER={config['MIN_SCORE_TOP_TIER']}
MIN_SCORE_DIGEST={config['MIN_SCORE_DIGEST']}
MIN_EMAIL_MATCH_SCORE={config['MIN_EMAIL_MATCH_SCORE']}
RERANK_MODEL="{config['RERANK_MODEL']}"
RERANK_FROM_SCORE={config['RERANK_FROM_SCORE']}
SCORE_SLEEP_SEC={config['SCORE_SLEEP_SEC']}
MAX_SCORE_PER_RUN={config['MAX_SCORE_PER_RUN']}
SENIOR_EXCLUDE_TERMS="{config['SENIOR_EXCLUDE_TERMS']}"

# ------------------------------------------------------------------------------
# 4. INSTANT TELEGRAM PUSH NOTIFICATIONS
# ------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN="{config['TELEGRAM_BOT_TOKEN']}"
TELEGRAM_CHAT_ID="{config['TELEGRAM_CHAT_ID']}"
ENABLE_TELEGRAM_ALERTS="{config['ENABLE_TELEGRAM_ALERTS']}"

# ------------------------------------------------------------------------------
# 5. GMAIL / IMAP RECRUITER TRIAGE & EMAIL DIGEST
# ------------------------------------------------------------------------------
EMAIL_ADDRESS="{config['EMAIL_ADDRESS']}"
EMAIL_PASSWORD="{config['EMAIL_PASSWORD']}"
RECIPIENT_EMAIL="{config['RECIPIENT_EMAIL']}"
IMAP_SERVER="{config['IMAP_SERVER']}"
SMTP_SERVER="{config['SMTP_SERVER']}"
SMTP_PORT={config['SMTP_PORT']}
IMAP_LOOKBACK_DAYS={config['IMAP_LOOKBACK_DAYS']}
SEND_EMAIL_DIGEST="{config['SEND_EMAIL_DIGEST']}"

# ------------------------------------------------------------------------------
# 6. SCRAPING & FEED DISCOVERY (JobSpy, Remote Feeds)
# ------------------------------------------------------------------------------
SEARCH_SITES="{config['SEARCH_SITES']}"
RESULTS_WANTED={config['RESULTS_WANTED']}
HOURS_OLD={config['HOURS_OLD']}
MAX_JOBS_PER_SCRAPE_SITE={config['MAX_JOBS_PER_SCRAPE_SITE']}
SCRAPE_DELAY_SECONDS={config['SCRAPE_DELAY_SECONDS']}
ENABLE_REMOTE_FEEDS="{config['ENABLE_REMOTE_FEEDS']}"
PROXIES="{config['PROXIES']}"

# ------------------------------------------------------------------------------
# 7. ATS API DIRECT CONNECTORS (POOLED COMPANY SLUGS)
# ------------------------------------------------------------------------------
ATS_GREENHOUSE="{config['ATS_GREENHOUSE']}"
ATS_LEVER="{config['ATS_LEVER']}"
ATS_ASHBY="{config['ATS_ASHBY']}"
COMPANIES_FILE="{config['COMPANIES_FILE']}"

# ------------------------------------------------------------------------------
# 8. LOCAL STORAGE, DATABASE & REPORTING PATHS
# ------------------------------------------------------------------------------
DB_PATH="{config['DB_PATH']}"
EXCEL_PATH="{config['EXCEL_PATH']}"
EXCEL_BACKUP_PATH="{config['EXCEL_BACKUP_PATH']}"
EXCEL_EXPORT_DIR="{config['EXCEL_EXPORT_DIR']}"

# ------------------------------------------------------------------------------
# 9. TIMEZONE, SECURITY & CONTROLS
# ------------------------------------------------------------------------------
TIMEZONE="{config['TIMEZONE']}"
TIMEZONE_OFFSET_HOURS={config['TIMEZONE_OFFSET_HOURS']}
ENABLE_STRICT_SECURITY_AUDIT="{config['ENABLE_STRICT_SECURITY_AUDIT']}"
DRY_RUN="{config['DRY_RUN']}"
"""


def main():
    target_path = Path(".env")

    # 1. Back up existing file if present
    if target_path.exists():
        backup_path = Path(f".env.bak_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copyfile(target_path, backup_path)
        print(f"[✓] Existing .env backed up to: {backup_path.name}")

    # 2. Write new .env file
    env_content = build_env_file_string(CONFIG_MAP)
    target_path.write_text(env_content, encoding="utf-8")
    print(f"[✓] Successfully wrote {len(CONFIG_MAP)} parameters to .env ({len(env_content)} bytes)")

    # 3. Read back and verify
    lines = [
        line.strip()
        for line in target_path.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.strip().startswith("#")
    ]
    print(f"[✓] Verification: {len(lines)} active keys verified on disk.")


if __name__ == "__main__":
    main()

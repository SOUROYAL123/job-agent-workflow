#!/usr/bin/env python3
"""
create_readme.py - Generates the production README.md for CareerOS.
"""
from pathlib import Path

README_CONTENT = """# CareerOS: Autonomous Job Intelligence & Application Pipeline

CareerOS is an autonomous, agentic career intelligence engine designed to continuously monitor direct Application Tracking Systems (ATS), evaluate job opportunities using Google Gemini reasoning models, deliver real-time Telegram alerts for high-conviction roles, and maintain a local application tracker in SQLite and Excel.

---

## Architecture Overview

```
                          ┌────────────────────────┐
                          │   Direct ATS Boards    │
                          │ Greenhouse/Lever/Ashby │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │    ATS Ingestion &     │
                          │   Location Filtering   │
                          └───────────┬────────────┘
                                      │
                                      ▼
                          ┌────────────────────────┐
                          │  Google Gemini Engine  │
                          │ (Score, Tips, Pitches) │
                          └─────┬────────────┬─────┘
                                │            │
           Score >= 80          │            │  All Records
                                ▼            ▼
        ┌─────────────────────────┐        ┌─────────────────────────┐
        │  Telegram Bot Dispatch  │        │   SQLite DB (jobs.db)   │
        │ (@sourav_careeros_bot)  │        │  & Excel Digest Backup  │
        └─────────────────────────┘        └─────────────────────────┘
```

---

## Core Capabilities

- **Direct ATS Harvester:** Probes company career portals on Greenhouse, Lever, and Ashby directly via API endpoints, eliminating third-party aggregator noise and stale postings.
- **Intelligent Fit Scoring (0-100):** Leverages Google Gemini (`gemini-1.5-flash`) to analyze job descriptions against candidate profiles, evaluating technical match, seniority bounds, and missing skills.
- **Tailored STAR Pitch Generator:** Synthesizes custom resume optimization tips and STAR (Situation, Task, Action, Result) interview talking points for top-tier opportunities.
- **Instant Priority Alerts:** Delivers formatted markdown alerts via Telegram for high-scoring positions ($\\ge 80$) with direct application deep-links.
- **Two-Tier Storage:** Tracks ingestion states and evaluation histories in SQLite (`jobs.db`) while compiling application spreadsheets (`cloud_jobs_backup.xlsx`).
- **Inbox Recruiter Triage:** Monitors incoming recruiter correspondence and status updates via authenticated Gmail IMAP.
- **Enterprise Secret Hygiene:** Enforces local pre-commit hooks, Gitleaks pattern detection, and push protection to prevent API keys or personal credentials from entering version control.

---

## Project Structure

```
.
├── .github/
│   ├── workflows/
│   │   ├── daily.yml             # GitHub Actions automated scheduled run
│   │   └── test.yml              # CI verification pipeline
│   └── dependabot.yml            # Dependency vulnerability scanning
├── .gitignore                    # Exclusion rules for secrets, DBs, and reports
├── .pre-commit-config.yaml       # Hook definitions (Gitleaks, whitespace, YAML)
├── careeros_master.py            # Master orchestration engine and CLI runner
├── ats_finder.py                 # Multi-board ATS scraper (Greenhouse, Lever, Ashby)
├── remote_feeds.py               # Aggregator feed parser for verified remote roles
├── candidate_profile.example.txt # Profile baseline template for Gemini reasoning
├── dynamic_feeds.json            # Active external API registry
├── github_sources_registry.json  # Curated target repo and company listings
├── requirements.txt              # Production Python package dependencies
├── run_daily.bat                 # Windows Task Scheduler automation entrypoint
└── README.md                     # System documentation
```

---

## Quick Setup & Execution

### 1. Requirements & Dependencies
```powershell
# Clone the repository
git clone https://github.com/SOUROYAL123/job-agent-workflow.git
cd job-agent-workflow

# Create virtual environment and install packages
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment Configuration (.env)
Copy `.env.example` to `.env` and fill in your operational credentials:
- `GEMINI_API_KEY`: Google AI Studio API key (`gemini-1.5-flash`)
- `TELEGRAM_BOT_TOKEN`: Token obtained from `@BotFather`
- `TELEGRAM_CHAT_ID`: Your numerical Telegram user/chat ID
- `EMAIL_ADDRESS` & `EMAIL_PASSWORD`: Gmail App Password (2FA enabled)

### 3. Verification & Live Run
```powershell
# Run credential and connectivity diagnostics
py careeros_master.py --test

# Run live job discovery, Gemini scoring, and Telegram alerts
py careeros_master.py
```

---

## Database Management

The pipeline tracks jobs inside an internal SQLite database (`jobs.db`).

- **Inspect database status:**
  ```powershell
  py -c "import sqlite3; conn = sqlite3.connect('jobs.db'); cur = conn.cursor(); print('Total jobs:', cur.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]); print('Unscored jobs:', cur.execute('SELECT COUNT(*) FROM jobs WHERE score IS NULL').fetchone()[0])"
  ```

- **Reset cached jobs to unscored state for Gemini evaluation:**
  ```powershell
  py -c "import sqlite3; conn = sqlite3.connect('jobs.db'); cur = conn.cursor(); cur.execute('UPDATE jobs SET score = NULL, evaluated_at = NULL'); conn.commit(); print(f'[+] Reset {cur.rowcount} jobs for evaluation.'); conn.close()"
  ```

---

## Automation (Windows Task Scheduler)

To configure CareerOS to run autonomously every morning at 8:00 AM IST:
```powershell
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$((Get-Location).Path)\\run_daily.bat`"" -WorkingDirectory "$((Get-Location).Path)"
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
Register-ScheduledTask -TaskName "CareerOS_Daily_Execution" -Action $action -Trigger $trigger -Description "Daily CareerOS job discovery and AI evaluation pipeline"
```
"""

def main():
    target = Path("README.md")
    target.write_text(README_CONTENT.strip(), encoding="utf-8")
    print(f"[+] Successfully created {target.resolve()} ({len(README_CONTENT)} characters)")

if __name__ == "__main__":
    main()
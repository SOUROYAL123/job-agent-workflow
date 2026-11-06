# CareerOS: Autonomous Job Discovery & AI Career Intelligence Engine

CareerOS is a Python job-search pipeline. It pulls vacancies from ATS platforms (Greenhouse, Lever, Ashby) and job boards, scores them against a candidate profile with Google Gemini, generates STAR interview pitches, and sends alerts via Telegram and Gmail.

## Scripts

| Script | Category | Lines | Role |
| :--- | :--- | ---: | :--- |
| `job_agent.py` | Core Orchestration & Scoring | 1961 | Main pipeline: ATS/board ingestion, SQLite dedup, Gemini fit scoring, STAR pitch generation, Telegram/Gmail alerts, Excel export. |
| `auto_runner.py` | Core Orchestration & Scoring | 281 | Headless scheduler wrapper: run lock, DB health check and backup, rotating logs, failure alerts, then runs the follow-on scripts. |
| `edge_engine.py` | Job Feed Discovery | 498 | Conversion scoring that prioritises fresh Direct-ATS and Kolkata roles; resilient HTTP helpers. |
| `ats_finder.py` | Job Feed Discovery | 432 | Probes Greenhouse, Lever and Ashby with company slug lists to find active career boards. |
| `remote_feeds.py` | Job Feed Discovery | 459 | Secondary fetcher for remote tech job boards. |
| `pull_live_ids.py` | Diagnostics & Sync | 782 | Verifies Telegram chat IDs, Gmail IMAP/SMTP and Gemini endpoint status. |
| `auto_fetch_ids.py` | Diagnostics & Sync | 208 | Fetches Telegram bot updates and chat IDs from the Telegram API. |
| `reextract_env_sources.py` | Environment & Config | 486 | Extracts company slugs and ATS registries from raw config strings into JSON. |
| `merge_env.py` | Environment & Config | 300 | Merges new config keys into an existing .env without overwriting secrets. |
| `security_audit.py` | Diagnostics & Sync | 148 | Scans code, configs and logs for hardcoded secrets. |
| `inbox_triage.py` | Inbox & Tracking | 224 | Gmail IMAP triage of recruiter replies, interview invites and receipts. |
| `followup_reminder.py` | Inbox & Tracking | 284 | Tracks application dates and emails reminders for unanswered applications. |
| `weekly_summary.py` | Inbox & Tracking | 313 | Weekly digest of submissions, responses and source conversion. |
| `networking_helper.py` | Candidate Prep | 506 | Drafts connection requests and referral/follow-up messages. |
| `resume_tailor.py` | Candidate Prep | 412 | Tailors resume bullets to a specific job description. |
| `interview_simulator.py` | Candidate Prep | 178 | Generates technical and behavioural interview questions for a target job. |
| `test_units.py` | Testing | 76 | Unit tests: poison-row 3-strike cap, conversion scoring. |
| `test_pipeline.py` | Testing | 247 | Integration tests: digest, Excel export, notes sync, DB migration, auth failure. |

## Supporting Files

| File | Purpose |
| :--- | :--- |
| `.env.example` | Template for API keys, Telegram tokens and email settings. |
| `candidate_profile.example.txt` | Template for your candidate profile. |
| `dynamic_feeds.json` | Registry of verified Greenhouse, Lever and Ashby boards. |
| `github_sources_registry.json` | Curated index of hiring-related source repos. |
| `requirements.txt` | Direct dependencies, pinned. |
| `setup_automation.ps1` | Creates the venv and Windows Task Scheduler trigger. |
| `START_HERE.bat` | One-click Windows runner. |
| `.github/workflows/test.yml` | CI: unit and integration tests on push and PR. |
| `.github/workflows/daily.yml` | Manual-dispatch pipeline run (scheduled runs use Windows Task Scheduler). |

## Pipeline

```
ATS + job boards -> SQLite dedup (jobs.db) -> Gemini scoring (0-100, missing skills, STAR pitch)
   -> score >= 80: Telegram push
   -> all scored jobs: Excel workbook + database commit
   -> auto_runner follow-ons: resume tailor, networking, inbox triage, follow-ups, weekly summary
```

## Quick Start (Windows)

```powershell
git clone https://github.com/SOUROYAL123/job-agent-workflow.git
cd job-agent-workflow
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
copy candidate_profile.example.txt candidate_profile.txt
```

Fill in `.env` and `candidate_profile.txt`, then:

```powershell
py test_units.py       # unit tests
py test_pipeline.py    # integration tests
py job_agent.py        # live ingestion + scoring
py auto_runner.py      # full automated run (what the scheduler calls)
```

Never commit `.env`, `candidate_profile.txt`, `*.db` or `*.xlsx`; they are gitignored.

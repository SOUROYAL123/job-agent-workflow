# CareerOS: Autonomous Job Discovery & AI Career Intelligence Engine

CareerOS is an autonomous, agentic job search pipeline engineered in Python. It aggregates technical vacancy postings across verified ATS platforms (Greenhouse, Lever, Ashby), evaluates job descriptions against candidate profiles using Google Gemini, generates tailored interview pitches (STAR method), and dispatches instant push alerts via Telegram and Gmail.

---

## Complete Workflow Script Analysis

| Script Name | Category | Lines | Architecture Role & Responsibilities |
| :--- | :--- | :--- | :--- |
| `apollo_hunter_engine.py` | Job Feed Discovery & Scraping | 164 | Recruiter and hiring manager contact discovery engine for targeted cold outreach. |
| `ats_finder.py` | Job Feed Discovery & Scraping | 216 | Automated ATS endpoint scanner. Probes Greenhouse, Lever, and Ashby APIs using curated company slug lists to detect active career boards. |
| `auto_fetch_ids.py` | Auditing & Feed Sync | 104 | Automated parameter discovery script that retrieves Telegram bot updates and channel IDs directly from the Telegram API. |
| `auto_runner.py` | Core Orchestration & Scoring | 135 | Headless task scheduler runner with execution locking, error handling, and rotating log management for daily automated runs. |
| `careeros_master.py` | Core Orchestration & Scoring | 533 | Primary production orchestrator. Handles live ATS ingestion (Greenhouse, Lever, Ashby), SQLite deduplication, Gemini 1.5 Flash scoring, STAR pitch generation, Telegram push alerts, and Excel backup export. |
| `create_readme_script.py` | Utility & Diagnostics | 143 | Workflow utility script. |
| `edge_engine.py` | Job Feed Discovery & Scraping | 249 | High-speed HTTP fetcher with custom user-agents, timeout handling, and request rate-limiting for resilient ATS scraping. |
| `followup_reminder.py` | Inbox Triage & Tracking | 142 | Application cadence tracker. Monitors application dates and generates timely follow-up reminders for unanswered submissions. |
| `get_chat_id.py` | Testing & Diagnostics | 8 | Lightweight diagnostic script to print the active numerical chat ID from incoming Telegram bot messages. |
| `github_repo_sync.py` | Auditing & Feed Sync | 521 | Repository synchronization utility. Tracks upstream ATS feed changes, updates organization registries, and prunes dead endpoints. |
| `inbox_triage.py` | Inbox Triage & Tracking | 112 | Automated email monitoring engine. Uses Gmail IMAP/SMTP to triage inbound recruiter emails, interview invitations, and application receipts. |
| `inspect_keys.py` | Utility & Diagnostics | 47 | Workflow utility script. |
| `interview_simulator.py` | Candidate Tailoring & Prep | 89 | Interactive interview preparation simulator. Uses Gemini to generate technical and behavioral interview questions based on target job postings. |
| `job_agent.py` | Core Orchestration & Scoring | 828 | Core CareerOS agent engine containing vacancy extraction heuristics, regex pattern matching, and Gemini scoring logic. |
| `make_ca_bundle.py` | Utility & Diagnostics | 11 | Workflow utility script. |
| `merge_env.py` | Environment & Configuration | 150 | Environment reconciliation tool that merges new configuration keys into existing `.env` files without overwriting existing secrets. |
| `networking_helper.py` | Candidate Tailoring & Prep | 253 | Outreach and referral assistant. Drafts personalized connection requests, recruiter follow-ups, and networking pitches. |
| `ping2.py` | Testing & Diagnostics | 22 | Direct model diagnostic script that tests content generation across candidate Gemini model endpoints. |
| `ping_gemini.py` | Testing & Diagnostics | 10 | Standalone API test verifying connectivity and token authorization against the Gemini API endpoint. |
| `ping_telegram.py` | Testing & Diagnostics | 14 | Standalone notification test validating bot token delivery to your Telegram chat ID. |
| `pull_live_ids.py` | Auditing & Feed Sync | 391 | Credential and environment diagnostic probe. Verifies Telegram chat IDs, Gmail IMAP/SMTP connectivity, and Gemini endpoint status. |
| `reextract_env_sources.py` | Environment & Configuration | 243 | Extracts and consolidates company slugs and ATS registries from raw configuration strings into structured JSON files. |
| `remote_feeds.py` | Job Feed Discovery & Scraping | 308 | Secondary job board fetcher for remote tech listings, remote developer boards, and distributed cloud roles. |
| `remote_feeds_backup.py` | Utility & Diagnostics | 230 | Workflow utility script. |
| `resume_tailor.py` | Candidate Tailoring & Prep | 206 | Targeted resume generator. Evaluates candidate profiles against specific job descriptions to produce tailored STAR achievement bullets. |
| `security_audit.py` | Auditing & Feed Sync | 74 | Static code analysis tool. Scans python files, configs, and logs for hardcoded secrets, exposed tokens, or unmasked credentials. |
| `ssl_test.py` | Utility & Diagnostics | 21 | Workflow utility script. |
| `test_pipeline.py` | Testing & Diagnostics | 246 | Integration test suite validating end-to-end data flow: ATS ingestion -> Gemini scoring -> database commit -> alert dispatch. |
| `test_units.py` | Testing & Diagnostics | 38 | Unit test suite testing individual helper functions, regex parsing, score normalization, and schema validation. |
| `ultimate_job_agent.py` | Core Orchestration & Scoring | 718 | Advanced multi-stage agent pipeline incorporating iterative keyword scoring, reranking filters, and structured candidate matching. |
| `update_credentials.py` | Utility & Diagnostics | 89 | Workflow utility script. |
| `weekly_summary.py` | Inbox Triage & Tracking | 157 | Weekly performance auditor. Compiles submission statistics, response metrics, and source conversion rates into an email digest. |
| `write_env.py` | Environment & Configuration | 229 | Configuration utility that builds, formats, and validates the master `.env` file with timestamped backups. |

---

## Supporting Infrastructure & Configuration

| File Name | Purpose |
| :--- | :--- |
| `.env.example` | Template configuration specifying required API keys, Telegram tokens, and ATS board slugs. |
| `.gitignore` | Exclusion rules ensuring `.env`, `jobs.db`, generated spreadsheets (`*.xlsx`), and logs are never tracked. |
| `.pre-commit-config.yaml` | Git pre-commit hooks enforcing formatting, YAML linting, and preventing secret exposure via Gitleaks. |
| `dynamic_feeds.json` | Registry of verified corporate Greenhouse, Lever, and Ashby ATS URLs. |
| `github_sources_registry.json` | Curated index of cloud infrastructure repositories and tech hiring databases. |
| `requirements.txt` | Locked dependency manifest for requests, google-generativeai, openpyxl, python-dotenv, and pre-commit. |
| `setup_automation.ps1` | PowerShell deployment script configuring Python virtual environments and Task Scheduler triggers. |
| `START_HERE.bat` | One-click Windows batch runner for local diagnostic checks and immediate pipeline execution. |

---

## Pipeline Architecture

```
                      +---------------------------------------+
                      |       ATS Discovery & Ingestion       |
                      |   (Greenhouse, Lever, Ashby APIs)     |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |        SQLite Deduplication           |
                      |             (jobs.db)                 |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       Gemini AI Reasoning Engine      |
                      |   - Fit Scoring (0-100)               |
                      |   - Missing Skill Analysis            |
                      |   - Tailored STAR Interview Pitches   |
                      +---------+-------------------+---------+
                                |                   |
                 +--------------+                   +---------------+
                 | (Score >= 80)                                    |
                 v                                                  v
+---------------------------------+                +---------------------------------+
|      Instant Telegram Push      |                |   Workbook & Database Commit    |
|    (@sourav_careeros_bot)       |                |    (cloud_jobs_backup.xlsx)     |
+---------------------------------+                +---------------------------------+
```

---

## Quick Start

### 1. Installation
```powershell
git clone [https://github.com/SOUROYAL123/job-agent-workflow.git](https://github.com/SOUROYAL123/job-agent-workflow.git)
cd job-agent-workflow
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Diagnostics Check
```powershell
py careeros_master.py --test
```

### 3. Run Live Ingestion & AI Scoring
```powershell
py careeros_master.py
```
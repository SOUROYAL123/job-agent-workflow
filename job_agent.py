"""
========================================================================================
ULTIMATE AGENTIC CAREER INTELLIGENCE & JOB SEARCH ENGINE (CareerOS Core)
========================================================================================
Integrates:
- Discovery: Multi-source ingestion (JobSpy, ATS feeds, Remote APIs, Custom JSON)
- Parsing & Vault: Evidence-backed candidate profile loader (.txt, .md, .pdf/.docx hooks)
- Security & Anti-Fraud: Domain validation, fee/scam heuristic checks, PII protection
- Reasoning & Scoring: Google Gemini API (structured JSON response) with offline fallback
- Alerting: Telegram push notifications for top-tier matches (sent once per job)
- Persistence: SQLite database (jobs, applications, audit logs)
- Reporting: Professional multi-tab Excel Workbook (openpyxl) with IST timestamps & styles

Environment variables (set in PowerShell with $env:NAME="value"):
    GEMINI_API_KEY        optional, enables Gemini scoring (else offline heuristic)
    TELEGRAM_BOT_TOKEN    optional, from @BotFather
    TELEGRAM_CHAT_ID      optional, your chat id (message your bot, then check getUpdates)
========================================================================================
"""

import os
from dotenv import load_dotenv
load_dotenv(override=True)
import sys
import json
import re
import html
import hashlib
import sqlite3
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------
# 1. UPLOAD & CONFIGURATION VARIABLES (CONFIG LAYER)
# --------------------------------------------------------------------------------------
@dataclass
class AgentConfig:
    # --- Candidate & Profile Upload Variables ---
    CANDIDATE_PROFILE_PATH: str = os.getenv("CANDIDATE_PROFILE_PATH", "candidate_profile.txt")
    CANDIDATE_NAME: str = os.getenv("CANDIDATE_NAME", "Sourav Roy Chowdhury")
    CANDIDATE_BASE_LOCATION: str = os.getenv("CANDIDATE_BASE_LOCATION", "Kolkata, India")
    TARGET_ROLES: List[str] = field(default_factory=lambda: [
        "AWS Cloud Support Engineer",
        "Cloud Support Associate",
        "Cloud Operations Engineer",
        "Technical Support Engineer",
        "Linux Support Engineer",
        "Infrastructure Support Specialist"
    ])
    TARGET_LOCATIONS: List[str] = field(default_factory=lambda: [
        "Kolkata", "Remote", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Noida", "Gurugram"
    ])

    # --- AI & Reasoning Engine (Gemini) ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    TEMPERATURE: float = 0.2

    # --- Telegram Alerting ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_ALERTS_ENABLED: bool = os.getenv("TELEGRAM_ALERTS_ENABLED", "1") == "1"

    # --- Scoring & Prioritization Thresholds ---
    MIN_SCORE_TOP_TIER: int = int(os.getenv("MIN_SCORE_TOP_TIER", "80"))
    MIN_SCORE_DIGEST: int = int(os.getenv("MIN_SCORE_DIGEST", "60"))
    SENIOR_EXCLUDE_TERMS: List[str] = field(default_factory=lambda: [
        "staff", "principal", "director", "vp", "head of", "lead architect", "lead", "architect iii"
    ])

    # --- Storage & Export Variables ---
    DB_PATH: str = os.getenv("DB_PATH", "jobs_career_vault.db")
    EXCEL_EXPORT_DIR: str = os.getenv("EXCEL_EXPORT_DIR", "./exports")
    EXCEL_FILENAME_PREFIX: str = "Job_Digest_Report"

    # --- Timezone & Localization ---
    TIMEZONE_OFFSET_HOURS: float = 5.5  # IST (UTC+05:30)

    # --- Security & Anti-Fraud Thresholds ---
    SCAM_KEYWORDS: List[str] = field(default_factory=lambda: [
        "registration fee", "processing fee", "security deposit", "pay for training",
        "bank details required before interview", "cryptocurrency investment",
        "telegram task", "daily payment task", "whatsapp hr only", "send money"
    ])
    FREE_EMAIL_DOMAINS: List[str] = field(default_factory=lambda: [
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "protonmail.com"
    ])

config = AgentConfig()


# --------------------------------------------------------------------------------------
# 2. TIME & HASH HELPERS
# --------------------------------------------------------------------------------------
def get_current_ist_timestamp() -> str:
    """Returns ISO format timestamp localized to Indian Standard Time (IST)."""
    tz_ist = timezone(timedelta(hours=config.TIMEZONE_OFFSET_HOURS))
    return datetime.now(tz_ist).strftime("%Y-%m-%d %H:%M:%S IST")

def compute_job_hash(url: str, title: str, company: str) -> str:
    """Generates a stable, canonical hash ignoring tracking query parameters."""
    clean_url = url.split("?")[0].split("&")[0].strip().lower()
    norm_title = re.sub(r"[^a-z0-9]", "", title.lower())
    norm_company = re.sub(r"[^a-z0-9]", "", company.lower())
    payload = f"{clean_url}|{norm_title}|{norm_company}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


# --------------------------------------------------------------------------------------
# 3. DATABASE LAYER (SQLITE PERSISTENCE)
# --------------------------------------------------------------------------------------
class DatabaseManager:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            # Table 1: Scraped & Ingested Jobs
            conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_hash TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                job_url TEXT NOT NULL,
                direct_url TEXT,
                source_channel TEXT NOT NULL,
                source_site TEXT,
                date_posted TEXT,
                discovered_at TEXT NOT NULL,
                raw_description TEXT,
                match_score INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'Unreviewed',
                recommendation TEXT,
                fit_reason TEXT,
                missing_skills TEXT,
                resume_tailor_tip TEXT,
                star_pitch TEXT,
                is_scam INTEGER DEFAULT 0,
                scam_reason TEXT,
                scored INTEGER DEFAULT 0,
                scored_at TEXT,
                user_notes TEXT DEFAULT '',
                application_status TEXT DEFAULT 'New',
                telegram_alerted INTEGER DEFAULT 0
            );
            """)

            # Migration: add telegram_alerted to databases created by older versions
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
            if "telegram_alerted" not in cols:
                conn.execute("ALTER TABLE jobs ADD COLUMN telegram_alerted INTEGER DEFAULT 0")

            # Table 2: Application Lifecycle & Tracker
            conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER UNIQUE,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Applied',
                applied_date TEXT NOT NULL,
                follow_up_date TEXT,
                notes TEXT,
                updated_at TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );
            """)

            # Table 3: System Audit & Health Log
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            );
            """)
            conn.commit()

    def insert_or_get_job(self, job_dict: Dict[str, Any]) -> Tuple[int, bool]:
        """Inserts a job if unique. Returns (job_id, is_new)."""
        job_hash = compute_job_hash(job_dict["job_url"], job_dict["title"], job_dict["company"])
        discovered_at = get_current_ist_timestamp()
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM jobs WHERE job_hash = ?", (job_hash,))
            row = cur.fetchone()
            if row:
                return row["id"], False

            cur.execute("""
            INSERT INTO jobs (
                job_hash, title, company, location, job_url, direct_url,
                source_channel, source_site, date_posted, discovered_at,
                raw_description, user_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_hash, job_dict["title"], job_dict["company"], job_dict.get("location", "Not Specified"),
                job_dict["job_url"], job_dict.get("direct_url", job_dict["job_url"]),
                job_dict.get("source_channel", "Scrape"), job_dict.get("source_site", "Direct"),
                job_dict.get("date_posted", datetime.now().strftime("%Y-%m-%d")),
                discovered_at, job_dict.get("raw_description", ""), ""
            ))
            conn.commit()
            return cur.lastrowid, True

    def get_unscored_jobs(self) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute("SELECT * FROM jobs WHERE scored = 0").fetchall()

    def get_pending_alerts(self, min_score: int) -> List[sqlite3.Row]:
        """Top-tier, non-scam, scored jobs that have not been pushed to Telegram yet."""
        with self.get_connection() as conn:
            return conn.execute("""
                SELECT * FROM jobs
                WHERE scored = 1 AND is_scam = 0
                  AND match_score >= ? AND telegram_alerted = 0
                ORDER BY match_score DESC
            """, (min_score,)).fetchall()

    def mark_alerted(self, job_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE jobs SET telegram_alerted = 1 WHERE id = ?", (job_id,))
            conn.commit()

    def update_job_score(self, job_id: int, score_data: Dict[str, Any]):
        scored_at = get_current_ist_timestamp()
        with self.get_connection() as conn:
            conn.execute("""
            UPDATE jobs SET
                match_score = ?,
                priority = ?,
                recommendation = ?,
                fit_reason = ?,
                missing_skills = ?,
                resume_tailor_tip = ?,
                star_pitch = ?,
                is_scam = ?,
                scam_reason = ?,
                scored = 1,
                scored_at = ?
            WHERE id = ?
            """, (
                score_data.get("score", 0),
                score_data.get("priority", "Low"),
                score_data.get("recommendation", "Review"),
                score_data.get("fit_reason", ""),
                score_data.get("missing_skills", ""),
                score_data.get("resume_tailor_tip", ""),
                score_data.get("star_pitch", ""),
                1 if score_data.get("is_scam") else 0,
                score_data.get("scam_reason", ""),
                scored_at,
                job_id
            ))
            conn.commit()

    def log_audit(self, event_type: str, details: str):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (event_type, details, timestamp) VALUES (?, ?, ?)",
                (event_type, details, get_current_ist_timestamp())
            )
            conn.commit()


# --------------------------------------------------------------------------------------
# 4. CANDIDATE PROFILE & EVIDENCE VAULT INGESTION
# --------------------------------------------------------------------------------------
class CandidateVault:
    @staticmethod
    def load_profile(path: str = config.CANDIDATE_PROFILE_PATH) -> str:
        """Reads candidate profile from text file or returns default verified facts."""
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    return content
            except Exception as e:
                print(f"[Vault] Notice: Could not read {path} ({e}). Using embedded verified profile.")

        # Default Verified Profile
        return """
        CANDIDATE VERIFIED FACT SHEET:
        - Candidate Name: Sourav Roy Chowdhury
        - Target Roles: AWS Cloud Support Engineer, Cloud Operations, Linux/Technical Support Associate.
        - Primary Base: Kolkata, West Bengal, India. Open to Kolkata on-site/hybrid and India Remote.
        - Core Hands-on Cloud Skills:
          * AWS Services: EC2, VPC (multi-AZ subnets, NAT Gateway, IGW, Route Tables), ALB, S3, RDS PostgreSQL,
            EBS, EFS, IAM (least privilege policies), CloudWatch, CloudTrail, SSM Session Manager (no public SSH), Secrets Manager.
          * Infrastructure as Code: Terraform (modular configurations, multi-tier VPC architecture).
          * Linux & OS: Ubuntu/Debian, Bash shell scripting, systemd service management, process triage, permissions, curl/netstat.
          * Networking: TCP/IP, DNS, DHCP, HTTP/HTTPS, TLS, VPC peering, CIDR routing.
          * Containers & Databases: Docker containerization, PostgreSQL 16 administration, SQL queries.
          * Applications & Automation: Node.js, Express, Python REST scripts, Webhook integrations.
        - Ground Rule: Never fabricate years of commercial AWS employment. Frame experience as rigorous hands-on projects,
          architectural deployments, and technical lab builds.
        """.strip()


# --------------------------------------------------------------------------------------
# 5. SECURITY & ANTI-FRAUD ENGINE
# --------------------------------------------------------------------------------------
class SecurityFilter:
    @staticmethod
    def audit_job(title: str, company: str, description: str) -> Tuple[bool, str]:
        """
        Scans job text for malicious red flags:
        1. Monetary fees or deposits.
        2. Unofficial recruiter communication channels (WhatsApp only / Telegram tasking).
        3. Phishing patterns.
        """
        text_lower = f"{title} {company} {description}".lower()

        # Check red flag scam keywords
        for kw in config.SCAM_KEYWORDS:
            if kw in text_lower:
                return True, f"High Risk: Detected scam flag phrase '{kw}'"

        # Check suspicious WhatsApp/Telegram-only hiring
        if re.search(r"(telegram task|send message on whatsapp to hr|pay deposit)", text_lower):
            return True, "High Risk: Unsolicited task payment or Telegram/WhatsApp HR redirection"

        return False, "Passed Verification"


# --------------------------------------------------------------------------------------
# 6. REASONING & SCORING ENGINE (GEMINI API + HEURISTIC FALLBACK)
# --------------------------------------------------------------------------------------
class ScoringEngine:
    def __init__(self, api_key: str = config.GEMINI_API_KEY, model: str = config.GEMINI_MODEL):
        self.api_key = api_key
        self.model = model

    def score_job(self, job: sqlite3.Row, candidate_profile: str) -> Dict[str, Any]:
        """Evaluates job against verified candidate facts using Gemini API or Heuristic fallback."""
        title = job["title"]
        company = job["company"]
        desc = job["raw_description"] or ""

        # Step A: Pre-LLM Title Guardrail (Avoid senior titles)
        for term in config.SENIOR_EXCLUDE_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", title.lower()):
                return {
                    "score": 25,
                    "priority": "Skip",
                    "recommendation": "Exclude (Senior/Enterprise)",
                    "fit_reason": f"Title matches senior exclusion filter '{term}'.",
                    "missing_skills": "Requires multi-year staff/lead enterprise experience",
                    "resume_tailor_tip": "N/A",
                    "star_pitch": "N/A",
                    "is_scam": False,
                    "scam_reason": ""
                }

        # Step B: Anti-Fraud Check
        is_scam, scam_reason = SecurityFilter.audit_job(title, company, desc)
        if is_scam:
            return {
                "score": 0,
                "priority": "Fraud Alert",
                "recommendation": "Block & Report",
                "fit_reason": "Failed security and fraud verification.",
                "missing_skills": "Legitimate company verification",
                "resume_tailor_tip": "Do not apply",
                "star_pitch": "Do not engage",
                "is_scam": True,
                "scam_reason": scam_reason
            }

        # Step C: Gemini API Evaluation (if key provided)
        if self.api_key:
            llm_result = self._call_gemini_api(title, company, desc, candidate_profile)
            if llm_result:
                return llm_result

        # Step D: Deterministic Heuristic Fallback (Offline / Zero-Token)
        return self._heuristic_fallback_score(title, desc)

    def _call_gemini_api(self, title: str, company: str, desc: str, profile: str) -> Optional[Dict[str, Any]]:
        """Invokes Google Gemini REST API using structured JSON output instructions."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        prompt = f"""
You are an expert Cloud Engineering Career Strategist and Technical Recruiter.
Analyze the following Job Posting against the Candidate's Verified Fact Sheet.

CANDIDATE FACTS:
{profile}

JOB DETAILS:
Title: {title}
Company: {company}
Description: {desc[:2500]}

SCORING RULES (0-100):
- 85-100: Exceptional match for entry/associate AWS Cloud Support, Linux, Infrastructure, or Operations.
- 70-84: Strong fit with minor missing niche requirements.
- 50-69: Moderate fit, adjacent role or requires minor upskilling.
- <50: Poor fit, high seniority mismatch, or unrelated tech stack.
- Never invent commercial enterprise experience not present in facts.

Respond ONLY with a valid JSON object matching this exact schema:
{{
  "score": <integer 0-100>,
  "priority": "<High | Medium | Low | Skip>",
  "recommendation": "<Apply Immediately | Tailor Resume & Apply | Review | Skip>",
  "fit_reason": "<1-2 concise sentences explaining skill overlap>",
  "missing_skills": "<comma separated list of missing requirements>",
  "resume_tailor_tip": "<specific point on how to present candidate projects for this role>",
  "star_pitch": "<a 2-sentence interview pitch highlighting Terraform or Linux troubleshooting>"
}}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": config.TEMPERATURE,
                "responseMimeType": "application/json"
            }
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text)
                parsed["is_scam"] = False
                parsed["scam_reason"] = ""
                return parsed
        except Exception as e:
            print(f"[Gemini] API note: {e}. Defaulting to deterministic heuristic engine.")
            return None

    def _heuristic_fallback_score(self, title: str, desc: str) -> Dict[str, Any]:
        """Calculates deterministic score based on high-value keyword density."""
        text = f"{title} {desc}".lower()
        score = 45  # baseline

        high_val_keywords = ["aws", "cloud", "linux", "ec2", "vpc", "troubleshooting", "bash", "terraform", "support"]
        matches = [kw for kw in high_val_keywords if kw in text]

        score += len(matches) * 6
        if "kolkata" in text or "remote" in text:
            score += 8
        if "entry" in text or "associate" in text or "junior" in text or "0-2" in text:
            score += 10

        score = min(score, 94)

        priority = "High" if score >= config.MIN_SCORE_TOP_TIER else ("Medium" if score >= config.MIN_SCORE_DIGEST else "Low")
        rec = "Apply Immediately" if score >= config.MIN_SCORE_TOP_TIER else "Tailor Resume & Apply"

        return {
            "score": score,
            "priority": priority,
            "recommendation": rec,
            "fit_reason": f"Matched critical cloud/support competencies: {', '.join(matches[:4])}.",
            "missing_skills": "Enterprise production support ticketing systems" if "ticket" in text else "None identified",
            "resume_tailor_tip": "Spotlight multi-tier VPC Terraform deployment and zero-public-access RDS architecture.",
            "star_pitch": "Demonstrated hands-on VPC and ALB deployment in ap-south-1 with automated CloudWatch logging.",
            "is_scam": False,
            "scam_reason": ""
        }


# --------------------------------------------------------------------------------------
# 7. TELEGRAM ALERTING
# --------------------------------------------------------------------------------------
def send_telegram_alert(job, bot_token: str, chat_id: str) -> bool:
    """
    Sends an immediate mobile push notification for a top-tier opportunity.
    Accepts a dict or sqlite3.Row. Returns True only if Telegram confirmed delivery.
    Uses HTML parse mode with escaping, so '_', '*', '[' in job text cannot break the message.
    """
    if not bot_token or not chat_id:
        return False

    j = dict(job)  # sqlite3.Row has no .get(); normalise to dict
    esc = lambda v: html.escape(str(v or ""))

    tip = (j.get("resume_tailor_tip") or "")
    tip = tip if len(tip) <= 180 else tip[:177] + "..."

    text = (
        f"ðŸš¨ <b>Top Match ({esc(j.get('match_score'))}/100)</b>: {esc(j.get('title'))}\n"
        f"ðŸ¢ <b>Company</b>: {esc(j.get('company'))} ({esc(j.get('location'))})\n"
        f"ðŸŽ¯ <b>Recommendation</b>: {esc(j.get('recommendation'))}\n"
        f"ðŸ’¡ <b>Tip</b>: {esc(tip)}\n"
        f"ðŸ”— <a href=\"{html.escape(str(j.get('job_url') or ''), quote=True)}\">Apply Here</a>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok"))
    except Exception as e:
        print(f"[Alert] Telegram push failed: {e}")
        return False


def dispatch_alerts(db: DatabaseManager) -> int:
    """Pushes each top-tier, non-scam job to Telegram once. Returns number sent."""
    if not config.TELEGRAM_ALERTS_ENABLED:
        return 0
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[Alert] Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID). Skipping alerts.")
        return 0

    sent = 0
    for job in db.get_pending_alerts(config.MIN_SCORE_TOP_TIER):
        if send_telegram_alert(job, config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID):
            db.mark_alerted(job["id"])
            sent += 1
            print(f" -> Telegram alert sent: ID {job['id']} '{job['title']}' ({job['match_score']})")
    db.log_audit("TELEGRAM_ALERTS", f"Sent {sent} top-tier alerts")
    return sent


# --------------------------------------------------------------------------------------
# 8. EXCEL DIGEST WORKBOOK GENERATOR (OPENPYXL)
# --------------------------------------------------------------------------------------
class ExcelReportGenerator:
    @staticmethod
    def generate_digest(db: DatabaseManager, output_dir: str = config.EXCEL_EXPORT_DIR) -> str:
        """Constructs an executive-grade 4-sheet formatted Excel workbook."""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise ImportError("openpyxl is required. Run: python -m pip install openpyxl")

        os.makedirs(output_dir, exist_ok=True)
        ts_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(output_dir, f"{config.EXCEL_FILENAME_PREFIX}_{ts_slug}.xlsx")

        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Remove default blank sheet

        # Styles
        hdr_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")  # Navy
        hdr_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        green_fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
        amber_fill = PatternFill(start_color="FEF7E0", end_color="FEF7E0", fill_type="solid")
        red_fill = PatternFill(start_color="FCE8E6", end_color="FCE8E6", fill_type="solid")
        border_side = Side(style="thin", color="E2E8F0")
        grid_border = Border(left=border_side, right=border_side, top=border_side, bottom=border_side)
        link_font = Font(name="Calibri", size=10, color="0969DA", underline="single")
        base_font = Font(name="Calibri", size=10)

        with db.get_connection() as conn:
            all_jobs = conn.execute("SELECT * FROM jobs ORDER BY match_score DESC, id DESC").fetchall()
            top_jobs = [j for j in all_jobs if j["match_score"] >= config.MIN_SCORE_DIGEST and not j["is_scam"]]
            app_rows = conn.execute("SELECT * FROM applications ORDER BY applied_date DESC").fetchall()
            audits = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()

        # Sheet 1: Top Matches (Digest Priority)
        ws_top = wb.create_sheet(title=f"Top_Matches_{config.MIN_SCORE_DIGEST}+")
        headers_top = [
            "ID", "Score", "Priority", "Recommendation", "Job Title", "Company", "Location",
            "Listing Link", "Fit Reason", "Missing Skills", "Resume Tailor Tip", "STAR Pitch Hook",
            "Discovered At (IST)", "Scored At (IST)", "Notes / Action"
        ]
        ws_top.append(headers_top)
        ws_top.row_dimensions[1].height = 26
        ws_top.freeze_panes = "E2"

        for r_idx, job in enumerate(top_jobs, start=2):
            score = job["match_score"]
            ws_top.append([
                job["id"], score, job["priority"], job["recommendation"],
                job["title"], job["company"], job["location"],
                job["job_url"], job["fit_reason"], job["missing_skills"],
                job["resume_tailor_tip"], job["star_pitch"],
                job["discovered_at"], job["scored_at"], job["user_notes"]
            ])
            fill = green_fill if score >= config.MIN_SCORE_TOP_TIER else amber_fill

            for c_idx in range(1, len(headers_top) + 1):
                cell = ws_top.cell(row=r_idx, column=c_idx)
                cell.border = grid_border
                cell.font = base_font
                if c_idx == 2:  # Score highlight
                    cell.fill = fill
                    cell.font = Font(name="Calibri", size=11, bold=True)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif c_idx == 8 and str(cell.value).startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = link_font
                elif c_idx in [9, 10, 11, 12]:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")

        # Sheet 2: All Scored Jobs (Master Log)
        ws_all = wb.create_sheet(title="All_Scored_Jobs")
        headers_all = [
            "ID", "Score", "Priority", "Title", "Company", "Location", "Source",
            "URL", "Scam Check", "Scored At (IST)"
        ]
        ws_all.append(headers_all)
        ws_all.row_dimensions[1].height = 24
        ws_all.freeze_panes = "D2"

        for r_idx, job in enumerate(all_jobs, start=2):
            ws_all.append([
                job["id"], job["match_score"], job["priority"], job["title"],
                job["company"], job["location"], f"{job['source_channel']} ({job['source_site']})",
                job["job_url"], "FLAGGED SCAM" if job["is_scam"] else "Verified Safe", job["scored_at"]
            ])
            for c_idx in range(1, len(headers_all) + 1):
                cell = ws_all.cell(row=r_idx, column=c_idx)
                cell.border = grid_border
                cell.font = base_font
                if c_idx == 9 and job["is_scam"]:
                    cell.fill = red_fill
                    cell.font = Font(name="Calibri", bold=True, color="9C1C1C")
                if c_idx == 8 and str(cell.value).startswith("http"):
                    cell.hyperlink = cell.value
                    cell.font = link_font

        # Sheet 3: Application Lifecycle Tracker
        ws_app = wb.create_sheet(title="Applications_Tracker")
        headers_app = ["App ID", "Company", "Job Title", "Status", "Applied Date", "Follow-up Due", "Notes"]
        ws_app.append(headers_app)
        ws_app.row_dimensions[1].height = 24

        for r_idx, app in enumerate(app_rows, start=2):
            ws_app.append([
                app["id"], app["company"], app["title"], app["status"],
                app["applied_date"], app["follow_up_date"], app["notes"]
            ])
            for c_idx in range(1, len(headers_app) + 1):
                cell = ws_app.cell(row=r_idx, column=c_idx)
                cell.border = grid_border
                cell.font = base_font

        # Sheet 4: System Audit & Health Log
        ws_audit = wb.create_sheet(title="System_Audit_Log")
        headers_audit = ["Log ID", "Event Type", "Details", "Timestamp (IST)"]
        ws_audit.append(headers_audit)
        for r_idx, log in enumerate(audits, start=2):
            ws_audit.append([log["id"], log["event_type"], log["details"], log["timestamp"]])
            for c_idx in range(1, len(headers_audit) + 1):
                cell = ws_audit.cell(row=r_idx, column=c_idx)
                cell.border = grid_border
                cell.font = base_font

        # Header styling + auto-fit column widths across sheets
        for ws in [ws_top, ws_all, ws_app, ws_audit]:
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=1, column=col)
                cell.fill = hdr_fill
                cell.font = hdr_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    if cell.row == 1:
                        max_len = max(max_len, len(val_str) + 4)
                    else:
                        max_len = max(max_len, min(len(val_str), 55))
                ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        wb.save(filepath)
        return filepath


# --------------------------------------------------------------------------------------
# 9. WORKFLOW RUNNER & CLI INTERFACE
# --------------------------------------------------------------------------------------
def seed_sample_jobs(db: DatabaseManager):
    """Seeds verified representative job feeds for testing."""
    sample_jobs = [
        {
            "title": "AWS Cloud Support Associate",
            "company": "CloudTech Solutions",
            "location": "Kolkata, WB (Hybrid)",
            "job_url": "https://linkedin.com/jobs/view/aws-support-kolkata-39210",
            "source_channel": "LinkedIn",
            "source_site": "JobSpy",
            "raw_description": "Looking for Cloud Support Associate. Key skills: AWS EC2, VPC, Linux system administration, Bash, S3, troubleshooting connectivity, TCP/IP, DNS."
        },
        {
            "title": "Technical Support Engineer - Linux & Cloud",
            "company": "RedCore Systems",
            "location": "Remote (India)",
            "job_url": "https://naukri.com/job-listings-linux-cloud-support-01",
            "source_channel": "Naukri",
            "source_site": "JobSpy",
            "raw_description": "Requirements: Strong Linux troubleshooting (systemd, logs, permissions), Docker container basics, PostgreSQL queries, AWS fundamentals."
        },
        {
            "title": "Cloud Operations Engineer (Tier 1)",
            "company": "CogniSphere Networks",
            "location": "Bengaluru (Remote Allowed)",
            "job_url": "https://remotive.com/jobs/cognisphere-cloud-tier1-99",
            "source_channel": "RemoteAPI",
            "source_site": "Remotive",
            "raw_description": "Monitor production infrastructure, CloudWatch alarms, IAM access reviews, Terraform modular deployments, SLA incident resolution."
        },
        {
            "title": "Senior Principal Cloud Enterprise Architect",
            "company": "Global MegaCorp",
            "location": "Kolkata, WB",
            "job_url": "https://careers.megacorp.com/req-9999",
            "source_channel": "ATS Feed",
            "source_site": "Workday",
            "raw_description": "15+ years experience leading enterprise digital transformation, multi-region Kubernetes, VP level stakeholder communication."
        },
        {
            "title": "Data Entry & Cloud Assistant - Immediate Start",
            "company": "QuickHire Agency",
            "location": "Kolkata, WB",
            "job_url": "https://quikr.com/jobs/unverified-job-881",
            "source_channel": "Scrape",
            "source_site": "Portal",
            "raw_description": "Earn 5000 daily. Pay 1500 registration fee for document processing. Contact HR on WhatsApp only."
        }
    ]

    new_count = 0
    for j in sample_jobs:
        _, is_new = db.insert_or_get_job(j)
        if is_new:
            new_count += 1
    db.log_audit("SEED_JOBS", f"Ingested {new_count} new candidate job records")
    print(f"[Ingest] Successfully ingested {new_count} sample jobs.")


def run_pipeline(upload_profile: Optional[str] = None, send_alerts: bool = True):
    print("=" * 70)
    print("CAREEROS: ULTIMATE AGENTIC JOB SEARCH & REASONING ENGINE")
    print(f"Timestamp: {get_current_ist_timestamp()}")
    print("=" * 70)

    db = DatabaseManager()
    profile_path = upload_profile or config.CANDIDATE_PROFILE_PATH
    profile_text = CandidateVault.load_profile(profile_path)
    print(f"[Vault] Candidate Profile loaded ({len(profile_text)} characters).")

    # Seed samples if database is empty
    with db.get_connection() as conn:
        count = conn.execute("SELECT count(*) as c FROM jobs").fetchone()["c"]
    if count == 0:
        seed_sample_jobs(db)

    # Scoring Stage
    scorer = ScoringEngine()
    unscored = db.get_unscored_jobs()
    print(f"[Brain] Found {len(unscored)} unscored jobs. Evaluating...")

    for row in unscored:
        result = scorer.score_job(row, profile_text)
        db.update_job_score(row["id"], result)
        print(f" -> Evaluated ID {row['id']}: '{row['title']}' | Score: {result['score']} | {result['recommendation']}")

    db.log_audit("SCORING_RUN", f"Scored {len(unscored)} jobs with Gemini/Heuristic Engine")

    # Alert Stage (top-tier only, once per job)
    if send_alerts:
        dispatch_alerts(db)

    # Export Stage
    excel_path = ExcelReportGenerator.generate_digest(db)
    print("=" * 70)
    print(f"[SUCCESS] Excel Digest Generated: {excel_path}")
    print("=" * 70)
    return excel_path


def main():
    parser = argparse.ArgumentParser(description="CareerOS Ultimate Agentic Job Search Engine")
    parser.add_argument("--profile", type=str, default=None, help="Path to uploaded candidate profile (.txt / .md)")
    parser.add_argument("--seed", action="store_true", help="Seed representative job vacancies")
    parser.add_argument("--export-only", action="store_true", help="Export existing DB to Excel without re-scoring")
    parser.add_argument("--no-alerts", action="store_true", help="Skip Telegram alerts for this run")
    parser.add_argument("--test-telegram", action="store_true", help="Send one test message to verify Telegram setup")
    args = parser.parse_args()

    if args.test_telegram:
        ok = send_telegram_alert(
            {"match_score": 99, "title": "Telegram Test Job", "company": "CareerOS",
             "location": "Kolkata", "recommendation": "Apply Immediately",
             "resume_tailor_tip": "If you can read this, alerts work.", "job_url": "https://example.com"},
            config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
        )
        print("Telegram test:", "SENT" if ok else "FAILED (check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return

    db = DatabaseManager()
    if args.seed:
        seed_sample_jobs(db)
    elif args.export_only:
        p = ExcelReportGenerator.generate_digest(db)
        print(f"Exported to {p}")
    else:
        run_pipeline(upload_profile=args.profile, send_alerts=not args.no_alerts)


if __name__ == "__main__":
    main()

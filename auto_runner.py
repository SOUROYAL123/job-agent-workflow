#!/usr/bin/env python3
"""
auto_runner.py - Zero-touch daily orchestrator for job_agent.py.
Handles Wi-Fi readiness after laptop wake, lockfile safety, 7-day DB backups,
log rotation, silent background execution, and failure alert emails.
"""

import argparse
import os
import smtplib
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
load_dotenv(BASE_DIR / ".env", override=True)

LOG_FILE = BASE_DIR / "run_log.txt"
LOCK_FILE = BASE_DIR / "agent.lock"
STAMP_FILE = BASE_DIR / "last_success.txt"
STATUS_FILE = BASE_DIR / "LAST_RUN_STATUS.txt"
BACKUP_DIR = BASE_DIR / "backups"

DB_PATH = BASE_DIR / os.getenv("DB_PATH", "jobs.db")
MIN_SCORE = int(os.getenv("MIN_EMAIL_MATCH_SCORE", "60"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "").strip()
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "").strip()
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "").strip() or EMAIL_ADDRESS
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

COOLDOWN_HOURS = 5          # Prevents duplicate scheduled runs after reboots
MAX_LOG_BYTES = 2_000_000   # Rotate run_log.txt at ~2 MB


def rotate_log() -> None:
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        old = BASE_DIR / "run_log.old.txt"
        if old.exists():
            old.unlink()
        LOG_FILE.rename(old)


def log_line(msg: str, silent: bool = False) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
        f.write(line + "\n")
    if not silent and sys.stdout is not None:
        try:
            print(line)
        except Exception:
            pass


def wait_for_internet(max_wait_sec: int = 180, silent: bool = False) -> bool:
    deadline = time.time() + max_wait_sec
    first = True
    while time.time() < deadline:
        for host, port in (("imap.gmail.com", 993), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((host, port), timeout=5):
                    return True
            except OSError:
                continue
        if first:
            log_line("Waiting for Wi-Fi / internet connection...", silent)
            first = False
        time.sleep(10)
    return False


def db_is_healthy(path: Path) -> bool:
    try:
        c = sqlite3.connect(path)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
        return ok
    except Exception:
        return False


def ensure_healthy_db(silent: bool = False) -> None:
    """If jobs.db is corrupt, keep the bad copy and restore the newest healthy backup."""
    if not DB_PATH.exists() or db_is_healthy(DB_PATH):
        return
    log_line("jobs.db FAILED integrity check; trying to restore from backups.", silent)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    DB_PATH.rename(DB_PATH.with_name(f"jobs_corrupt_{stamp}.db"))
    for b in sorted(BACKUP_DIR.glob("jobs_*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        if db_is_healthy(b):
            import shutil
            shutil.copy2(b, DB_PATH)
            log_line(f"Restored database from backups/{b.name}", silent)
            return
    log_line("No healthy backup found; a fresh database will be created.", silent)


def backup_database(silent: bool = False) -> None:
    if not DB_PATH.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    today_backup = BACKUP_DIR / f"jobs_{datetime.now():%Y-%m-%d}.db"
    if not today_backup.exists():
        try:
            src = sqlite3.connect(DB_PATH)
            dst = sqlite3.connect(today_backup)
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            log_line(f"Backed up database -> backups/{today_backup.name}", silent)
        except Exception as exc:
            log_line(f"DB backup warning: {exc}", silent)

    # Keep only the 7 newest daily backups
    backups = sorted(BACKUP_DIR.glob("jobs_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_db in backups[7:]:
        try:
            old_db.unlink()
        except OSError:
            pass


def write_status_summary(outcome: str) -> None:
    total = scored = unscored = top = 0
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            scored = conn.execute("SELECT COUNT(*) FROM jobs WHERE scored=1").fetchone()[0]
            unscored = conn.execute("SELECT COUNT(*) FROM jobs WHERE scored=0").fetchone()[0]
            top = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE scored=1 AND match_score>=?", (MIN_SCORE,)
            ).fetchone()[0]
            conn.close()
        except Exception:
            pass

    STATUS_FILE.write_text(
        f"Last Run       : {datetime.now():%Y-%m-%d %I:%M:%S %p}\n"
        f"Outcome        : {outcome}\n"
        f"Total Jobs     : {total}\n"
        f"Scored / Queue : {scored} scored | {unscored} waiting\n"
        f"Matches >= {MIN_SCORE}  : {top}\n",
        encoding="utf-8",
    )


def send_failure_alert(reason: str, tail_lines: list[str]) -> None:
    if not (EMAIL_ADDRESS and EMAIL_PASSWORD):
        return
    body = (
        f"Your automated Cloud Job Agent encountered an issue:\n\n"
        f"Reason: {reason}\n\n"
        f"Recent log lines:\n" + "\n".join(tail_lines[-20:])
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = "[Job Agent] Automation Attention Needed"
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as s:
            s.ehlo()
            s.starttls()
            s.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            s.sendmail(EMAIL_ADDRESS, [RECIPIENT_EMAIL], msg.as_string())
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scheduled", action="store_true", help="silent mode for Task Scheduler")
    args = ap.parse_args()
    silent = args.scheduled

    rotate_log()

    # Skip if a scheduled run already succeeded within COOLDOWN_HOURS
    if args.scheduled and STAMP_FILE.exists():
        try:
            last_dt = datetime.fromisoformat(STAMP_FILE.read_text(encoding="utf-8").strip())
            if datetime.now() - last_dt < timedelta(hours=COOLDOWN_HOURS):
                log_line("Scheduled run skipped (already ran within cooldown window).", silent)
                return 0
        except Exception:
            pass

    # Prevent overlapping runs
    if LOCK_FILE.exists():
        if time.time() - LOCK_FILE.stat().st_mtime < 3600:
            log_line("Another instance is already running; exiting.", silent)
            return 0
        LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        log_line("=== Starting Automated Cloud Job Pipeline ===", silent)
        if not wait_for_internet(silent=silent):
            log_line("No internet connection after 3 minutes; deferring to next window.", silent)
            write_status_summary("DEFERRED (Offline)")
            return 0

        ensure_healthy_db(silent=silent)
        backup_database(silent=silent)

        venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        py_exec = str(venv_py if venv_py.exists() else Path(sys.executable))

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        flags = subprocess.CREATE_NO_WINDOW if (os.name == "nt" and silent) else 0

        captured: list[str] = []
        proc = subprocess.Popen(
            [py_exec, "-u", str(BASE_DIR / "job_agent.py")],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=flags,
        )
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\r\n")
            captured.append(line)
            log_line(line, silent=silent)

        rc = proc.wait()
        joined = "\n".join(captured)

        if rc != 0 or "Gemini rejected GEMINI_API_KEY" in joined:
            reason = f"job_agent.py exited with code {rc}"
            log_line(f"=== Pipeline finished with issue: {reason} ===", silent)
            write_status_summary(f"ERROR ({reason})")
            send_failure_alert(reason, captured)
            return rc or 1

        STAMP_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")

        # Keep the networking kit current and email any follow-ups that are due (never contacts anyone).
        for extra in ("github_repo_sync.py", "networking_helper.py", "followup_reminder.py", "weekly_summary.py"):
            script = BASE_DIR / extra
            if not script.exists():
                continue
            try:
                res = subprocess.run([py_exec, "-u", str(script)], cwd=str(BASE_DIR), capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", env=env, timeout=300,
                                     creationflags=flags)
                for ln in (res.stdout or "").strip().splitlines()[-3:]:
                    log_line(ln, silent=silent)
                if res.returncode != 0:
                    log_line(f"{extra} exited with code {res.returncode}: {(res.stderr or '')[-200:]}", silent)
            except Exception as exc:
                log_line(f"{extra} skipped: {exc}", silent)
        if "QUOTA_EXHAUSTED" in joined:
            write_status_summary("PARTIAL (Gemini quota exhausted; unscored jobs wait for next run)")
            log_line("=== Pipeline finished PARTIAL: scoring quota exhausted ===", silent)
            return 0
        write_status_summary("SUCCESS")
        log_line("=== Automated Pipeline Complete ===", silent)
        return 0
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

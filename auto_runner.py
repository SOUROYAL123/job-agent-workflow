#!/usr/bin/env python3
"""
auto_runner.py
Daily Orchestrator for the Job Agent Pipeline.
Automatically executes:
  1. github_repo_sync.py (discovers new GitHub sources, deletes obsolete ones, updates packages)
  2. ats_finder.py (probes companies.txt for live ATS boards and removes dead slugs)
  3. job_agent.py (scrapes, scores with Gemini, updates Excel tracker, sends email digest)
"""

import datetime
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
BACKUP_DIR = BASE_DIR / "backups"
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "jobs.db")

LOG_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"auto_runner_{datetime.date.today().isoformat()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("auto_runner")


def wait_for_internet(max_attempts: int = 12, delay_seconds: int = 10) -> bool:
    for attempt in range(1, max_attempts + 1):
        try:
            requests.get("https://api.github.com", timeout=5)
            return True
        except Exception:
            logger.warning("Waiting for internet connection (%d/%d)...", attempt, max_attempts)
            time.sleep(delay_seconds)
    return False


def check_and_backup_database() -> bool:
    if not DB_PATH.exists():
        return True
    try:
        conn = sqlite3.connect(str(DB_PATH))
        res = conn.execute("PRAGMA integrity_check;").fetchone()
        conn.close()
        if not res or res[0] != "ok":
            logger.error("SQLite integrity check failed: %s", res)
            return False

        stamp = datetime.date.today().isoformat()
        backup_file = BACKUP_DIR / f"jobs_backup_{stamp}.db"
        if not backup_file.exists():
            shutil.copy2(DB_PATH, backup_file)
            logger.info("Created SQLite backup: %s", backup_file.name)

        # Keep only the 7 most recent database backups
        backups = sorted(BACKUP_DIR.glob("jobs_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old_bkp in backups[7:]:
            old_bkp.unlink(missing_ok=True)
        return True
    except Exception as exc:
        logger.error("Database check error: %s", exc)
        return False


def rotate_old_logs(keep_days: int = 14) -> None:
    cutoff = time.time() - (keep_days * 86400)
    for f in LOG_DIR.glob("*.log"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def run_pre_agent_pipeline_hooks() -> None:
    """Runs github_repo_sync.py and ats_finder.py before job_agent.py starts."""
    hooks = ["github_repo_sync.py", "ats_finder.py"]
    for script_name in hooks:
        script_path = BASE_DIR / script_name
        if not script_path.exists():
            continue
        logger.info("Running pre-flight hook: %s", script_name)
        res = subprocess.run([sys.executable, str(script_path)], cwd=BASE_DIR)
        if res.returncode != 0:
            logger.warning("Hook %s exited with code %d (continuing pipeline).", script_name, res.returncode)


def main() -> int:
    logger.info("=== Starting Automated Job Agent Daily Pipeline ===")
    rotate_old_logs()

    if not wait_for_internet():
        logger.error("No internet connectivity available. Aborting run.")
        return 1

    if not check_and_backup_database():
        logger.error("Database integrity check failed. Aborting run.")
        return 1

    # Step 1 & 2: Sync open-source GitHub repos, prune obsolete ones, and update ATS slugs
    run_pre_agent_pipeline_hooks()

    # Step 3: Run main job_agent.py pipeline
    agent_script = BASE_DIR / "job_agent.py"
    if not agent_script.exists():
        logger.error("job_agent.py not found in %s", BASE_DIR)
        return 1

    logger.info("Launching job_agent.py...")
    res = subprocess.run([sys.executable, str(agent_script)], cwd=BASE_DIR)
    if res.returncode == 0:
        logger.info("=== Daily Pipeline Completed Successfully ===")
    else:
        logger.error("job_agent.py exited with return code %d", res.returncode)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())

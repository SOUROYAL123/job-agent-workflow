#!/usr/bin/env python3
"""
github_repo_sync.py
Autonomous GitHub & Open-Source Discovery, Obsolescence Pruning, and Package Updater.
"""

import datetime
import importlib.metadata
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
REGISTRY_FILE = BASE_DIR / "github_sources_registry.json"
COMPANIES_FILE = BASE_DIR / "companies.txt"
DYNAMIC_FEEDS_FILE = BASE_DIR / "dynamic_feeds.json"
ENV_FILE = BASE_DIR / ".env"

MAX_STALE_DAYS_COMPANY_DIR = int(os.getenv("SYNC_MAX_STALE_DAYS_DIR", "365"))
MAX_STALE_DAYS_JOB_BOARD = int(os.getenv("SYNC_MAX_STALE_DAYS_JOBS", "120"))
MIN_GITHUB_STARS = int(os.getenv("SYNC_MIN_STARS", "15"))
SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
STRIKE_LIMIT = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("github_repo_sync")

SEED_REPOSITORIES: Dict[str, Dict[str, Any]] = {
    "abhagsain/WFH-Companies-India": {
        "category": "company_dir",
        "branch": "main",
        "readme_path": "README.md",
    },
    "poteto/hiring-without-whiteboards": {
        "category": "company_dir",
        "branch": "main",
        "readme_path": "README.md",
    },
    "remoteintech/remote-jobs": {
        "category": "company_dir",
        "branch": "main",
        "readme_path": "README.md",
    },
    "lukasz-madon/awesome-remote-job": {
        "category": "company_dir",
        "branch": "master",
        "readme_path": "README.md",
    },
    "SimplifyJobs/New-Grad-Positions": {
        "category": "job_board",
        "branch": "dev",
        "readme_path": "README.md",
    },
}

DISCOVERY_QUERIES: List[Tuple[str, str]] = [
    ("remote-companies OR remote-friendly-companies in:name,topics", "company_dir"),
    ("wfh companies india OR remote companies india in:name,description,topics", "company_dir"),
    ("hiring-without-whiteboards OR tech-companies-hiring in:name,topics", "company_dir"),
    ("remote-jobs cloud OR devops jobs remote in:name,description", "job_board"),
    ("tech-jobs-india OR remote-jobs-list in:name,description,topics", "job_board"),
]

TRACKED_PYPI_PACKAGES: Dict[str, str] = {
    "python-jobspy": "jobspy",
    "feedparser": "feedparser",
    "beautifulsoup4": "bs4",
}

NOISE_NAMES: Set[str] = {
    "company", "name", "website", "location", "roles", "notes", "status",
    "link", "apply", "career", "careers", "jobs", "remote", "hybrid", "india",
    "usa", "global", "worldwide", "github", "linkedin", "twitter", "readme",
    "contributing", "license", "table of contents", "back to top", "here",
    "source", "website link", "job board", "openings", "tech stack", "url",
}


def _github_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "auto-job-agent-repo-sync/3.0",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_iso_date(iso_str: Optional[str]) -> Optional[datetime.datetime]:
    if not iso_str:
        return None
    try:
        return datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def _has_obsolete_year(text: str) -> bool:
    current_year = datetime.datetime.now(datetime.timezone.utc).year
    years = [int(y) for y in re.findall(r"\b(202[0-9]|203[0-9])\b", text)]
    return bool(years and max(years) < current_year)


def load_registry() -> Dict[str, Any]:
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            data.setdefault("manual_companies", [])
            data.setdefault("repositories", {})
            data.setdefault("obsolete_blacklist", [])
            data.setdefault("dead_ats_companies", [])
            data.setdefault("feed_strikes", {})
            data.setdefault("dead_feeds", [])
            return data
        except Exception as exc:
            logger.warning("Rebuilding corrupt registry: %s", exc)

    initial_manual: List[str] = []
    if COMPANIES_FILE.exists():
        initial_manual = [
            line.strip()
            for line in COMPANIES_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    return {
        "last_sync_utc": None,
        "manual_companies": sorted(set(initial_manual)),
        "repositories": {},
        "obsolete_blacklist": [],
        "dead_ats_companies": [],
        "feed_strikes": {},
        "dead_feeds": [],
    }


def save_registry(registry: Dict[str, Any]) -> None:
    registry["last_sync_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")


def _run_verification_tests(import_name: str) -> bool:
    try:
        subprocess.run([sys.executable, "-c", f"import {import_name}"], check=True, timeout=30)
        test_file = BASE_DIR / "test_units.py"
        if test_file.exists():
            res = subprocess.run([sys.executable, str(test_file)], cwd=BASE_DIR, timeout=90)
            if res.returncode != 0:
                return False
        return True
    except Exception:
        return False


def sync_jobspy() -> bool:
    """Upgrades python-jobspy and tracked packages with automatic rollback if test_units.py fails."""
    updated_any = False
    for pypi_name, import_name in TRACKED_PYPI_PACKAGES.items():
        try:
            resp = requests.get(f"https://pypi.org/pypi/{pypi_name}/json", timeout=15)
            if resp.status_code != 200:
                continue
            latest_ver = resp.json().get("info", {}).get("version")
            if not latest_ver:
                continue

            try:
                old_ver = importlib.metadata.version(pypi_name)
            except importlib.metadata.PackageNotFoundError:
                old_ver = None

            if old_ver == latest_ver:
                continue

            logger.info("Upgrading %s: %s -> %s", pypi_name, old_ver, latest_ver)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", f"{pypi_name}=={latest_ver}", "--quiet"],
                check=True,
            )

            if _run_verification_tests(import_name):
                updated_any = True
            elif old_ver:
                logger.warning("Tests failed with %s==%s; rolling back to %s", pypi_name, latest_ver, old_ver)
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", f"{pypi_name}=={old_ver}", "--quiet"],
                    check=True,
                )
        except Exception as exc:
            logger.warning("Package sync skipped for %s: %s", pypi_name, exc)
    return updated_any


def check_career_ops(repo_full_name: str = "speedyapply/JobSpy", max_stale_days: int = 365) -> bool:
    """Verifies that a GitHub repository is active, unarchived, and recently updated."""
    url = f"https://api.github.com/repos/{repo_full_name}"
    try:
        resp = requests.get(url, headers=_github_headers(), timeout=15)
        if resp.status_code in (404, 410, 451):
            return False
        if resp.status_code != 200:
            return True

        data = resp.json()
        if data.get("archived") or data.get("disabled"):
            return False
        if _has_obsolete_year(data.get("name", "")) or _has_obsolete_year(data.get("description") or ""):
            return False

        pushed_at = _parse_iso_date(data.get("pushed_at"))
        if pushed_at:
            age_days = (datetime.datetime.now(datetime.timezone.utc) - pushed_at).days
            if age_days > max_stale_days:
                return False
        return True
    except Exception:
        return True


def prune_obsolete_sources(registry: Dict[str, Any]) -> List[str]:
    repos_reg: Dict[str, Any] = registry.get("repositories", {})
    blacklist: Set[str] = set(registry.get("obsolete_blacklist", []))
    pruned: List[str] = []

    for repo_name in list(repos_reg.keys()):
        meta = repos_reg[repo_name]
        max_days = (
            MAX_STALE_DAYS_JOB_BOARD
            if meta.get("category") == "job_board"
            else MAX_STALE_DAYS_COMPANY_DIR
        )
        if not check_career_ops(repo_name, max_stale_days=max_days):
            logger.info("Removing obsolete repository: %s", repo_name)
            pruned.append(repo_name)
            blacklist.add(repo_name)
            del repos_reg[repo_name]

    registry["obsolete_blacklist"] = sorted(blacklist)
    return pruned


def discover_github_sources(registry: Dict[str, Any]) -> List[str]:
    newly_added: List[str] = []
    blacklist: Set[str] = set(registry.get("obsolete_blacklist", []))
    repos_reg: Dict[str, Any] = registry.setdefault("repositories", {})

    for seed_repo, meta in SEED_REPOSITORIES.items():
        if seed_repo not in repos_reg and seed_repo not in blacklist:
            repos_reg[seed_repo] = {
                "category": meta["category"],
                "default_branch": meta["branch"],
                "readme_path": meta["readme_path"],
                "companies": [],
                "feeds": [],
                "discovered_via": "seed",
            }

    for query, category in DISCOVERY_QUERIES:
        max_days = MAX_STALE_DAYS_JOB_BOARD if category == "job_board" else MAX_STALE_DAYS_COMPANY_DIR
        cutoff_date = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_days)
        ).strftime("%Y-%m-%d")
        full_query = f"{query} pushed:>={cutoff_date} stars:>={MIN_GITHUB_STARS} archived:false"

        try:
            resp = requests.get(
                "https://api.github.com/search/repositories",
                headers=_github_headers(),
                params={"q": full_query, "sort": "updated", "order": "desc", "per_page": 8},
                timeout=20,
            )
            if resp.status_code != 200:
                continue

            for item in resp.json().get("items", []):
                full_name = item.get("full_name")
                if not full_name or full_name in blacklist or full_name in repos_reg:
                    continue
                if _has_obsolete_year(full_name) or _has_obsolete_year(item.get("description") or ""):
                    blacklist.add(full_name)
                    continue

                repos_reg[full_name] = {
                    "category": category,
                    "default_branch": item.get("default_branch", "main"),
                    "readme_path": "README.md",
                    "stars": item.get("stargazers_count", 0),
                    "pushed_at": item.get("pushed_at"),
                    "companies": [],
                    "feeds": [],
                    "discovered_via": query,
                }
                newly_added.append(full_name)
                logger.info("Discovered new GitHub source: %s", full_name)
        except Exception as exc:
            logger.warning("Search query '%s' failed: %s", query, exc)

    registry["obsolete_blacklist"] = sorted(blacklist)
    return newly_added


def _clean_company_name(raw_name: str) -> Optional[str]:
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", raw_name)
    cleaned = re.sub(r"[*_`~<>]", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) < 2 or len(cleaned) > 55:
        return None
    if cleaned.lower() in NOISE_NAMES:
        return None
    if cleaned.startswith(("http://", "https://", "#", "-", "|", "!")):
        return None
    if not re.search(r"[A-Za-z]", cleaned):
        return None
    return cleaned


def extract_markdown_companies(markdown_text: str) -> List[str]:
    companies: Set[str] = set()
    for line in markdown_text.splitlines():
        line_str = line.strip()
        if line_str.startswith("|") and line_str.count("|") >= 2:
            cells = [c.strip() for c in line_str.strip("|").split("|")]
            if cells and not re.match(r"^[-:]+$", cells[0]):
                candidate = _clean_company_name(cells[0])
                if candidate:
                    companies.add(candidate)

        bullet_match = re.match(r"^[-*+]\s+\[([^\]]+)\]\((https?://[^)]+)\)", line_str)
        if bullet_match:
            name_part, url_part = bullet_match.group(1), bullet_match.group(2)
            host = urlparse(url_part).netloc.lower()
            if not any(s in host for s in ("github.com", "shields.io", "badge", "twitter.com", "reddit.com")):
                candidate = _clean_company_name(name_part)
                if candidate:
                    companies.add(candidate)

    return sorted(companies)


def extract_feeds_from_markdown(markdown_text: str) -> List[str]:
    pattern = r"https?://[^\s)\"'>]+(?:\.rss|\.xml|/feed|/rss|jobs\.json|api/jobs)[^\s)\"'>]*"
    return sorted(set(re.findall(pattern, markdown_text, flags=re.IGNORECASE)))


def extract_wfh_india() -> List[str]:
    if not check_career_ops("abhagsain/WFH-Companies-India", max_stale_days=MAX_STALE_DAYS_COMPANY_DIR):
        return []
    raw_url = "https://raw.githubusercontent.com/abhagsain/WFH-Companies-India/main/README.md"
    try:
        resp = requests.get(raw_url, timeout=15)
        if resp.status_code == 200:
            return extract_markdown_companies(resp.text)
    except Exception:
        pass
    return []


def sync_repository_contents(registry: Dict[str, Any]) -> None:
    for repo_name, meta in list(registry.get("repositories", {}).items()):
        branch = meta.get("default_branch", "main")
        readme_path = meta.get("readme_path", "README.md")
        raw_urls = [
            f"https://raw.githubusercontent.com/{repo_name}/{branch}/{readme_path}",
            f"https://raw.githubusercontent.com/{repo_name}/main/README.md",
            f"https://raw.githubusercontent.com/{repo_name}/master/README.md",
        ]
        content = None
        for url in dict.fromkeys(raw_urls):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200 and resp.text:
                    content = resp.text
                    break
            except Exception:
                continue

        if not content:
            continue

        extracted_companies = extract_markdown_companies(content)
        extracted_feeds = extract_feeds_from_markdown(content)
        if extracted_companies:
            meta["companies"] = extracted_companies[:500]
        if extracted_feeds:
            meta["feeds"] = extracted_feeds[:100]
        meta["last_fetched_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()


def validate_and_prune_feeds(registry: Dict[str, Any]) -> List[str]:
    feed_strikes: Dict[str, int] = registry.setdefault("feed_strikes", {})
    dead_feeds: Set[str] = set(registry.setdefault("dead_feeds", []))

    all_discovered: Set[str] = set()
    for meta in registry.get("repositories", {}).values():
        all_discovered.update(meta.get("feeds", []))

    healthy_feeds: List[str] = []
    for url in sorted(all_discovered):
        if url in dead_feeds:
            continue
        try:
            resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            body = resp.text.lstrip()[:200].lower()
            is_valid = resp.status_code == 200 and (
                body.startswith(("<?xml", "<rss", "<feed", "{", "["))
                or "<item>" in body
                or "<entry>" in body
            )
        except Exception:
            is_valid = False

        if is_valid:
            feed_strikes[url] = 0
            healthy_feeds.append(url)
        else:
            feed_strikes[url] = feed_strikes.get(url, 0) + 1
            if feed_strikes[url] >= STRIKE_LIMIT:
                dead_feeds.add(url)

    registry["dead_feeds"] = sorted(dead_feeds)
    return healthy_feeds


def update_companies(
    new_companies: Optional[List[str]] = None,
    registry: Optional[Dict[str, Any]] = None,
    healthy_feeds: Optional[List[str]] = None,
) -> int:
    own_registry = registry is None
    if own_registry:
        registry = load_registry()

    dead_companies: Set[str] = set(registry.get("dead_ats_companies", []))
    active_companies: Set[str] = set(registry.get("manual_companies", []))

    if new_companies:
        active_companies.update(c.strip() for c in new_companies if c.strip())

    for meta in registry.get("repositories", {}).values():
        for comp in meta.get("companies", []):
            if comp not in dead_companies:
                active_companies.add(comp)

    sorted_companies = sorted(active_companies, key=lambda s: s.lower())
    COMPANIES_FILE.write_text("\n".join(sorted_companies) + "\n", encoding="utf-8")

    if healthy_feeds is None:
        dead_feeds = set(registry.get("dead_feeds", []))
        healthy_feeds = sorted({
            f for meta in registry.get("repositories", {}).values()
            for f in meta.get("feeds", [])
            if f not in dead_feeds
        })

    feeds_payload = {
        "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "active_repositories": list(registry.get("repositories", {}).keys()),
        "feeds": healthy_feeds,
    }
    DYNAMIC_FEEDS_FILE.write_text(json.dumps(feeds_payload, indent=2), encoding="utf-8")

    if own_registry:
        save_registry(registry)

    logger.info("Saved %d active companies and %d healthy feeds.", len(sorted_companies), len(healthy_feeds))
    return len(sorted_companies)


def enable_remote_feeds() -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text("ENABLE_REMOTE_FEEDS=true\n", encoding="utf-8")
        return
    content = ENV_FILE.read_text(encoding="utf-8")
    if "ENABLE_REMOTE_FEEDS=" in content:
        updated = re.sub(r"^ENABLE_REMOTE_FEEDS=.*$", "ENABLE_REMOTE_FEEDS=true", content, flags=re.MULTILINE)
        if updated != content:
            ENV_FILE.write_text(updated, encoding="utf-8")
    else:
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write("\nENABLE_REMOTE_FEEDS=true\n")


def sync_if_due() -> bool:
    registry = load_registry()
    last_sync = _parse_iso_date(registry.get("last_sync_utc"))
    if last_sync:
        elapsed_hours = (datetime.datetime.now(datetime.timezone.utc) - last_sync).total_seconds() / 3600.0
        if elapsed_hours < SYNC_INTERVAL_HOURS:
            return False
    main()
    return True


def main() -> None:
    logger.info("Starting autonomous GitHub & open-source sync...")
    registry = load_registry()
    sync_jobspy()
    prune_obsolete_sources(registry)
    discover_github_sources(registry)
    sync_repository_contents(registry)
    healthy_feeds = validate_and_prune_feeds(registry)
    update_companies(registry=registry, healthy_feeds=healthy_feeds)
    enable_remote_feeds()
    save_registry(registry)
    logger.info("Autonomous GitHub sync complete.")


if __name__ == "__main__":
    main()

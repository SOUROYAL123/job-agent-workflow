#!/usr/bin/env python3
"""
remote_feeds.py
Ingests worldwide and India-friendly remote tech roles from built-in APIs
(RemoteOK, Himalayas, Arbeitnow, Hacker News) PLUS all dynamic open-source
RSS/Atom/JSON feeds discovered by github_repo_sync.py in dynamic_feeds.json.
"""

import datetime
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

BASE_DIR = Path(__file__).resolve().parent
DYNAMIC_FEEDS_FILE = BASE_DIR / "dynamic_feeds.json"

logger = logging.getLogger("remote_feeds")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, application/xml, text/xml, */*",
}

TARGET_ROLE_RE = re.compile(
    r"\b(cloud|aws|devops|sre|site reliability|platform|infrastructure|support|"
    r"implementation|linux|sysadmin|systems|backend|node|python|terraform|docker|"
    r"kubernetes|architect|solutions|engineer|developer)\b",
    re.IGNORECASE,
)

RESTRICTED_GEO_RE = re.compile(
    r"\b(us only|usa only|united states only|u\.s\. only|uk only|eu only|"
    r"europe only|canada only|must reside in the us|authorized to work in the us)\b",
    re.IGNORECASE,
)


def _is_relevant_and_eligible(title: str, location: str, description: str, senior_re: Any = None) -> bool:
    if not title or not TARGET_ROLE_RE.search(title):
        return False
    if senior_re is not None and senior_re.search(title):
        return False
    combined_geo = f"{location} {description[:600]}"
    if RESTRICTED_GEO_RE.search(combined_geo):
        return False
    return True


def fetch_remoteok() -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    try:
        resp = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return jobs
        data = resp.json()
        for item in data[1:] if isinstance(data, list) and len(data) > 1 else []:
            title = str(item.get("position") or "").strip()
            company = str(item.get("company") or "").strip()
            url = str(item.get("url") or item.get("apply_url") or "").strip()
            if not title or not url:
                continue
            jobs.append({
                "title": title,
                "company": company or "RemoteOK Employer",
                "location": str(item.get("location") or "Remote Worldwide"),
                "description": str(item.get("description") or ""),
                "job_url": url,
                "date_posted": str(item.get("date") or "")[:10],
                "source_site": "remoteok",
            })
    except Exception as exc:
        logger.warning("RemoteOK feed error: %s", exc)
    return jobs


def fetch_himalayas() -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    try:
        resp = requests.get("https://himalayas.app/jobs/api?limit=50", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return jobs
        for item in resp.json().get("jobs", []):
            title = str(item.get("title") or "").strip()
            company = str(item.get("companyName") or "").strip()
            url = str(item.get("applicationLink") or item.get("guid") or "").strip()
            locs = item.get("locationRestrictions") or []
            loc_str = ", ".join(locs) if isinstance(locs, list) and locs else "Remote Worldwide"
            if not title or not url:
                continue
            jobs.append({
                "title": title,
                "company": company or "Himalayas Employer",
                "location": loc_str,
                "description": str(item.get("description") or ""),
                "job_url": url,
                "date_posted": datetime.date.today().isoformat(),
                "source_site": "himalayas",
            })
    except Exception as exc:
        logger.warning("Himalayas feed error: %s", exc)
    return jobs


def fetch_arbeitnow() -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    try:
        resp = requests.get("https://www.arbeitnow.com/api/job-board-api", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return jobs
        for item in resp.json().get("data", []):
            if not item.get("remote", False):
                continue
            title = str(item.get("title") or "").strip()
            company = str(item.get("company_name") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            jobs.append({
                "title": title,
                "company": company or "Arbeitnow Employer",
                "location": str(item.get("location") or "Remote"),
                "description": str(item.get("description") or ""),
                "job_url": url,
                "date_posted": datetime.date.today().isoformat(),
                "source_site": "arbeitnow",
            })
    except Exception as exc:
        logger.warning("Arbeitnow feed error: %s", exc)
    return jobs


def fetch_hackernews() -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    try:
        ids_resp = requests.get("https://hacker-news.firebaseio.com/v0/jobstories.json", timeout=10)
        if ids_resp.status_code != 200:
            return jobs
        story_ids = (ids_resp.json() or [])[:25]
        for sid in story_ids:
            item_resp = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=6)
            if item_resp.status_code != 200:
                continue
            item = item_resp.json() or {}
            raw_title = str(item.get("title") or "").strip()
            url = str(item.get("url") or f"https://news.ycombinator.com/item?id={sid}").strip()
            if not raw_title:
                continue
            parts = re.split(r"\s+is\s+hiring\s+|\s+hiring\s+", raw_title, flags=re.IGNORECASE)
            company = parts[0].strip() if len(parts) > 1 else "YC Startup"
            jobs.append({
                "title": raw_title,
                "company": company[:60],
                "location": "Remote / Global",
                "description": str(item.get("text") or raw_title),
                "job_url": url,
                "date_posted": datetime.date.today().isoformat(),
                "source_site": "hackernews",
            })
    except Exception as exc:
        logger.warning("HackerNews feed error: %s", exc)
    return jobs


def fetch_dynamic_open_source_feeds() -> List[Dict[str, Any]]:
    """Automatically ingests RSS, Atom, and JSON job feeds discovered by github_repo_sync.py."""
    jobs: List[Dict[str, Any]] = []
    if not DYNAMIC_FEEDS_FILE.exists():
        return jobs
    try:
        payload = json.loads(DYNAMIC_FEEDS_FILE.read_text(encoding="utf-8"))
        feed_urls = payload.get("feeds", [])
    except Exception:
        return jobs

    for feed_url in feed_urls:
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            text = resp.text.lstrip()
            # JSON feed
            if text.startswith(("{", "[")):
                data = resp.json()
                items = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
                if isinstance(items, list):
                    for item in items[:50]:
                        if not isinstance(item, dict):
                            continue
                        title = str(item.get("title") or item.get("position") or "").strip()
                        url = str(item.get("url") or item.get("link") or item.get("apply_url") or "").strip()
                        if title and url:
                            jobs.append({
                                "title": title,
                                "company": str(item.get("company") or item.get("company_name") or "OpenSource Feed"),
                                "location": str(item.get("location") or "Remote"),
                                "description": str(item.get("description") or ""),
                                "job_url": url,
                                "date_posted": datetime.date.today().isoformat(),
                                "source_site": "opensource_json_feed",
                            })
            # XML / RSS / Atom feed
            elif text.startswith(("<?xml", "<rss", "<feed")):
                root = ET.fromstring(resp.content)
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1].lower()
                    if tag in ("item", "entry"):
                        title_el = elem.find("title") or elem.find("{*}title")
                        link_el = elem.find("link") or elem.find("{*}link")
                        desc_el = (
                            elem.find("description")
                            or elem.find("{*}description")
                            or elem.find("{*}summary")
                        )
                        title = (title_el.text or "").strip() if title_el is not None else ""
                        url = ""
                        if link_el is not None:
                            url = (link_el.text or link_el.attrib.get("href") or "").strip()
                        desc = (desc_el.text or "").strip() if desc_el is not None else ""
                        if title and url:
                            jobs.append({
                                "title": title,
                                "company": "OpenSource RSS Feed",
                                "location": "Remote",
                                "description": desc,
                                "job_url": url,
                                "date_posted": datetime.date.today().isoformat(),
                                "source_site": "opensource_rss_feed",
                            })
        except Exception as exc:
            logger.debug("Dynamic feed skipped (%s): %s", feed_url, exc)
    return jobs


def run(
    db_path: str,
    get_conn: Callable,
    insert_job: Callable,
    job_hash: Callable,
    senior_re: Any = None,
    fetchers: Optional[List[Callable[[], List[Dict[str, Any]]]]] = None,
) -> int:
    """Executes all remote feed fetchers and inserts eligible roles into the SQLite database."""
    if fetchers is None:
        fetchers = [
            fetch_remoteok,
            fetch_himalayas,
            fetch_arbeitnow,
            fetch_hackernews,
            fetch_dynamic_open_source_feeds,
        ]

    inserted_count = 0
    conn = get_conn(db_path)
    try:
        for fetcher in fetchers:
            try:
                items = fetcher()
            except Exception as exc:
                logger.warning("Fetcher %s failed: %s", getattr(fetcher, "__name__", "unknown"), exc)
                continue

            for item in items:
                title = item.get("title", "")
                company = item.get("company", "Remote Employer")
                location = item.get("location", "Remote")
                description = item.get("description", "")
                job_url = item.get("job_url", "")

                if not _is_relevant_and_eligible(title, location, description, senior_re=senior_re):
                    continue

                j_hash = job_hash(job_url, title, company)
                row = {
                    "job_hash": j_hash,
                    "title": title,
                    "company": company,
                    "location": location,
                    "experience": "",
                    "job_type": "Full-time",
                    "is_remote": 1,
                    "date_posted": item.get("date_posted") or datetime.date.today().isoformat(),
                    "description": description[:5000],
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "company_url": "",
                    "source_channel": "remote_feeds",
                    "source_site": item.get("source_site", "remote_feed"),
                    "came_from_email": 0,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                try:
                    if insert_job(conn, row):
                        inserted_count += 1
                except TypeError:
                    # Fallback if insert_job signature expects (conn, row_dict) vs cursor
                    insert_job(conn, row)
                    inserted_count += 1
        conn.commit()
    finally:
        conn.close()

    logger.info("Remote feeds stage inserted %d new eligible jobs.", inserted_count)
    return inserted_count

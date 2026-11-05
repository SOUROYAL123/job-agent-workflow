#!/usr/bin/env python3
"""
ats_finder.py
Probes Greenhouse, Lever, and Ashby job boards for companies in companies.txt,
automatically updates ATS_GREENHOUSE, ATS_LEVER, and ATS_ASHBY in .env,
and prunes dead/obsolete company slugs.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = Path(__file__).resolve().parent
COMPANIES_FILE = BASE_DIR / "companies.txt"
ENV_FILE = BASE_DIR / ".env"
REGISTRY_FILE = BASE_DIR / "github_sources_registry.json"

MAX_PROBES_PER_RUN = int(os.getenv("ATS_MAX_PROBES_PER_RUN", "60"))
STRIKE_LIMIT = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ats_finder")

DEFAULT_COMPANIES: List[str] = [
    "canonical", "gitlab", "automattic", "hashicorp", "cloudflare",
    "datadog", "grafanalabs", "postman", "razorpay", "browserstack",
    "chargebee", "freshworks", "zerodha", "meesho", "cred",
    "supabase", "vercel", "render", "tailscale", "fly",
]


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def check_greenhouse(slug: str) -> bool:
    if not slug:
        return False
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = requests.get(url, timeout=6)
        return r.status_code == 200 and "jobs" in r.json()
    except Exception:
        return False


def check_lever(slug: str) -> bool:
    if not slug:
        return False
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = requests.get(url, timeout=6)
        return r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        return False


def check_ashby(slug: str) -> bool:
    if not slug:
        return False
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = requests.get(url, timeout=6)
        return r.status_code == 200 and "jobs" in r.json()
    except Exception:
        return False


def probe_company(company_name: str) -> Tuple[str, Optional[str]]:
    """Returns (slug, provider) where provider is 'greenhouse', 'lever', 'ashby', or None."""
    slug = _slugify(company_name)
    if not slug or len(slug) < 2:
        return slug, None
    if check_greenhouse(slug):
        return slug, "greenhouse"
    if check_lever(slug):
        return slug, "lever"
    if check_ashby(slug):
        return slug, "ashby"
    return slug, None


def _load_env_slugs(key: str) -> Set[str]:
    raw = os.getenv(key, "")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _set_env_variable(key: str, value: str) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    content = ENV_FILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(content):
        updated = pattern.sub(f"{key}={value}", content)
        ENV_FILE.write_text(updated, encoding="utf-8")
    else:
        with ENV_FILE.open("a", encoding="utf-8") as f:
            f.write(f"\n{key}={value}\n")


def main() -> None:
    logger.info("Running ATS board discovery and dead-slug pruning...")
    registry: Dict = {}
    if REGISTRY_FILE.exists():
        try:
            registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            registry = {}

    ats_strikes: Dict[str, int] = registry.setdefault("ats_strikes", {})
    dead_ats: Set[str] = set(registry.setdefault("dead_ats_companies", []))
    verified_ats: Dict[str, str] = registry.setdefault("verified_ats_slugs", {})

    gh_slugs = _load_env_slugs("ATS_GREENHOUSE")
    lever_slugs = _load_env_slugs("ATS_LEVER")
    ashby_slugs = _load_env_slugs("ATS_ASHBY")

    # 1. Verify currently configured slugs and prune any obsolete/dead ones
    for slug in list(gh_slugs):
        if not check_greenhouse(slug):
            ats_strikes[slug] = ats_strikes.get(slug, 0) + 1
            if ats_strikes[slug] >= STRIKE_LIMIT:
                logger.info("Pruning obsolete Greenhouse slug: %s", slug)
                gh_slugs.discard(slug)
                dead_ats.add(slug)
        else:
            ats_strikes[slug] = 0

    for slug in list(lever_slugs):
        if not check_lever(slug):
            ats_strikes[slug] = ats_strikes.get(slug, 0) + 1
            if ats_strikes[slug] >= STRIKE_LIMIT:
                logger.info("Pruning obsolete Lever slug: %s", slug)
                lever_slugs.discard(slug)
                dead_ats.add(slug)
        else:
            ats_strikes[slug] = 0

    for slug in list(ashby_slugs):
        if not check_ashby(slug):
            ats_strikes[slug] = ats_strikes.get(slug, 0) + 1
            if ats_strikes[slug] >= STRIKE_LIMIT:
                logger.info("Pruning obsolete Ashby slug: %s", slug)
                ashby_slugs.discard(slug)
                dead_ats.add(slug)
        else:
            ats_strikes[slug] = 0

    # 2. Load candidate companies from DEFAULT_COMPANIES + companies.txt
    candidates: List[str] = list(DEFAULT_COMPANIES)
    if COMPANIES_FILE.exists():
        for line in COMPANIES_FILE.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                candidates.append(clean)

    already_known = gh_slugs | lever_slugs | ashby_slugs | dead_ats | set(verified_ats.keys())
    to_probe = [c for c in dict.fromkeys(candidates) if _slugify(c) not in already_known][:MAX_PROBES_PER_RUN]

    if to_probe:
        logger.info("Probing %d candidate companies across Greenhouse, Lever, and Ashby...", len(to_probe))
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(probe_company, comp): comp for comp in to_probe}
            for fut in as_completed(futures):
                comp = futures[fut]
                try:
                    slug, provider = fut.result()
                    if provider == "greenhouse":
                        gh_slugs.add(slug)
                        verified_ats[slug] = "greenhouse"
                        logger.info("Discovered live Greenhouse board: %s", slug)
                    elif provider == "lever":
                        lever_slugs.add(slug)
                        verified_ats[slug] = "lever"
                        logger.info("Discovered live Lever board: %s", slug)
                    elif provider == "ashby":
                        ashby_slugs.add(slug)
                        verified_ats[slug] = "ashby"
                        logger.info("Discovered live Ashby board: %s", slug)
                    else:
                        ats_strikes[comp] = ats_strikes.get(comp, 0) + 1
                        if ats_strikes[comp] >= STRIKE_LIMIT:
                            dead_ats.add(comp)
                except Exception:
                    pass

    # 3. Write updated live slugs back to .env for job_agent.py
    if gh_slugs:
        _set_env_variable("ATS_GREENHOUSE", ",".join(sorted(gh_slugs)))
    if lever_slugs:
        _set_env_variable("ATS_LEVER", ",".join(sorted(lever_slugs)))
    if ashby_slugs:
        _set_env_variable("ATS_ASHBY", ",".join(sorted(ashby_slugs)))

    registry["dead_ats_companies"] = sorted(dead_ats)
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    logger.info(
        "ATS sync complete (Greenhouse: %d, Lever: %d, Ashby: %d).",
        len(gh_slugs),
        len(lever_slugs),
        len(ashby_slugs),
    )


if __name__ == "__main__":
    main()

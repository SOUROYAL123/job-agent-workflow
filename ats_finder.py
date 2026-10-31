"""
ats_finder.py - finds which companies publish a public Greenhouse, Lever, or Ashby job feed,
so the agent can read their openings directly. Uses only the public feeds your job_agent.py uses.

Run:   python ats_finder.py            (prints the lines)
       python ats_finder.py --apply    (also writes them into .env, keeping a backup)
       python ats_finder.py --weekly   (skips if it already ran in the last 7 days; implies --apply;
                                        used by START_HERE.bat)
Edit:  put extra company names, one per line, in companies.txt (lines starting with # are ignored).
Output: prints the exact ATS_GREENHOUSE=, ATS_LEVER=, and ATS_ASHBY= lines to paste into .env, and
saves them to ats_found.txt. Existing slugs already in your .env are kept in the printed lines.
A company that is not found simply uses another system (Workday, Zoho Recruit, its own site):
check its careers page by hand every week or two.
Companies that could not be checked (rate limit, network error) are listed separately; re-run later.
"""
import os
import re
import sys
import time
from datetime import date

# Same SSL setup as job_agent.py, so corporate / Windows certificate stores work here too.
# Must run before requests is imported.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except Exception:
    pass

UA = {"User-Agent": "personal-job-agent/1.0"}
PAUSE = 0.6  # seconds between requests, to stay polite
RETRY_CODES = (429, 500, 502, 503, 504)

# Starter list: edit freely. Mix of Indian cloud/managed-service firms, Indian SaaS, and global cloud/SaaS
# companies that hire remote support engineers. Nothing here claims they use Greenhouse, Lever, or Ashby.
DEFAULT_COMPANIES = [
    "Cloud4C", "Minfy", "CloudThat", "Searce", "Rapyder", "Rackspace",
    "Freshworks", "Postman", "BrowserStack", "Razorpay", "Chargebee", "Whatfix", "Darwinbox", "Sprinto",
    "Hasura", "CleverTap", "MoEngage", "Wingify", "Uniphore", "LeadSquared", "Mindtickle", "Zeta",
    "Innovaccer", "Gupshup", "Exotel", "Kissflow", "Zluri", "Atlan",
    "DigitalOcean", "Cloudflare", "Datadog", "Elastic", "GitLab", "Fastly", "Twilio", "MongoDB",
    "Snowflake", "Confluent", "Okta", "PagerDuty", "New Relic", "Nutanix", "Sumo Logic",
    "Supabase", "Render", "PostHog", "Linear", "Vanta", "Retool", "Deel",
]

# "operations" was dropped: it matched sales/finance/people operations. "cloud", "infrastructure",
# and "noc" already catch Cloud Operations, Infrastructure Operations, and NOC roles.
ROLE_WORDS = (
    "aws", "cloud", "support", "implementation", "devops", "sre", "noc",
    "infrastructure", "onboarding", "platform", "reliability",
)
INDIA_PLACES = (
    "india", "bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "gurgaon", "gurugram",
    "noida", "chennai", "kolkata",
)
REMOTE_WORDS = ("remote", "apac", "anywhere")
# A "remote" role that names one of these regions (and no Indian place) is not counted as relevant.
NON_INDIA_HINTS = (
    "us", "usa", "united states", "canada", "uk", "united kingdom", "emea", "europe",
    "latam", "americas", "north america",
)
SUFFIXES = (
    "pvt", "ltd", "private", "limited", "inc", "llc", "technologies", "technology", "solutions",
    "systems", "software", "labs", "services",
)


def _word_re(words):
    """Whole-word matcher, so 'india' does not match 'Indiana' and 'sre' does not match 'presales'."""
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.I)


ROLE_RE = _word_re(ROLE_WORDS)
INDIA_RE = _word_re(INDIA_PLACES)
REMOTE_RE = _word_re(REMOTE_WORDS)
NON_INDIA_RE = _word_re(NON_INDIA_HINTS)


def slug_candidates(name: str):
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    core = [w for w in words if w not in SUFFIXES] or words
    cands = ["".join(words), "".join(core), "-".join(core), "-".join(words)]
    # First word alone is only a safe guess for one-word names. For "New Relic" it would try "new",
    # which can belong to a different company's board.
    if len(core) == 1:
        cands.append(core[0])
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def relevant(title: str, loc: str) -> bool:
    title, loc = title or "", loc or ""
    if not ROLE_RE.search(title):
        return False
    if INDIA_RE.search(loc):
        return True
    return bool(REMOTE_RE.search(loc)) and not NON_INDIA_RE.search(loc)


class CheckFailed(Exception):
    """The feed could not be read (throttled or server error), so 'not found' would be a guess."""


STATS = {"ok": 0, "fail": 0}


def fetch(url):
    """GET with a short retry on 429/5xx and on network errors. Raises on a final network error."""
    r = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=20)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code in RETRY_CODES and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        break
    return r


def get_json(url):
    """Parsed JSON on 200, None for 'no such board', CheckFailed when throttled or broken."""
    r = fetch(url)
    if r.status_code in RETRY_CODES:
        raise CheckFailed(f"HTTP {r.status_code}")
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def check_greenhouse(slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if not isinstance(data, dict):
        return None
    jobs = data.get("jobs", [])
    return len(jobs), sum(relevant(j.get("title", ""), (j.get("location") or {}).get("name", "")) for j in jobs)


def check_lever(slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(data, list):
        return None
    return len(data), sum(relevant(j.get("text", ""), (j.get("categories") or {}).get("location", "") or "") for j in data)


def check_ashby(slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if not isinstance(data, dict) or "jobs" not in data:
        return None
    jobs = [j for j in data.get("jobs", []) if j.get("isListed", True)]
    rel_count = 0
    for j in jobs:
        sec_locs = [
            loc_obj.get("location", "")
            for loc_obj in (j.get("secondaryLocations") or [])
            if isinstance(loc_obj, dict) and loc_obj.get("location")
        ]
        primary_loc = j.get("location") or ""
        loc = ", ".join(filter(None, [primary_loc, *sec_locs]))
        if j.get("isRemote") and "remote" not in loc.lower():
            loc = f"{loc} (Remote)".strip()
        if relevant(j.get("title", ""), loc):
            rel_count += 1
    return len(jobs), rel_count


SYSTEMS = (
    ("greenhouse", check_greenhouse),
    ("lever", check_lever),
    ("ashby", check_ashby),
)


def load_companies():
    names = list(DEFAULT_COMPANIES)
    if os.path.exists("companies.txt"):
        with open("companies.txt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    names.append(line)
    seen, out = set(), []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def existing(var):
    return [s.strip() for s in os.getenv(var, "").split(",") if s.strip()]


def apply_to_env(lines, path=".env"):
    """Replace or append the ATS_ lines in .env, keeping a backup and the file's line endings."""
    if not os.path.exists(path):
        print("[apply] .env not found; nothing written.")
        return False
    with open(path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    with open(path + ".bak3", "w", encoding="utf-8", newline="") as fh:
        fh.write(raw)
    out = raw.splitlines()
    for new in lines:
        key = new.split("=", 1)[0]
        for i, old in enumerate(out):
            if re.match(rf"^\s*{key}\s*=", old):
                out[i] = new
                break
        else:
            out.append(new)
    # Write to a temp file, then swap it in, so a crash mid-write cannot leave a half-written .env.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(eol.join(out) + eol)
    os.replace(tmp, path)
    print(f"[apply] .env updated (backup saved as {path}.bak3).")
    return True


def ran_recently(days=7, stamp="ats_last_run.txt"):
    try:
        with open(stamp) as fh:
            last = date.fromisoformat(fh.read().strip())
        return (date.today() - last).days < days
    except Exception:
        return False


def probe_company(name):
    """Try each system and slug guess. Returns (status, details) with status one of
    found / empty / missing / unchecked."""
    errored = False
    empty_note = None
    for system, fn in SYSTEMS:
        for slug in slug_candidates(name):
            try:
                res = fn(slug)
                STATS["ok"] += 1
            except Exception as exc:
                STATS["fail"] += 1
                errored = True
                print(f"  ! {name} [{system}/{slug}]: {str(exc)[:60]}", flush=True)
                res = None
            time.sleep(PAUSE)
            if res is None:
                continue
            total, rel = res
            if total == 0 and system in ("lever", "ashby"):
                empty_note = f"{name} ({system}/{slug}, 0 open jobs now)"
                break
            return "found", (system, slug, total, rel)
    if empty_note:
        return "empty", empty_note
    return ("unchecked" if errored else "missing"), None


def main():
    args = set(sys.argv[1:])
    weekly = "--weekly" in args
    apply = "--apply" in args or weekly
    if weekly and ran_recently():
        print("[ats_finder] already ran in the last 7 days; skipping.")
        return

    stores = {"greenhouse": {}, "lever": {}, "ashby": {}}
    missing, empty, unchecked = [], [], []
    companies = load_companies()
    print(f"Checking {len(companies)} companies against public Greenhouse, Lever, and Ashby feeds...\n", flush=True)
    for name in companies:
        status, info = probe_company(name)
        if status == "found":
            system, slug, total, rel = info
            stores[system][slug] = (name, total, rel)
            print(f"  FOUND  {name:<18} {system:<10} slug={slug:<18} {total} jobs, {rel} relevant for you", flush=True)
        elif status == "empty":
            empty.append(info)
        elif status == "unchecked":
            unchecked.append(name)
        else:
            missing.append(name)

    if STATS["ok"] == 0:
        print("\n[ats_finder] no request succeeded (offline, blocked, or SSL problem). "
              "Nothing was changed; it will try again next run.")
        return

    gh = sorted(set(existing("ATS_GREENHOUSE")) | set(stores["greenhouse"]))
    lv = sorted(set(existing("ATS_LEVER")) | set(stores["lever"]))
    ab = sorted(set(existing("ATS_ASHBY")) | set(stores["ashby"]))
    lines = [
        f"ATS_GREENHOUSE={','.join(gh)}",
        f"ATS_LEVER={','.join(lv)}",
        f"ATS_ASHBY={','.join(ab)}",
    ]
    print("\n===== PASTE THESE THREE LINES INTO .env (replace the existing ATS_ lines) =====")
    print("\n".join(lines))
    print("===============================================================================")
    if empty:
        print("\nFound but nothing open right now (re-run later):", "; ".join(empty))
    if unchecked:
        print(f"\nCould not check {len(unchecked)} companies (rate limit or network error). Re-run later:")
        print("  " + ", ".join(unchecked))
    print(f"\nNo public Greenhouse/Lever/Ashby feed found for {len(missing)} companies. Check these careers pages by hand:")
    print("  " + ", ".join(missing))
    with open("ats_found.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n# Not found (check careers pages manually):\n# " + ", ".join(missing) + "\n")
        if unchecked:
            f.write("\n# Could not check (re-run later):\n# " + ", ".join(unchecked) + "\n")
    print("\nSaved to ats_found.txt")
    if apply and apply_to_env(lines):
        # Only mark the week as done when .env was really updated, so a missing .env retries next run.
        with open("ats_last_run.txt", "w") as fh:
            fh.write(date.today().isoformat())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
edge_engine.py - Structural conversion engine beyond passive job scraping:
1. First-Mover Conversion Ranking (weights match_score + posting freshness + direct ATS channel)
2. Market Gap Telemetry (aggregates top missing_skills across high-scoring jobs)
3. Day-1 Incident Runbook & Phone-Screen Drill Generator (proves hands-on AWS/Linux competence)
"""
import argparse
import collections
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import job_agent as ja


class TechnicalEdgeBrief(BaseModel):
    diagnostic_runbook_pitch: str = Field(
        description="A concise, high-signal 4-5 sentence 'Day-1 Triage Pitch' showing the hiring manager exactly how the candidate would diagnose a real incident in their stack using his actual tools (CloudWatch Logs, SSM Session Manager, ss, tcpdump, traceroute, netcat, pg_stat_activity, pg_locks, Terraform, or webhook signature verification)."
    )
    hiring_manager_hook: str = Field(
        description="A punchy 3-sentence direct message to a Support/Engineering Manager leading with technical proof-of-work instead of generic self-praise."
    )
    phone_screen_drills: List[str] = Field(
        description="3 role-specific technical phone-screen questions the recruiter/engineer is likely to ask for this JD, paired with the exact CLI command or architectural answer from the candidate's background."
    )
    micro_lab_suggestion: str = Field(
        description="If the JD has missing skills, 1 concrete 30-minute mini-addition the candidate can make to his ap-south-1 Terraform / LegacyLens repo to bridge the gap honestly."
    )


def compute_conversion_score(row: dict) -> float:
    """Computes an actionable priority score combining LLM fit, posting freshness, and channel quality."""
    base = float(row.get("match_score") or 0)
    bonus = 0.0

    # 1. Freshness boost: postings within the last 48 hours get priority strike status
    dp = (row.get("date_posted") or "").strip()[:10]
    if dp:
        try:
            posted_dt = datetime.fromisoformat(dp).date()
            age_days = (datetime.now(timezone.utc).date() - posted_dt).days
            if age_days <= 1:
                bonus += 12.0
            elif age_days <= 3:
                bonus += 7.0
            elif age_days >= 14:
                bonus -= 5.0
        except Exception:
            pass

    # 2. Channel quality boost: direct ATS boards convert much higher than crowded aggregators
    channel = (row.get("source_channel") or "").lower()
    site = (row.get("source_site") or "").lower()
    if "direct ats" in channel or site in ("greenhouse", "lever", "ashby", "smartrecruiters") or "keka" in site or "amazon" in site:
        bonus += 6.0

    # 3. Local Kolkata advantage
    loc = (row.get("location") or "").lower()
    if "kolkata" in loc:
        bonus += 5.0

    return round(base + bonus, 1)


def show_priority_strike_list(db_path: str = ja.DB_PATH, limit: int = 10):
    ja.stage_init(db_path)
    conn = ja.get_conn(db_path)
    conn.row_factory = sqlite3.Row
    applied_keys = ja.load_applied_keys(conn)
    rows = conn.execute(
        "SELECT id, title, company, location, match_score, date_posted, source_channel, source_site, job_url_direct, job_url, user_notes "
        "FROM jobs WHERE scored=1 AND match_score>=60 AND TRIM(COALESCE(user_notes, ''))=''"
    ).fetchall()
    conn.close()

    candidates = []
    for r in rows:
        d = dict(r)
        if ja.is_applied_duplicate(d, applied_keys):
            continue
        d["conversion_score"] = compute_conversion_score(d)
        candidates.append(d)

    candidates.sort(key=lambda x: (x["conversion_score"], x["match_score"], x["id"]), reverse=True)
    print("\n================ FIRST-MOVER STRIKE QUEUE (CONVERSION RANKED) ================")
    if not candidates:
        print("No unapplied jobs >= 60 found.")
        return []
    for idx, c in enumerate(candidates[:limit], 1):
        posted = c.get("date_posted") or "recent"
        print(
            f"{idx:2d}. [Conv:{c['conversion_score']} | Fit:{c['match_score']}] #{c['id']} "
            f"{c['title']} @ {c['company']} ({c['location']}) | Posted:{posted} | Via:{c.get('source_site')}"
        )
    print("==============================================================================\n")
    return candidates[:limit]


def analyze_market_skill_gaps(db_path: str = ja.DB_PATH, min_score: int = 60):
    """Aggregates missing_skills across all >=60 jobs to show the highest-ROI skills to add to the lab."""
    ja.stage_init(db_path)
    conn = ja.get_conn(db_path)
    rows = conn.execute(
        "SELECT missing_skills FROM jobs WHERE scored=1 AND match_score>=? AND missing_skills != ''",
        (min_score,),
    ).fetchall()
    conn.close()

    counter = collections.Counter()
    for (ms_raw,) in rows:
        for item in re.split(r"[,;/|]+", ms_raw or ""):
            clean = item.strip().lower()
            if len(clean) >= 2 and "experience" not in clean and "degree" not in clean:
                counter[clean] += 1

    print("\n================ MARKET SKILL-GAP TELEMETRY (TOP DEMAND IN YOUR QUEUE) ================")
    if not counter:
        print("Not enough scored jobs with missing_skills yet.")
        return []
    for skill, count in counter.most_common(10):
        print(f"  - {skill:<35} (requested in {count} matching jobs)")
    print("Tip: Adding the #1-#2 tools above as a small module in Legacylens-automation unlocks these roles.")
    print("=======================================================================================\n")
    return counter.most_common(10)


def generate_edge_brief(job_id: int, db_path: str = ja.DB_PATH):
    ja.stage_init(db_path)
    conn = ja.get_conn(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()

    if not row:
        print(f"[edge] Job #{job_id} not found.")
        return None

    job = dict(row)
    profile = ja.load_profile()
    if not ja.GEMINI_API_KEY:
        raise SystemExit("[edge] GEMINI_API_KEY missing in .env")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=ja.GEMINI_API_KEY)

    prompt = f"""You are a Senior Cloud Support & SRE Hiring Manager coaching Sourav Roy Chowdhury.
Create a Technical Proof-of-Work & Phone-Screen Edge Brief for the target job below.

STRICT GROUNDING RULES (USE ONLY REAL TOOLS & PROJECTS FROM CANDIDATE PROFILE):
- Live Production System: LegacyLens Automation (Node.js, PostgreSQL 16 with Row-Level Security, REST APIs, Twilio & Razorpay webhook signature verification, incident triage & log inspection on Railway and Render).
- AWS Project (ap-south-1, github.com/SOUROYAL123/Legacylens-automation): Two-AZ Terraform infrastructure (public/private/isolated subnets, NAT Gateways, multi-stage non-root Docker on ECS Fargate behind ALB, ECR lifecycle policies, encrypted RDS PostgreSQL 16, Secrets Manager runtime injection, SSM Session Manager & port forwarding without public SSH, lab Transit Gateway + IPsec Site-to-Site VPN).
- Linux & Network Diagnostics: Ubuntu, Bash, systemd, TCP/IP, subnetting, route tables, security groups, ss, tcpdump, traceroute, netcat, pg_stat_activity, pg_locks, CloudWatch Logs.
- Earlier Background: 14 years client-facing production pipeline coordination in 3D animation (Thotsynthesis, Dream4d, HiTech, AATS Studios) + B.Sc. (New Alipore College, 2006).

CANDIDATE PROFILE:
{profile}

TARGET JOB:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Missing Skills Flagged: {job.get('missing_skills', '')}
Description:
{ja.sanitize_untrusted_jd(job.get('description') or '')[:3800]}
"""

    models = [m for m in ja.MODEL_CHAIN if m != "gemini-flash"] or ["gemini-flash-lite-latest"]
    res = None
    for m in models:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TechnicalEdgeBrief,
                    temperature=0.2,
                ),
            )
            res = TechnicalEdgeBrief.model_validate_json(resp.text)
            break
        except Exception as exc:
            print(f"[edge] retry {m}: {str(exc)[:80]}")

    if not res:
        return None

    out = f"""
================ TECHNICAL PROOF-OF-WORK & PHONE-SCREEN EDGE (#{job_id}) ================
Target : {job.get('title')} @ {job.get('company')}

--- 1. "DAY-1 INCIDENT RUNBOOK" PITCH (PASTE IN APPLICATION / EMAIL) ---
{res.diagnostic_runbook_pitch}

--- 2. HIGH-SIGNAL HIRING MANAGER DM (PROOF-OF-WORK HOOK) ---
{res.hiring_manager_hook}

--- 3. 15-MINUTE PHONE SCREEN DRILLS (EXACT CLI / AWS ANSWERS) ---
"""
    for i, d in enumerate(res.phone_screen_drills, 1):
        out += f"  Q{i}: {d}\n"
    out += f"""
--- 4. 30-MINUTE LAB BRIDGE FOR MISSING SKILLS ---
  {res.micro_lab_suggestion}
=========================================================================================
"""
    print(out)
    edge_file = f"tailored_resume_job_{job_id}.txt"
    with open(edge_file, "a", encoding="utf-8") as f:
        f.write("\n" + out)
    print(f"[edge] Appended Proof-of-Work & Phone-Screen Drills to {edge_file}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=None, help="Generate Technical Edge Brief for a specific job ID")
    ap.add_argument("--rank", action="store_true", help="Show First-Mover Conversion Strike Queue")
    ap.add_argument("--gaps", action="store_true", help="Show Market Skill-Gap Telemetry across scored jobs")
    args = ap.parse_args()

    if args.id is not None:
        generate_edge_brief(args.id)
        return
    if args.rank:
        show_priority_strike_list()
        return
    if args.gaps:
        analyze_market_skill_gaps()
        return

    # Default behavior when run inside auto_runner.py
    top = show_priority_strike_list(limit=5)
    analyze_market_skill_gaps()


if __name__ == "__main__":
    main()

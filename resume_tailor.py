#!/usr/bin/env python3
"""
resume_tailor.py - Single-pass generator for ATS-tailored resume summary, bullets,
cover letter, and STAR story, strictly aligned with Sourav's two PDF resumes.
"""
import argparse
import os
import sqlite3
from typing import List
from pydantic import BaseModel, Field

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import job_agent as ja


class TailoredResumeOutput(BaseModel):
    target_role: str = Field(description="The job title being targeted.")
    company: str = Field(description="The hiring company.")
    recommended_base_pdf: str = Field(
        description="Sourav_Roy_Chowdhury_AWS_Cloud_Support.pdf or Sourav_Roy_Chowdhury_AWS_Cloud_Implementation.pdf"
    )
    ats_keywords_matched: List[str] = Field(
        description="Exact technical and operational keywords from the JD matched in this version."
    )
    tailored_summary: str = Field(
        description="A 3-4 sentence professional summary tailored to this specific JD."
    )
    tailored_bullets: List[str] = Field(
        description="5 high-impact resume bullet points re-phrased to match the JD using ONLY real experience."
    )
    cover_letter: str = Field(
        description="A tailored, ready-to-send 3-paragraph cover letter referencing real AWS/Terraform/PostgreSQL projects."
    )
    star_story: str = Field(
        description="One concise STAR-format interview story (Situation, Task, Action, Result) from the candidate's real background."
    )


def pick_best_pdf(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    impl_kw = ("implementation", "onboarding", "deployment", "delivery", "integration", "migration", "solutions", "client", " coordinator", "webhook")
    supp_kw = ("support", "noc", "incident", "triage", "l1", "l2", "escalation", "cloudwatch", "monitoring", "sysadmin", "linux", "troubleshoot")
    impl_score = sum(2 if k in title.lower() else 1 for k in impl_kw if k in text)
    supp_score = sum(2 if k in title.lower() else 1 for k in supp_kw if k in text)
    if impl_score > supp_score:
        return "Sourav_Roy_Chowdhury_AWS_Cloud_Implementation.pdf"
    return "Sourav_Roy_Chowdhury_AWS_Cloud_Support.pdf"


def tailor_resume_for_job(job_id: int, db_path: str = ja.DB_PATH):
    ja.stage_init(db_path)
    conn = ja.get_conn(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        conn.close()
        print(f"[error] Job #{job_id} not found in {db_path}.")
        return None

    job = dict(row)
    profile = ja.load_profile()

    if not ja.GEMINI_API_KEY:
        conn.close()
        raise SystemExit("[error] GEMINI_API_KEY missing in .env")

    from google import genai
    from google.genai import types
    client = genai.Client(api_key=ja.GEMINI_API_KEY)
    suggested_pdf = pick_best_pdf(job.get("title", ""), job.get("description", ""))

    prompt = f"""You are an expert technical resume writer and ATS optimization specialist.
Generate a complete application kit (Tailored Summary, 5 ATS Bullets, 3-Paragraph Cover Letter, and 1 STAR Story) for the JOB DESCRIPTION below.

STRICT FACTUAL ALIGNMENT WITH CANDIDATE RESUMES (NEVER INVENT OR ALTER FACTS):
1. Current Role: Founder & Cloud/Automation Developer | LegacyLens Automation, Kolkata (Jul 2022 - Present). Built and operate a live WhatsApp ordering and payment system (Node.js, PostgreSQL 16 with Row-Level Security, REST APIs, Twilio & Razorpay webhook signature verification and credential hardening) for a restaurant client; troubleshoot production incidents on Railway and Render using log inspection and root-cause analysis.
2. Parallel Role: Independent Tutor, Mathematics and Science (Class 7-10, CBSE/ICSE), Kolkata (Jul 2022 - Present).
3. Personal AWS Project (ap-south-1, github.com/SOUROYAL123/Legacylens-automation): Two-AZ AWS environment in Terraform (public, private application, and isolated database subnets across two AZs, NAT Gateways, separate route tables, multi-stage non-root Docker builds on ECS Fargate behind ALB, ECR lifecycle policies, encrypted RDS PostgreSQL 16, Secrets Manager runtime injection with scoped IAM task execution roles, SSM Session Manager & VPC Interface Endpoints with public SSH removed, lab Transit Gateway + IPsec Site-to-Site VPN).
4. Technical & Troubleshooting Tools: EC2, VPC, ECS Fargate, ECR, ALB, RDS PostgreSQL, IAM, Secrets Manager, SSM Session Manager, CloudWatch Logs, NAT Gateway, VPC Endpoints, Ubuntu, Bash, systemd, TCP/IP, subnetting, route tables, security groups, ss, tcpdump, traceroute, netcat, pg_stat_activity, pg_locks, health checks, incident triage, escalation handling.
5. Earlier Experience (14 years, 2008-2022 in Kolkata):
   - 3D Animator & Production Pipeline Coordinator | Thotsynthesis Pvt. Ltd. (Feb 2022 - Jun 2022)
   - 3D Animator | Dream4d Animation (Jul 2021 - Jan 2022)
   - 3D Generalist | HiTech Animation (Oct 2019 - Jun 2021)
   - Animation Lead | AATS Studios (Sep 2018 - Aug 2019)
   - Earlier 3D Animation Roles (2008 - 2018)
6. Education & Certification:
   - B.Sc. (General) | New Alipore College, Kolkata | 2006
   - Matriculation | A.K. Ghosh Memorial High School, Kolkata
   - AWS Certified Solutions Architect - Associate (SAA-C03): exam planned November 2026
7. Recommended Base Resume PDF: {suggested_pdf}

CANDIDATE PROFILE:
{profile}

JOB DESCRIPTION:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description:
{(job.get('description') or '')[:3800]}
"""

    print(f"[tailor] Single-pass kit generation for Job #{job_id}: {job.get('title')} @ {job.get('company')}...")
    models = [m for m in ja.MODEL_CHAIN if m != "gemini-flash"] or ["gemini-flash-lite-latest"]
    res = None
    for m in models:
        try:
            resp = client.models.generate_content(
                model=m,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TailoredResumeOutput,
                    temperature=0.2,
                ),
            )
            res = TailoredResumeOutput.model_validate_json(resp.text)
            break
        except Exception as exc:
            print(f"[retry] {m} failed: {str(exc)[:80]}")

    if not res:
        conn.close()
        print(f"[error] Failed to generate tailored kit for Job #{job_id}.")
        return None

    # Save cover_letter and star_story back to jobs.db so --kit and Excel have them
    conn.execute(
        "UPDATE jobs SET cover_letter=?, star_story=? WHERE id=?",
        (res.cover_letter, res.star_story, job_id),
    )
    conn.commit()
    conn.close()

    output_text = f"""================================================================================
TAILORED APPLICATION KIT: #{job_id} {res.target_role} @ {res.company}
================================================================================
Apply Link      : {job.get('job_url_direct') or job.get('job_url')}
Base PDF to Use : {res.recommended_base_pdf}
ATS Keywords    : {', '.join(res.ats_keywords_matched)}

--- CUSTOMIZED PROFESSIONAL SUMMARY ---
{res.tailored_summary}

--- CUSTOMIZED EXPERIENCE & PROJECT BULLETS ---
"""
    for b in res.tailored_bullets:
        output_text += f"  * {b}\n"
    output_text += f"""
--- TAILORED COVER LETTER ---
{res.cover_letter}

--- STAR INTERVIEW STORY ---
{res.star_story}
================================================================================
"""
    print(output_text)
    filename = f"tailored_resume_job_{job_id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output_text)
    print(f"[tailor] Saved full kit to {filename} and updated jobs.db\n")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, default=None, help="Job ID from jobs.db to tailor resume for")
    ap.add_argument("--top", type=int, default=3, help="Max new unapplied matches to tailor per run (default: 3)")
    ap.add_argument("--min-score", type=int, default=75, help="Minimum match_score for auto-tailoring (default: 75)")
    args = ap.parse_args()

    if args.id is not None:
        tailor_resume_for_job(args.id)
        return

    conn = ja.get_conn(ja.DB_PATH)
    applied_keys = ja.load_applied_keys(conn)
    rows = conn.execute(
        "SELECT id, title, company, match_score, user_notes FROM jobs "
        "WHERE scored=1 AND match_score>=? AND TRIM(COALESCE(user_notes, ''))='' "
        "ORDER BY match_score DESC, id DESC",
        (args.min_score,),
    ).fetchall()
    conn.close()

    pending_ids = [
        r["id"] for r in rows
        if not ja.is_applied_duplicate(dict(r), applied_keys)
        and not os.path.exists(f"tailored_resume_job_{r['id']}.txt")
    ][: args.top]

    if not pending_ids:
        print(f"[tailor] All unapplied jobs scoring >= {args.min_score} already have tailored resume kits.")
        return

    for jid in pending_ids:
        tailor_resume_for_job(jid)


if __name__ == "__main__":
    main()

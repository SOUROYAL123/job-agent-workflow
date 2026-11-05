#!/usr/bin/env python3
"""
interview_simulator.py - Interactive CLI mock interview agent that drills you on
real AWS, Linux, networking, and PostgreSQL scenarios for a specific Job ID and grades your answers.
Usage:
  python interview_simulator.py --id 387
"""
import argparse
import sqlite3
from typing import List
from pydantic import BaseModel, Field

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

import job_agent as ja


class InterviewQuestions(BaseModel):
    questions: List[str] = Field(
        description="3 realistic, scenario-based technical phone-screen questions tailored to this JD and the candidate's AWS/Linux/PostgreSQL resume."
    )


class AnswerEvaluation(BaseModel):
    score_out_of_10: int
    strengths: str
    missing_commands_or_concepts: str
    ideal_20_second_answer: str


def run_simulation(job_id: int, db_path: str = ja.DB_PATH):
    conn = ja.get_conn(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not row:
        raise SystemExit(f"Job #{job_id} not found in {db_path}")

    job = dict(row)
    profile = ja.load_profile()
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=ja.GEMINI_API_KEY)
    model = next((m for m in ja.MODEL_CHAIN if m != "gemini-flash"), "gemini-flash-lite-latest")

    q_prompt = f"""Generate 3 practical technical interview questions for Sourav interviewing for:
Role: {job.get('title')} @ {job.get('company')}
JD: {ja.sanitize_untrusted_jd(job.get('description') or '')[:2500]}
Candidate Profile: {profile[:2000]}
Focus on real troubleshooting: AWS VPC/ECS/ALB/RDS/SSM, Linux (ss, tcpdump, systemd), PostgreSQL (pg_locks, RLS), or incident communication."""

    resp = client.models.generate_content(
        model=model,
        contents=q_prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=InterviewQuestions, temperature=0.3),
    )
    qs = InterviewQuestions.model_validate_json(resp.text).questions

    print(f"\n================ LIVE MOCK INTERVIEW: {job.get('title')} @ {job.get('company')} ================")
    print("Type your answer to each question and press Enter (or type 'q' to quit).\n")

    for i, q in enumerate(qs, 1):
        print(f"Q{i}: {q}")
        ans = input("\nYour Answer > ").strip()
        if not ans or ans.lower() in ("q", "quit", "exit"):
            break
        eval_prompt = f"""Question: {q}\nCandidate Answer: {ans}\nCandidate Profile: {profile[:1500]}
Grade this answer like a Senior AWS Cloud Support Hiring Manager. Suggest exact CLI commands or AWS concepts from the candidate's real background."""
        ev_resp = client.models.generate_content(
            model=model,
            contents=eval_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=AnswerEvaluation, temperature=0.2),
        )
        ev = AnswerEvaluation.model_validate_json(ev_resp.text)
        print(f"\n  [Score: {ev.score_out_of_10}/10]")
        print(f"  + Strengths : {ev.strengths}")
        print(f"  ! To Add    : {ev.missing_commands_or_concepts}")
        print(f"  * Gold Pitch: {ev.ideal_20_second_answer}\n" + "-" * 75)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", type=int, required=True, help="Job ID from jobs.db to practice for")
    args = ap.parse_args()
    run_simulation(args.id)

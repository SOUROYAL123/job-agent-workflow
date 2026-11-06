#!/usr/bin/env python3
"""
inbox_triage.py - Closed-loop IMAP scanner that checks recent emails against companies
in your `applications` table, auto-updates statuses to 'replied', 'interviewing' or 'rejected',
and triggers an edge_engine prep brief when a recruiter invites you to interview.
"""
import email
import imaplib
import re
import sqlite3
from datetime import datetime, timedelta
from email.header import decode_header

import job_agent as ja

INTERVIEW_WORDS = re.compile(
    r"\b(interview|schedule|calendly|availability|shortlisted|phone\s+screen|technical\s+round|assessment|hackerrank|codility)\b",
    re.I,
)
REJECTION_WORDS = re.compile(
    r"\b(unfortunately|not\s+moving\s+forward|other\s+candidates|unable\s+to\s+proceed|not\s+selected)\b",
    re.I,
)

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _decode(val: str) -> str:
    if not val:
        return ""
    parts = []
    for chunk, enc in decode_header(val):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="ignore"))
        else:
            parts.append(str(chunk))
    return " ".join(parts).strip()


def _imap_since(days: int) -> str:
    """IMAP SINCE date (DD-Mon-YYYY) with fixed English month names, independent of locale."""
    d = datetime.now() - timedelta(days=days)
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _connect_imap():
    mail = imaplib.IMAP4_SSL(ja.IMAP_SERVER, ja.IMAP_PORT)
    mail.login(ja.EMAIL_ADDRESS, ja.EMAIL_PASSWORD)
    return mail


def _job_id_for(conn: sqlite3.Connection, url: str):
    """The applications table has no job id; find the matching job row by URL."""
    if not url:
        return None
    row = conn.execute(
        "SELECT id FROM jobs WHERE job_url=? OR job_url_direct=? LIMIT 1", (url, url)
    ).fetchone()
    return int(row["id"]) if row else None


def scan_recruiter_replies(db_path: str = ja.DB_PATH, connect=None) -> int:
    """Returns the number of status updates. `connect` is an IMAP connection factory (for tests)."""
    ja.stage_init(db_path)
    conn = ja.get_conn(db_path)
    conn.row_factory = sqlite3.Row

    apps = conn.execute(
        "SELECT id, company, title, status, job_url FROM applications "
        "WHERE LOWER(status) IN ('applied', 'replied')"
    ).fetchall()
    if not apps:
        conn.close()
        print("[inbox-triage] No active 'applied' entries in applications table to monitor yet.")
        return 0

    if connect is None:
        if not (ja.EMAIL_ADDRESS and ja.EMAIL_PASSWORD):
            conn.close()
            print("[inbox-triage] EMAIL_ADDRESS / EMAIL_PASSWORD not configured; skipping inbox reply scan.")
            return 0
        connect = _connect_imap

    updates = 0
    try:
        mail = connect()
        mail.select("INBOX")
        typ, data = mail.search(None, f"(SINCE {_imap_since(14)})")
        msg_ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-80:]
        for num in msg_ids:
            typ, msg_data = mail.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_hdr = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email.message_from_bytes(raw_hdr)
            subj = _decode(msg.get("Subject", ""))
            sender = _decode(msg.get("From", ""))
            combined = f"{subj} {sender}".lower()
            # Ignore automated job alert senders
            if any(h in combined for h in ja.ALERT_SENDER_HINTS):
                continue
            combined_norm = re.sub(r"[^a-z0-9]+", "", combined)
            for app in apps:
                comp = (app["company"] or "").strip()
                comp_norm = re.sub(r"[^a-z0-9]+", "", comp.lower())
                if len(comp_norm) < 3 or comp_norm not in combined_norm:
                    continue
                new_status = "replied"
                if INTERVIEW_WORDS.search(subj):
                    new_status = "interviewing"
                elif REJECTION_WORDS.search(subj):
                    new_status = "rejected"

                if new_status == (app["status"] or "").lower():
                    continue
                conn.execute(
                    "UPDATE applications SET status=?, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
                    (new_status, ja.now_utc(), f" | Auto-detected email: {subj[:60]}", app["id"]),
                )
                conn.commit()
                updates += 1
                print(f"[inbox-triage] {comp} ({app['title']}) -> status upgraded to '{new_status.upper()}' ({subj[:60]})")

                if new_status == "interviewing":
                    job_id = _job_id_for(conn, app["job_url"])
                    if job_id:
                        try:
                            import edge_engine

                            edge_engine.generate_edge_brief(job_id, db_path)
                        except Exception as exc:
                            print(f"[inbox-triage] edge brief for job #{job_id} skipped: {str(exc)[:100]}")
        try:
            mail.logout()
        except Exception:
            pass
    except Exception as exc:
        print(f"[inbox-triage] IMAP check skipped: {str(exc)[:100]}")

    conn.close()
    print(f"[inbox-triage] Checked active applications; {updates} status update(s).")
    return updates


if __name__ == "__main__":
    scan_recruiter_replies()

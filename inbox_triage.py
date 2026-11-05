#!/usr/bin/env python3

"""

inbox_triage.py - Closed-loop IMAP scanner that checks recent emails against companies

in your `applications` table, auto-updates statuses to 'replied' or 'interviewing',

and triggers edge_engine.py prep kits when a recruiter responds.

"""

import email

import imaplib

import re

import sqlite3

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





def scan_recruiter_replies(db_path: str = ja.DB_PATH):

    ja.stage_init(db_path)

    conn = ja.get_conn(db_path)

    conn.row_factory = sqlite3.Row

    apps = conn.execute(

        "SELECT id, company, title, status, job_id FROM applications WHERE status IN ('Applied', 'replied')"

    ).fetchall()



    if not apps:

        conn.close()

        print("[inbox-triage] No active 'Applied' entries in applications table to monitor yet.")

        return 0



    if not (ja.EMAIL_USER and ja.EMAIL_PASS):

        conn.close()

        print("[inbox-triage] EMAIL_USER / EMAIL_PASS not configured; skipping inbox reply scan.")

        return 0



    updates = 0

    try:

        M = imaplib.IMAP4_SSL(ja.IMAP_HOST)

        M.login(ja.EMAIL_USER, ja.EMAIL_PASS)

        M.select("INBOX")

        typ, data = M.search(None, f"(SINCE {ja.imap_since_date(14)})")

        msg_ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-80:]



        for num in msg_ids:

            typ, msg_data = M.fetch(num, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")

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



            for app in apps:

                comp = (app["company"] or "").strip()

                comp_norm = re.sub(r"[^a-z0-9]+", "", comp.lower())

                if len(comp_norm) < 3 or comp_norm not in re.sub(r"[^a-z0-9]+", "", combined):

                    continue



                new_status = "replied"

                if INTERVIEW_WORDS.search(subj):

                    new_status = "interviewing"

                elif REJECTION_WORDS.search(subj):

                    new_status = "rejected"



                if new_status != app["status"]:

                    conn.execute(

                        "UPDATE applications SET status=?, updated_at=?, notes= COALESCE(notes,'') || ? WHERE id=?",

                        (new_status, ja.now_utc(), f" | Auto-detected email: {subj[:60]}", app["id"]),

                    )

                    conn.commit()

                    updates += 1

                    print(f"[inbox-triage] {comp} ({app['title']}) -> status upgraded to '{new_status.upper()}' ({subj[:60]})")

                    if new_status == "interviewing" and app["job_id"]:

                        try:

                            import edge_engine

                            edge_engine.generate_edge_brief(int(app["job_id"]), db_path)

                        except Exception:

                            pass

        M.logout()

    except Exception as exc:

        print(f"[inbox-triage] IMAP check skipped: {str(exc)[:100]}")



    conn.close()

    print(f"[inbox-triage] Checked active applications; {updates} status update(s).")

    return updates





if __name__ == "__main__":

    scan_recruiter_replies()


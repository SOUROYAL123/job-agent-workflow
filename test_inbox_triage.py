"""Offline tests for inbox_triage: schema match, status handling, alert-sender skip, edge brief by job URL."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
DB = os.path.join(tmp, "t.db")
os.environ["DB_PATH"] = DB
import job_agent as ja
import edge_engine
import inbox_triage as it

ja.stage_init(DB)
conn = sqlite3.connect(DB)
URL = "https://example.com/jobs/acme-1"
ja.insert_job(conn.cursor(), job_hash="acme1", title="Cloud Support Engineer", company="Acme Cloud",
              location="Kolkata", description="AWS", job_url=URL, source_channel="test", source_site="test")
for key, comp, title, status, url in [
    ("a1", "Acme Cloud", "Cloud Support Engineer", "applied", URL),
    ("b1", "Beta Systems", "Support Engineer", "Applied", ""),      # legacy capitalised status still scanned
    ("g1", "Gamma Labs", "Implementation Specialist", "applied", ""),
    ("d1", "Delta Works", "Cloud Engineer", "rejected", ""),        # finished applications are not rescanned
]:
    conn.execute(
        "INSERT INTO applications (app_key, company, title, job_url, status, applied_date) VALUES (?,?,?,?,?,?)",
        (key, comp, title, url, status, "2026-11-01"))
conn.commit()
conn.close()


class FakeIMAP:
    def __init__(self, msgs):
        self.msgs = msgs

    def select(self, box):
        return "OK", [b"1"]

    def search(self, charset, criteria):
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.msgs)))]

    def fetch(self, num, spec):
        subj, frm = self.msgs[int(num) - 1]
        hdr = f"Subject: {subj}\r\nFrom: {frm}\r\nDate: Thu, 05 Nov 2026 10:00:00 +0530\r\n\r\n".encode()
        return "OK", [(b"1 (BODY[HEADER.FIELDS (SUBJECT FROM DATE)] {%d}" % len(hdr), hdr), b")"]

    def logout(self):
        pass


msgs = [
    ("Acme Cloud: interview invitation for Cloud Support Engineer", "HR <hr@acmecloud.com>"),
    ("Update from Beta Systems: unfortunately we are not moving forward", "jobs@betasystems.io"),
    ("New jobs at Gamma Labs", "LinkedIn Job Alerts <jobs-noreply@linkedin.com>"),   # alert sender: ignored
    ("Delta Works: schedule a call", "talent@deltaworks.com"),                      # status 'rejected': not scanned
]
briefs = []
edge_engine.generate_edge_brief = lambda job_id, db_path=None: briefs.append(job_id)

n = it.scan_recruiter_replies(DB, connect=lambda: FakeIMAP(msgs))
assert n == 2, n
c = sqlite3.connect(DB)
st = dict(c.execute("SELECT app_key, status FROM applications").fetchall())
job_id = c.execute("SELECT id FROM jobs WHERE job_hash='acme1'").fetchone()[0]
c.close()
assert st == {"a1": "interviewing", "b1": "rejected", "g1": "applied", "d1": "rejected"}, st
print("PASS  triage: lowercase/legacy statuses scanned, interview + rejection detected, alerts and closed apps ignored")
assert briefs == [job_id], (briefs, job_id)
print("PASS  triage: interview invite triggers an edge brief for the job found by URL (no job_id column needed)")

# Running again changes nothing
assert it.scan_recruiter_replies(DB, connect=lambda: FakeIMAP(msgs)) == 0
print("PASS  triage: rescanning the same emails is idempotent")

# Missing credentials: skip cleanly instead of crashing
c = sqlite3.connect(DB)
c.execute("UPDATE applications SET status='applied' WHERE app_key='b1'")
c.commit()
c.close()
ja.EMAIL_ADDRESS, ja.EMAIL_PASSWORD = "", ""
assert it.scan_recruiter_replies(DB) == 0
print("PASS  triage: missing EMAIL_ADDRESS/EMAIL_PASSWORD skips the scan without crashing")

print("\nALL INBOX TRIAGE TESTS PASSED")

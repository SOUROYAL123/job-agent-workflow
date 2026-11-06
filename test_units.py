import sys as _sys, pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
import os, sqlite3, tempfile
tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "u.db")
import job_agent as ja

DB = os.path.join(tmp, "u.db")
ja.stage_init(DB)

conn = sqlite3.connect(DB)
ja.insert_job(conn.cursor(), job_hash="poison1", title="Cloud Support", company="TestCo",
              location="Kolkata", description="AWS Linux", job_url="https://example.com/p1",
              source_channel="test", source_site="test")
conn.commit(); conn.close()

def broken_scorer(job):
    raise ValueError("malformed JSON payload")

for strike in (1, 2, 3):
    ja.stage_score(DB, scorer=broken_scorer, sleep_sec=0)

c = sqlite3.connect(DB)
scored, attempts, model = c.execute("SELECT scored, score_attempts, scored_model FROM jobs WHERE job_hash='poison1'").fetchone()
c.close()
assert scored == 1 and attempts == 3 and model == "error-skip", (scored, attempts, model)
print("PASS  unit: 3-strike poison-row cap parks failing job as error-skip")

# 4. First-mover conversion score boosts fresh direct-ATS Kolkata roles
import edge_engine as ee
from datetime import datetime, timezone
today_str = datetime.now(timezone.utc).date().isoformat()
fresh_ats = {"match_score": 75, "date_posted": today_str, "source_channel": "Direct ATS", "source_site": "greenhouse", "location": "Kolkata"}
stale_board = {"match_score": 75, "date_posted": "2025-01-01", "source_channel": "Job Board", "source_site": "linkedin", "location": "Remote, India"}
assert ee.compute_conversion_score(fresh_ats) > ee.compute_conversion_score(stale_board)
print("PASS  unit: edge_engine conversion_score prioritizes fresh Direct ATS + Kolkata roles")

print("\nALL UNIT TESTS PASSED")

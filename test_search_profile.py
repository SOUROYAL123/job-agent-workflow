"""Offline tests for the search profile merge, query rotation and priority-company location bypass."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmp, "s.db")
import job_agent as ja

# 1. Merge: .env queries first, case-insensitive duplicates dropped, company searches included
profile = {"queries": ["cloud support engineer aws", "Implementation Specialist"],
           "company_queries": ["Cloud4C", "  implementation   specialist "]}
merged = ja.merge_queries(["My Custom Query", "Cloud Support Engineer AWS"], profile)
assert merged == ["My Custom Query", "Cloud Support Engineer AWS", "Implementation Specialist", "Cloud4C"], merged
print("PASS  profile: .env queries first, duplicates dropped, company searches merged")

# 2. Shipped search_profile.json is valid and non-trivial
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_profile.json"), encoding="utf-8") as f:
    shipped = json.load(f)
assert len(shipped["queries"]) >= 20 and {"Cloud4C", "Minfy", "CloudThat"} <= set(shipped["company_queries"])
assert len(ja.merge_queries([], shipped)) == len({q.lower() for q in shipped["queries"] + shipped["company_queries"]})
print("PASS  profile: shipped search_profile.json is valid")

# 3. Missing or broken profile files never crash the agent
assert ja.load_search_profile(os.path.join(tmp, "nope.json")) == {}
bad = os.path.join(tmp, "bad.json")
with open(bad, "w", encoding="utf-8") as f:
    f.write("{not json")
assert ja.load_search_profile(bad) == {}
os.environ["SEARCH_PROFILE"] = "off"
assert ja.load_search_profile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "search_profile.json")) == {}
del os.environ["SEARCH_PROFILE"]
print("PASS  profile: missing/invalid file and SEARCH_PROFILE=off are handled")

# 4. Rotation covers every query across runs and wraps around
qs = [f"q{i}" for i in range(7)]
cur = os.path.join(tmp, ".cursor")
seen, runs = [], 0
for _ in range(3):  # ceil(7/3) runs
    seen += ja.pick_queries(qs, 3, cur)
    runs += 1
assert set(seen) == set(qs), seen
assert ja.pick_queries(qs, 3, cur) == ["q2", "q3", "q4"], "cursor should wrap after 9 picks"
assert ja.pick_queries(qs, 0, cur) == qs and ja.pick_queries(qs, 7, cur) == qs and ja.pick_queries(qs, 99, cur) == qs
print("PASS  rotation: all queries covered across runs, wraps, 0/oversize means all")

# 5. Corrupt cursor falls back to the start
with open(cur, "w", encoding="utf-8") as f:
    f.write("garbage")
assert ja.pick_queries(qs, 3, cur) == ["q0", "q1", "q2"]
print("PASS  rotation: corrupt cursor file restarts safely")

# 6. Location rule unchanged by default; priority companies bypass it only when configured
job = {"title": "Cloud Support Engineer", "company": "Cloud4C Services", "location": "Bengaluru, India",
       "is_remote": 0, "description": "Onsite role."}
ja.LOCATION_BYPASS_COMPANIES = []
assert ja.location_ok(job) is False
ja.LOCATION_BYPASS_COMPANIES = ["cloud4c"]
assert ja.location_ok(job) is True
assert ja.location_ok(dict(job, company="Other Corp")) is False
assert ja.location_ok(dict(job, company="Other Corp", location="Kolkata, West Bengal")) is True
ja.LOCATION_BYPASS_COMPANIES = []
print("PASS  location: non-Kolkata onsite rejected by default; bypass is opt-in per company")

print("\nALL SEARCH PROFILE TESTS PASSED")

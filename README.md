# Job Agent - setup (Windows)

## 1. Install (once)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Fill in `.env`: `GEMINI_API_KEY`, and for Gmail an App Password (Google Account > Security >
2-Step Verification > App passwords).

## 2. Edit candidate_profile.txt
Add only skills you have actually used hands-on. The scorer credits nothing else.

## 3. Verify before trusting it (in this order)
0. `py check_key.py`                - confirms your Gemini key works (fix this first if it says REJECTED)
1. `python test_pipeline.py`        - offline checks, no accounts needed
2. `python job_agent.py --stage scrape`  - expect rows; if a board returns 0, drop it from SITES
3. `python job_agent.py --stage email`   - only job-alert mails are marked read
4. `python job_agent.py --stage score`   - check 5-10 scores by eye against the real job posts
5. `python job_agent.py --stage digest`  - writes the Excel and emails you

Then `python job_agent.py` runs everything in order.

## 4. Schedule
Task Scheduler > Create Basic Task > daily 8:00 > Action: start `run_daily.bat`.
Output goes to `run_log.txt`. (`daily_job_agent.yml` is the GitHub Actions alternative; private repo only.)

## 5. Email alerts for portals JobSpy can't scrape
Create alerts on Hirist, Instahyre, Foundit, Cutshort, Wellfound and company career pages.
Their emails are picked up by the email stage automatically.

## Notes
- Your notes: type in the last column ("Applied? (your notes)") on any sheet. Each run reads those
  notes into the database before rebuilding, so they survive and appear on every sheet.
  To delete a note, type a single `-`. Don't rename or delete the ID column.
- If the Excel file is open during a run, the agent saves a timestamped copy instead; your notes in
  either file are still picked up on the next run (newest file wins).
- Rows are scored once. To re-score after editing the profile:
  `sqlite3 jobs.db "UPDATE jobs SET scored=0, emailed_in_digest=0"` (this will re-email everything).

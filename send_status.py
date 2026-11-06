
import os, smtplib

from email.mime.text import MIMEText

from dotenv import load_dotenv



load_dotenv(".env", override=True)

addr = os.getenv("EMAIL_ADDRESS", "").strip()

pw = os.getenv("EMAIL_PASSWORD", "").strip()

to = os.getenv("RECIPIENT_EMAIL", "").strip() or addr

status = open("LAST_RUN_STATUS.txt").read() if os.path.exists("LAST_RUN_STATUS.txt") else "No status file found"

tail = "".join(open("run_log.txt", errors="replace").readlines()[-5:])

outcome = next((l.split(":", 1)[1].strip() for l in status.splitlines() if l.startswith("Outcome")), "unknown")

msg = MIMEText(status + "\n\nLast log lines:\n" + tail)

msg["Subject"] = "[Job Agent] " + outcome

msg["From"], msg["To"] = addr, to

with smtplib.SMTP(os.getenv("SMTP_SERVER", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:

    s.ehlo(); s.starttls(); s.login(addr, pw); s.sendmail(addr, [to], msg.as_string())

print("status email sent")

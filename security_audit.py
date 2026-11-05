#!/usr/bin/env python3
"""
security_audit.py - Scans git-tracked and staged files for accidental secret leaks,
API keys, database files, or spreadsheets before allowing commits or CI passes.
"""
import os
import re
import subprocess
import sys

FORBIDDEN_FILES = (
    re.compile(r"(^|/)\.env(\..+)?$"),
    re.compile(r"\.(db|sqlite|sqlite3|xlsx|xls|bak|pem|key)$", re.I),
    re.compile(r"(^|/)candidate_profile\.txt$"),
    re.compile(r"(^|/)tailored_resume_job_\d+\.txt$"),
)

ALLOWED_EXCEPTIONS = {".env.example", "candidate_profile.example.txt"}

SECRET_PATTERNS = (
    ("Google/Gemini API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("OpenAI/OpenRouter Key", re.compile(r"sk-(?:proj-|or-v1-)?[0-9A-Za-z]{20,}")),
    ("Groq API Key", re.compile(r"gsk_[0-9A-Za-z]{20,}")),
    ("GitHub Personal Token", re.compile(r"gh[pousr]_[0-9A-Za-z]{30,}")),
    ("Private SSH/RSA Key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("Hardcoded SMTP Password", re.compile(r'EMAIL_PASS\s*=\s*["\']?(?!your_|xxxx|change_me|\$\{)[a-z]{4}\s[a-z]{4}\s[a-z]{4}\s[a-z]{4}', re.I)),
)


def get_files_to_scan(staged_only: bool = False):
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"] if staged_only else ["git", "ls-files"]
    try:
        out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore")
        return [f.strip().replace("\\", "/") for f in out.splitlines() if f.strip()]
    except Exception:
        return []


def main():
    staged_only = "--staged" in sys.argv
    files = get_files_to_scan(staged_only=staged_only)
    issues = []

    for fpath in files:
        base = os.path.basename(fpath)
        if base in ALLOWED_EXCEPTIONS or fpath in ALLOWED_EXCEPTIONS:
            continue
        for pat in FORBIDDEN_FILES:
            if pat.search(fpath):
                issues.append(f"Forbidden sensitive file tracked/staged: {fpath}")
        if not os.path.exists(fpath) or os.path.getsize(fpath) > 2_000_000:
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue
        for label, regex in SECRET_PATTERNS:
            if regex.search(content):
                issues.append(f"Potential {label} detected inside {fpath}")

    if issues:
        print("\n[SECURITY BLOCK] Secret or sensitive file leak detected:")
        for i in issues:
            print(f"  - {i}")
        print("Commit/check aborted to protect your repository.\n")
        return 1

    print(f"PASS  security_audit: scanned {len(files)} file(s) — zero leaked keys or sensitive files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

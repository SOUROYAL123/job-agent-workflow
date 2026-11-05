#!/usr/bin/env python3
"""
merge_env.py - Safely merges missing keys from a template (.env.example)
into an existing .env file while creating an automatic backup.
"""

import argparse
import os
import re
import shutil
from datetime import datetime
from typing import List, Optional, Set, Tuple


def extract_key(line: str) -> Optional[str]:
    """Extracts the variable name from a standard or exported .env line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    if "=" in stripped:
        return stripped.split("=", 1)[0].strip()
    return None


def get_existing_keys(env_path: str) -> Set[str]:
    """Reads an existing .env file and collects all defined keys."""
    keys = set()
    if not os.path.exists(env_path):
        return keys

    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            key = extract_key(line)
            if key:
                keys.add(key)
    return keys


def parse_template_blocks(template_path: str) -> List[Tuple[Optional[str], List[str]]]:
    """
    Parses template into logical blocks, binding comments/docstrings
    to their corresponding key definition line.
    """
    blocks = []
    current_comments: List[str] = []

    with open(template_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            key = extract_key(line)
            if key:
                # Key definition found; attach accumulated comments
                blocks.append((key, current_comments + [line]))
                current_comments = []
            else:
                current_comments.append(line)

    return blocks


def merge_env(
    target_env: str = ".env",
    template_env: str = ".env.example",
    dry_run: bool = False,
) -> int:
    """
    Appends missing template variables to the target .env file.
    Returns the count of merged keys.
    """
    if not os.path.exists(template_env):
        print(f"[Error] Template file not found: {template_env}")
        return 0

    # Ensure target .env exists (create empty if missing)
    if not os.path.exists(target_env):
        if not dry_run:
            with open(target_env, "w", encoding="utf-8") as f:
                f.write(f"# Created from {template_env} on {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            print(f"[Init] Created new target file: {target_env}")

    existing_keys = get_existing_keys(target_env)
    template_blocks = parse_template_blocks(template_env)

    missing_blocks: List[Tuple[str, List[str]]] = []
    for key, lines in template_blocks:
        if key and key not in existing_keys:
            missing_blocks.append((key, lines))

    if not missing_blocks:
        print(f"[OK] No missing keys found. '{target_env}' is fully aligned with '{template_env}'.")
        return 0

    print(f"[Notice] Found {len(missing_blocks)} missing key(s):")
    for key, _ in missing_blocks:
        print(f"  + {key}")

    if dry_run:
        print("[Dry Run] No files modified.")
        return len(missing_blocks)

    # 1. Automatic Timestamped Backup
    backup_path = f"{target_env}.bak_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copyfile(target_env, backup_path)
    print(f"[Backup] Saved current environment snapshot to: {backup_path}")

    # 2. Append missing blocks cleanly
    with open(target_env, "a", encoding="utf-8") as f:
        # Ensure target file ends with a clean newline before appending
        f.write("\n\n")
        f.write("# ======================================================================\n")
        f.write(f"# MERGED MISSING KEYS FROM {os.path.basename(template_env)} ({datetime.now():%Y-%m-%d %H:%M:%S})\n")
        f.write("# ======================================================================\n")

        for _, lines in missing_blocks:
            for line in lines:
                f.write(line)
            if not lines[-1].endswith("\n"):
                f.write("\n")

    print(f"[Success] Successfully merged {len(missing_blocks)} key(s) into '{target_env}'.")
    return len(missing_blocks)


def main():
    parser = argparse.ArgumentParser(
        description="Merge missing keys from an env template into an existing .env file."
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to your current active .env file (default: .env)",
    )
    parser.add_argument(
        "--template",
        default=".env.example",
        help="Path to the source template .env file (default: .env.example)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the merge and show keys without modifying files",
    )

    args = parser.parse_args()
    merge_env(target_env=args.env, template_env=args.template, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

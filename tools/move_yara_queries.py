#!/usr/bin/env python3
"""Move YARA queries out of GitOps lib/ to a separate yara/ directory.

Preserves the same directory structure so they can be re-integrated later
when proper YARA config is set up.

Usage:
    python3 move_yara_queries.py [--dry-run]
"""

import argparse
import os
import re
import shutil
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")
YARA_DIR = os.path.join(SCRIPT_DIR, "yara")


def has_yara_variables(sql):
    """Check if SQL contains YARA-style $variables."""
    if not sql:
        return False
    # YARA variables: $varname (not $$escaped, not $FLEET_*)
    pattern = r'\$(?!\$)(?!FLEET_)[a-zA-Z_][a-zA-Z0-9_]*'
    return bool(re.search(pattern, sql))


def find_query_files(lib_dir):
    """Find all .yml query files in lib/."""
    query_files = []
    for root, dirs, files in os.walk(lib_dir):
        if "/queries/" not in root and not root.endswith("/queries"):
            continue
        for filename in files:
            if filename.endswith((".yml", ".yaml")) and not filename.startswith("."):
                query_files.append(os.path.join(root, filename))
    return sorted(query_files)


def load_file(filepath):
    """Load YAML file."""
    with open(filepath, "r") as f:
        content = f.read()
    if not content.strip():
        return None
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Move YARA queries to separate directory")
    parser.add_argument("--dry-run", action="store_true", help="Don't move files")
    args = parser.parse_args()

    query_files = find_query_files(LIB_DIR)
    print(f"Found {len(query_files)} query files")

    moved = 0

    for filepath in query_files:
        data = load_file(filepath)
        if data is None:
            continue

        if not isinstance(data, list):
            continue

        # Check if any query in file has YARA variables
        has_yara = False
        for query in data:
            if isinstance(query, dict):
                sql = query.get("query", "")
                if has_yara_variables(sql):
                    has_yara = True
                    break

        if not has_yara:
            continue

        # Calculate destination path (lib/... -> yara/...)
        rel_path = os.path.relpath(filepath, LIB_DIR)
        dest_path = os.path.join(YARA_DIR, rel_path)
        dest_dir = os.path.dirname(dest_path)

        rel_src = os.path.relpath(filepath, SCRIPT_DIR)
        rel_dst = os.path.relpath(dest_path, SCRIPT_DIR)

        if args.dry_run:
            print(f"MOVE: {rel_src} -> {rel_dst}")
        else:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(filepath, dest_path)
            print(f"Moved: {rel_src} -> {rel_dst}")

        moved += 1

    print()
    print(f"Total YARA queries to move: {moved}")

    if args.dry_run:
        print("\nThis was a dry run. Run without --dry-run to move files.")


if __name__ == "__main__":
    main()

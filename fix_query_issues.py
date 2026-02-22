#!/usr/bin/env python3
"""Fix various query issues for Fleet GitOps compatibility.

Issues fixed:
1. Remove queries with YARA-style $variables (need separate YARA config)
2. Convert interval strings to integers
3. Remove queries without SQL query field

Usage:
    python3 fix_query_issues.py [--dry-run]
"""

import argparse
import os
import re
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")


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


def has_yara_variables(sql):
    """Check if SQL contains YARA-style $variables."""
    if not sql:
        return False
    # YARA variables look like $varname (but not $$varname which is escaped)
    # Exclude Fleet env vars like $FLEET_*
    pattern = r'\$(?!\$)(?!FLEET_)[a-zA-Z_][a-zA-Z0-9_]*'
    return bool(re.search(pattern, sql))


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


def save_file(filepath, data):
    """Save YAML file."""
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="Fix Fleet query issues")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify files")
    args = parser.parse_args()

    query_files = find_query_files(LIB_DIR)
    print(f"Found {len(query_files)} query files")

    yara_removed = 0
    no_sql_removed = 0
    interval_fixed = 0
    files_modified = 0
    files_deleted = 0

    for filepath in query_files:
        data = load_file(filepath)
        if data is None:
            continue

        if not isinstance(data, list):
            continue

        modified = False
        new_queries = []

        for query in data:
            if not isinstance(query, dict):
                new_queries.append(query)
                continue

            sql = query.get("query", "")

            # Check for missing SQL
            if not sql or not sql.strip():
                rel_path = os.path.relpath(filepath, SCRIPT_DIR)
                name = query.get("name", "unknown")
                if args.dry_run:
                    print(f"NO SQL: {rel_path} - {name}")
                no_sql_removed += 1
                modified = True
                continue

            # Check for YARA variables
            if has_yara_variables(sql):
                rel_path = os.path.relpath(filepath, SCRIPT_DIR)
                name = query.get("name", "unknown")
                if args.dry_run:
                    print(f"YARA: {rel_path} - {name}")
                yara_removed += 1
                modified = True
                continue

            # Fix interval type (string -> int)
            if "interval" in query:
                interval = query["interval"]
                if isinstance(interval, str):
                    try:
                        query["interval"] = int(interval)
                        interval_fixed += 1
                        modified = True
                        if args.dry_run:
                            rel_path = os.path.relpath(filepath, SCRIPT_DIR)
                            name = query.get("name", "unknown")
                            print(f"INTERVAL: {rel_path} - {name} ({interval} -> {query['interval']})")
                    except ValueError:
                        pass

            new_queries.append(query)

        if modified:
            if not args.dry_run:
                if not new_queries:
                    os.remove(filepath)
                    files_deleted += 1
                    rel_path = os.path.relpath(filepath, SCRIPT_DIR)
                    print(f"Deleted: {rel_path}")
                else:
                    save_file(filepath, new_queries)
                    files_modified += 1
                    rel_path = os.path.relpath(filepath, SCRIPT_DIR)
                    print(f"Modified: {rel_path}")

    print()
    print("=" * 60)
    print("Summary:")
    print(f"  YARA queries removed: {yara_removed}")
    print(f"  No-SQL queries removed: {no_sql_removed}")
    print(f"  Interval types fixed: {interval_fixed}")
    if not args.dry_run:
        print(f"  Files modified: {files_modified}")
        print(f"  Files deleted: {files_deleted}")
    else:
        print()
        print("This was a dry run. Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()

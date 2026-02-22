#!/usr/bin/env python3
"""Convert query files from old fleetctl apply format to new GitOps list format.

Old format:
---
apiVersion: v1
kind: query
spec:
  name: query_name
  description: ...
  query: SELECT ...
  platform: windows

New format:
- name: query_name
  description: ...
  query: SELECT ...
  platform: windows

Usage:
    python3 convert_query_format.py [--dry-run]
"""

import argparse
import os
import re
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")

# Fields to keep from the spec
KEEP_FIELDS = [
    "name",
    "description",
    "query",
    "platform",
    "interval",
    "observer_can_run",
    "automations_enabled",
    "logging",
    "min_osquery_version",
    "discard_data",
]


def convert_file(filepath, dry_run=False):
    """Convert a single query file to the new format."""
    with open(filepath, "r") as f:
        content = f.read()

    # Skip empty files
    if not content.strip():
        return False, "empty"

    # Parse YAML
    try:
        docs = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        return False, f"yaml error: {e}"

    # Filter out None docs (from empty documents)
    docs = [d for d in docs if d is not None]

    if not docs:
        return False, "no documents"

    # Check if already in new format (starts with list)
    if isinstance(docs[0], list):
        return False, "already converted"

    # Check if it's the old format with apiVersion/kind/spec
    new_queries = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue

        # Handle old format
        if "apiVersion" in doc and "kind" in doc and "spec" in doc:
            spec = doc.get("spec", {})
            if not spec:
                continue
            # Extract only the fields we want
            new_query = {}
            for field in KEEP_FIELDS:
                if field in spec:
                    new_query[field] = spec[field]
            if new_query:
                new_queries.append(new_query)
        # Handle case where doc is already a query spec (no wrapper)
        elif "name" in doc and "query" in doc:
            new_query = {}
            for field in KEEP_FIELDS:
                if field in doc:
                    new_query[field] = doc[field]
            if new_query:
                new_queries.append(new_query)

    if not new_queries:
        return False, "no queries found"

    if dry_run:
        print(f"Would convert: {filepath}")
        print(f"  {len(new_queries)} queries")
        return True, "would convert"

    # Write new format
    with open(filepath, "w") as f:
        yaml.dump(new_queries, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return True, f"converted {len(new_queries)} queries"


def find_query_files(lib_dir):
    """Find all .yml query files in lib/."""
    query_files = []
    for root, dirs, files in os.walk(lib_dir):
        # Only process files in queries directories
        if "/queries/" not in root and not root.endswith("/queries"):
            continue

        for filename in files:
            if filename.endswith((".yml", ".yaml")) and not filename.startswith("."):
                query_files.append(os.path.join(root, filename))

    return sorted(query_files)


def main():
    parser = argparse.ArgumentParser(description="Convert query files to GitOps format")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually modify files")
    args = parser.parse_args()

    if not os.path.isdir(LIB_DIR):
        print(f"ERROR: lib/ directory not found at {LIB_DIR}", file=sys.stderr)
        sys.exit(1)

    query_files = find_query_files(LIB_DIR)
    print(f"Found {len(query_files)} query files")

    converted = 0
    skipped = 0
    errors = 0

    for filepath in query_files:
        rel_path = os.path.relpath(filepath, SCRIPT_DIR)
        success, message = convert_file(filepath, args.dry_run)

        if success:
            converted += 1
            if not args.dry_run:
                print(f"Converted: {rel_path}")
        elif "already" in message or "empty" in message:
            skipped += 1
        else:
            errors += 1
            print(f"Error ({message}): {rel_path}", file=sys.stderr)

    print()
    print(f"Summary:")
    print(f"  Converted: {converted}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")

    if args.dry_run:
        print()
        print("This was a dry run. Run without --dry-run to actually convert files.")


if __name__ == "__main__":
    main()

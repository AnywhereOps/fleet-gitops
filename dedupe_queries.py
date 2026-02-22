#!/usr/bin/env python3
"""Deduplicate Fleet queries by name, comparing SQL to confirm true duplicates.

Strategy:
1. Find all queries with the same name
2. Compare SQL to confirm they're actually duplicates
3. Keep the best one based on source precedence
4. Delete the losers

Usage:
    python3 dedupe_queries.py [--dry-run]
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")

# Source precedence (lower = better)
SOURCE_PRECEDENCE = {
    "fleet-docs": 1,
    "fleet-internal": 2,
    "palantir-configuration": 3,
    "chainguard-defense-kit": 4,
    "osquery-packs": 5,
    "mitre-attck": 6,
    "osquery-configuration": 7,
    "palantir": 8,
    "imessage-detection": 9,
}

# Category precedence (lower = better)
CATEGORY_PRECEDENCE = {
    "general": 1,
    "compliance": 2,
    "detection": 3,
    "incident_response": 4,
    "incident-response": 4,
    "informational": 5,  # Usually duplicate of general
    "endpoints": 6,
    "performance": 7,
    "policy": 8,
}


def normalize_sql(sql):
    """Normalize SQL for comparison."""
    if not sql:
        return ""
    # Lowercase, collapse whitespace, remove trailing semicolons
    sql = sql.lower().strip()
    sql = re.sub(r'\s+', ' ', sql)
    sql = sql.rstrip(';')
    return sql


def sql_similarity(sql1, sql2):
    """Calculate similarity ratio between two SQL queries."""
    norm1 = normalize_sql(sql1)
    norm2 = normalize_sql(sql2)
    if not norm1 or not norm2:
        return 0.0
    return SequenceMatcher(None, norm1, norm2).ratio()


def get_source_and_category(filepath, lib_dir):
    """Extract source and category from file path."""
    rel_path = os.path.relpath(filepath, lib_dir)
    parts = rel_path.split(os.sep)

    # Structure: {platform}/{device_type}/queries/{source}/{category}/file.yml
    source = parts[3] if len(parts) > 3 else "unknown"
    category = parts[4] if len(parts) > 4 else "unknown"

    return source, category


def get_platform_device(filepath, lib_dir):
    """Extract platform and device type from file path."""
    rel_path = os.path.relpath(filepath, lib_dir)
    parts = rel_path.split(os.sep)

    platform = parts[0] if len(parts) > 0 else "unknown"
    device_type = parts[1] if len(parts) > 1 else "unknown"

    return platform, device_type


def score_query(filepath, lib_dir):
    """Score a query file (lower = better, should be kept)."""
    source, category = get_source_and_category(filepath, lib_dir)
    platform, device_type = get_platform_device(filepath, lib_dir)

    source_score = SOURCE_PRECEDENCE.get(source, 100)
    category_score = CATEGORY_PRECEDENCE.get(category, 100)

    # Prefer platform-specific over "all"
    platform_score = 0 if platform != "all" else 1

    # Combined score
    return (source_score * 100) + category_score + platform_score


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


def load_queries(filepath):
    """Load queries from a file."""
    with open(filepath, "r") as f:
        content = f.read()

    if not content.strip():
        return []

    try:
        data = yaml.safe_load(content)
        if isinstance(data, list):
            return data
        return []
    except yaml.YAMLError:
        return []


def save_queries(filepath, queries):
    """Save queries to a file."""
    with open(filepath, "w") as f:
        yaml.dump(queries, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Fleet queries")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually modify files")
    parser.add_argument("--similarity", type=float, default=0.85,
                        help="SQL similarity threshold (0-1, default 0.85)")
    args = parser.parse_args()

    if not os.path.isdir(LIB_DIR):
        print(f"ERROR: lib/ directory not found at {LIB_DIR}", file=sys.stderr)
        sys.exit(1)

    query_files = find_query_files(LIB_DIR)
    print(f"Found {len(query_files)} query files")

    # Collect all queries with their metadata
    # name -> [(filepath, query_index, query_dict, score)]
    name_to_queries = defaultdict(list)

    for filepath in query_files:
        queries = load_queries(filepath)
        score = score_query(filepath, LIB_DIR)

        for i, query in enumerate(queries):
            if isinstance(query, dict) and "name" in query:
                name = query["name"]
                name_to_queries[name].append({
                    "filepath": filepath,
                    "index": i,
                    "query": query,
                    "score": score,
                    "sql": query.get("query", ""),
                })

    # Find duplicates
    duplicates = {name: queries for name, queries in name_to_queries.items()
                  if len(queries) > 1}

    print(f"Found {len(duplicates)} query names with multiple occurrences")

    # Analyze and dedupe
    files_to_modify = defaultdict(list)  # filepath -> [indices to remove]
    kept_count = 0
    removed_count = 0
    different_sql_count = 0

    for name, occurrences in sorted(duplicates.items()):
        # Sort by score (lower = better)
        occurrences.sort(key=lambda x: x["score"])

        # Check SQL similarity
        winner = occurrences[0]
        losers = []
        different = []

        for occ in occurrences[1:]:
            similarity = sql_similarity(winner["sql"], occ["sql"])
            if similarity >= args.similarity:
                losers.append(occ)
            else:
                different.append((occ, similarity))

        if args.dry_run:
            winner_rel = os.path.relpath(winner["filepath"], SCRIPT_DIR)
            source, category = get_source_and_category(winner["filepath"], LIB_DIR)
            print(f"\n{name}:")
            print(f"  KEEP: {winner_rel} ({source}/{category})")

            for loser in losers:
                loser_rel = os.path.relpath(loser["filepath"], SCRIPT_DIR)
                source, category = get_source_and_category(loser["filepath"], LIB_DIR)
                sim = sql_similarity(winner["sql"], loser["sql"])
                print(f"  DELETE: {loser_rel} ({source}/{category}) [similarity: {sim:.0%}]")

            for diff, sim in different:
                diff_rel = os.path.relpath(diff["filepath"], SCRIPT_DIR)
                source, category = get_source_and_category(diff["filepath"], LIB_DIR)
                print(f"  DIFFERENT SQL: {diff_rel} ({source}/{category}) [similarity: {sim:.0%}]")

        # Mark losers for removal
        for loser in losers:
            files_to_modify[loser["filepath"]].append(loser["index"])
            removed_count += 1

        kept_count += 1
        different_sql_count += len(different)

    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  Unique names with duplicates: {len(duplicates)}")
    print(f"  Queries to keep: {kept_count}")
    print(f"  Queries to remove: {removed_count}")
    print(f"  Different SQL (kept both): {different_sql_count}")

    if args.dry_run:
        print(f"\nThis was a dry run. Run without --dry-run to apply changes.")
        return

    # Apply removals
    files_modified = 0
    files_deleted = 0

    for filepath, indices_to_remove in files_to_modify.items():
        queries = load_queries(filepath)

        # Remove in reverse order to preserve indices
        for index in sorted(indices_to_remove, reverse=True):
            if index < len(queries):
                del queries[index]

        if not queries:
            # Delete empty file
            os.remove(filepath)
            files_deleted += 1
            rel_path = os.path.relpath(filepath, SCRIPT_DIR)
            print(f"Deleted: {rel_path}")
        else:
            # Save modified file
            save_queries(filepath, queries)
            files_modified += 1
            rel_path = os.path.relpath(filepath, SCRIPT_DIR)
            print(f"Modified: {rel_path}")

    print(f"\nFiles modified: {files_modified}")
    print(f"Files deleted: {files_deleted}")
    print(f"Total queries removed: {removed_count}")


if __name__ == "__main__":
    main()

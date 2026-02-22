#!/usr/bin/env python3
"""Fix query issues: interval types and missing SQL."""

import os
import sys
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")


def find_query_files(lib_dir):
    query_files = []
    for root, dirs, files in os.walk(lib_dir):
        if "/queries/" not in root and not root.endswith("/queries"):
            continue
        for filename in files:
            if filename.endswith((".yml", ".yaml")) and not filename.startswith("."):
                query_files.append(os.path.join(root, filename))
    return sorted(query_files)


def main():
    query_files = find_query_files(LIB_DIR)
    print(f"Found {len(query_files)} query files")

    interval_fixed = 0
    no_sql_removed = 0
    files_modified = 0
    files_deleted = 0

    for filepath in query_files:
        with open(filepath, "r") as f:
            content = f.read()
        if not content.strip():
            continue

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            continue

        if not isinstance(data, list):
            continue

        modified = False
        new_queries = []

        for query in data:
            if not isinstance(query, dict):
                new_queries.append(query)
                continue

            # Remove queries without SQL
            sql = query.get("query", "")
            if not sql or not sql.strip():
                name = query.get("name", "unknown")
                print(f"NO SQL: {name}")
                no_sql_removed += 1
                modified = True
                continue

            # Fix interval type
            if "interval" in query and isinstance(query["interval"], str):
                try:
                    query["interval"] = int(query["interval"])
                    interval_fixed += 1
                    modified = True
                except ValueError:
                    pass

            new_queries.append(query)

        if modified:
            if not new_queries:
                os.remove(filepath)
                files_deleted += 1
                rel = os.path.relpath(filepath, SCRIPT_DIR)
                print(f"Deleted: {rel}")
            else:
                with open(filepath, "w") as f:
                    yaml.dump(new_queries, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                files_modified += 1

    print(f"\nInterval fixed: {interval_fixed}")
    print(f"No-SQL removed: {no_sql_removed}")
    print(f"Files modified: {files_modified}")
    print(f"Files deleted: {files_deleted}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate query paths for Fleet GitOps config files.

Scans lib/ directory and outputs the query paths needed for:
- default.yml: all 'both/' queries (shared by servers AND devices)
- teams/workstations.yml & dedicated-devices.yml: all 'devices/' queries
- teams/it-servers.yml: all 'servers/' queries

Usage:
    python3 generate_query_paths.py [--update]

    Without --update: prints the paths to stdout
    With --update: updates the config files directly
"""

import argparse
import os
import re
import sys

# Paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")
DEFAULT_YML = os.path.join(SCRIPT_DIR, "default.yml")
TEAMS_DIR = os.path.join(SCRIPT_DIR, "teams")


def find_query_files(lib_dir):
    """Find all .yml query files in lib/, grouped by device type."""
    both_queries = []
    devices_queries = []
    servers_queries = []

    for root, dirs, files in os.walk(lib_dir):
        # Skip non-query directories
        if "/queries/" not in root and not root.endswith("/queries"):
            continue

        rel_root = os.path.relpath(root, lib_dir)

        for filename in sorted(files):
            if not filename.endswith((".yml", ".yaml")):
                continue
            if filename.startswith("."):
                continue

            rel_path = os.path.join(rel_root, filename)

            # Determine device type from path
            if "/both/" in rel_path:
                both_queries.append(rel_path)
            elif "/devices/" in rel_path:
                devices_queries.append(rel_path)
            elif "/servers/" in rel_path:
                servers_queries.append(rel_path)
            else:
                # Queries not in both/devices/servers go to both
                both_queries.append(rel_path)

    return {
        "both": sorted(both_queries),
        "devices": sorted(devices_queries),
        "servers": sorted(servers_queries),
    }


def format_query_paths(paths, prefix=""):
    """Format paths as YAML list items."""
    if not paths:
        return ""
    lines = []
    for path in paths:
        full_path = os.path.join(prefix, "lib", path) if prefix else os.path.join("lib", path)
        lines.append(f"  - path: {full_path}")
    return "\n".join(lines)


def update_config_file(filepath, query_paths_yaml):
    """Update a config file's queries section."""
    with open(filepath, "r") as f:
        content = f.read()

    # Find the queries section and replace it
    # Pattern: queries: followed by optional list items, until next top-level key
    pattern = r"(queries:)\s*(?:\n(?:  - [^\n]+\n)*|\n)"

    if query_paths_yaml:
        replacement = f"queries:\n{query_paths_yaml}\n"
    else:
        replacement = "queries:\n"

    new_content = re.sub(pattern, replacement, content, count=1)

    with open(filepath, "w") as f:
        f.write(new_content)


def main():
    parser = argparse.ArgumentParser(description="Generate query paths for Fleet GitOps configs")
    parser.add_argument("--update", action="store_true", help="Update config files directly")
    args = parser.parse_args()

    if not os.path.isdir(LIB_DIR):
        print(f"ERROR: lib/ directory not found at {LIB_DIR}", file=sys.stderr)
        sys.exit(1)

    queries = find_query_files(LIB_DIR)

    print(f"Found {len(queries['both'])} 'both' queries")
    print(f"Found {len(queries['devices'])} 'devices' queries")
    print(f"Found {len(queries['servers'])} 'servers' queries")
    print()

    # Generate paths for each config
    default_paths = format_query_paths(queries["both"], prefix="")
    devices_paths = format_query_paths(queries["devices"], prefix="..")
    servers_paths = format_query_paths(queries["servers"], prefix="..")

    if args.update:
        # Update default.yml
        print(f"Updating {DEFAULT_YML}...")
        update_config_file(DEFAULT_YML, default_paths)

        # Update workstations.yml
        workstations_yml = os.path.join(TEAMS_DIR, "workstations.yml")
        if os.path.exists(workstations_yml):
            print(f"Updating {workstations_yml}...")
            update_config_file(workstations_yml, devices_paths)

        # Update dedicated-devices.yml
        dedicated_yml = os.path.join(TEAMS_DIR, "dedicated-devices.yml")
        if os.path.exists(dedicated_yml):
            print(f"Updating {dedicated_yml}...")
            update_config_file(dedicated_yml, devices_paths)

        # Update it-servers.yml
        servers_yml = os.path.join(TEAMS_DIR, "it-servers.yml")
        if os.path.exists(servers_yml):
            print(f"Updating {servers_yml}...")
            update_config_file(servers_yml, servers_paths)

        print("\nDone! Config files updated.")
    else:
        print("=" * 60)
        print("default.yml queries (both/):")
        print("=" * 60)
        if default_paths:
            print(default_paths)
        else:
            print("  (none)")

        print()
        print("=" * 60)
        print("workstations.yml & dedicated-devices.yml queries (devices/):")
        print("=" * 60)
        if devices_paths:
            print(devices_paths)
        else:
            print("  (none)")

        print()
        print("=" * 60)
        print("it-servers.yml queries (servers/):")
        print("=" * 60)
        if servers_paths:
            print(servers_paths)
        else:
            print("  (none)")

        print()
        print("Run with --update to write these paths to the config files.")


if __name__ == "__main__":
    main()

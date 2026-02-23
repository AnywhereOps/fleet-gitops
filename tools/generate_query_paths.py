#!/usr/bin/env python3
import os
import re
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
LIB_DIR = os.path.join(ROOT_DIR, "lib")

def find_query_files(lib_dir):
    both, devices, servers = [], [], []
    for root, dirs, files in os.walk(lib_dir):
        if "/queries/" not in root and not root.endswith("/queries"):
            continue
        rel_root = os.path.relpath(root, lib_dir)
        for f in sorted(files):
            if not f.endswith((".yml", ".yaml")) or f.startswith("."):
                continue
            rel_path = os.path.join(rel_root, f)
            if "/both/" in rel_path:
                both.append(rel_path)
            elif "/devices/" in rel_path:
                devices.append(rel_path)
            elif "/servers/" in rel_path:
                servers.append(rel_path)
            else:
                both.append(rel_path)
    return {"both": sorted(both), "devices": sorted(devices), "servers": sorted(servers)}

def format_paths(paths, prefix=""):
    return "\n".join(f"  - path: {os.path.join(prefix, 'lib', p) if prefix else os.path.join('lib', p)}" for p in paths)

def update_config(filepath, paths_yaml):
    with open(filepath) as f:
        content = f.read()
    pattern = r"(queries:)\s*(?:\n(?:  - [^\n]+\n)*|\n)"
    replacement = f"queries:\n{paths_yaml}\n" if paths_yaml else "queries:\n"
    new_content = re.sub(pattern, replacement, content, count=1)
    with open(filepath, "w") as f:
        f.write(new_content)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    queries = find_query_files(LIB_DIR)
    print(f"Found {len(queries['both'])} 'both' queries")
    print(f"Found {len(queries['devices'])} 'devices' queries")
    print(f"Found {len(queries['servers'])} 'servers' queries")

    # Combine device and both queries for device teams
    device_queries = sorted(queries["devices"] + queries["both"])
    # Combine server and both queries for server teams
    server_queries = sorted(queries["servers"] + queries["both"])

    print(f"Device teams will get {len(device_queries)} queries (devices + both)")
    print(f"Server teams will get {len(server_queries)} queries (servers + both)")

    if args.update:
        # Device teams get devices + both
        for team in ["workstations.yml", "dedicated-devices.yml"]:
            path = os.path.join(ROOT_DIR, "teams", team)
            if os.path.exists(path):
                update_config(path, format_paths(device_queries, ".."))
                print(f"Updated {team}")
        # Server team gets servers + both
        servers_path = os.path.join(ROOT_DIR, "teams", "it-servers.yml")
        if os.path.exists(servers_path):
            update_config(servers_path, format_paths(server_queries, ".."))
            print("Updated it-servers.yml")
        print("\nDone!")

if __name__ == "__main__":
    main()

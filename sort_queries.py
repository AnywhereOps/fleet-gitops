#!/usr/bin/env python3
"""Sort and convert query sources (SQL files, YAML/JSON) into Fleet gitops
YAML format, organized by platform and category/purpose.

Auto-discovers query source directories in the repo and prompts for output
folder names when new sources are found.

Uses multiple detection strategies for platform and category, falling back
gracefully when standard fields aren't present."""

import argparse
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip3 install pyyaml")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Custom YAML representer to force literal block style for multi-line strings
# ---------------------------------------------------------------------------
class LiteralStr(str):
    pass


def _literal_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(LiteralStr, _literal_representer)


# ---------------------------------------------------------------------------
# Config file for remembering folder name mappings
# ---------------------------------------------------------------------------
CONFIG_FILE = ".sort_queries.json"


def load_config(repo_root):
    """Load saved source -> output folder name mappings."""
    config_path = os.path.join(repo_root, CONFIG_FILE)
    if os.path.isfile(config_path):
        with open(config_path, "r") as f:
            return json.load(f)
    return {}


def save_config(repo_root, config):
    """Save source -> output folder name mappings."""
    config_path = os.path.join(repo_root, CONFIG_FILE)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"\n  Saved folder mappings to {CONFIG_FILE}")


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------
SKIP_DIRS = {"lib", ".git", "__pycache__", "node_modules", ".github", "teams"}


def discover_sources(repo_root):
    """Find directories containing query files (.sql, .yml, .yaml, .json, .conf)."""
    sources = []

    for entry in sorted(os.listdir(repo_root)):
        full_path = os.path.join(repo_root, entry)
        if not os.path.isdir(full_path):
            continue
        if entry in SKIP_DIRS or entry.startswith("."):
            continue

        extensions = set()
        file_count = 0
        for root, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {
                "images", "node_modules", "__pycache__"
            }]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in (".sql", ".yml", ".yaml", ".json", ".conf"):
                    fpath = os.path.join(root, f)
                    if _is_query_file(fpath, ext):
                        file_count += 1
                        extensions.add(ext)

        if file_count > 0:
            if ".sql" in extensions:
                source_type = "sql" if len(extensions) == 1 else "mixed"
            elif ".conf" in extensions:
                source_type = "conf"
            elif ".json" in extensions:
                source_type = "json"
            else:
                source_type = "yaml"

            sources.append({
                "path": full_path,
                "name": entry,
                "type": source_type,
                "file_count": file_count,
                "extensions": sorted(extensions),
            })

    return sources


def _is_query_file(filepath, ext):
    """Quick heuristic to check if a file contains query data."""
    try:
        with open(filepath, "r", errors="ignore") as f:
            head = f.read(3000)
    except (IOError, OSError):
        return False

    if ext == ".sql":
        return "SELECT" in head.upper()

    if ext in (".yml", ".yaml"):
        return ("query:" in head or "name:" in head) and (
            "SELECT" in head.upper() or "spec:" in head or "platform:" in head
        )

    if ext == ".json" or ext == ".conf":
        return '"query"' in head and ('"name"' in head or '"SELECT' in head.upper())

    return False


# ---------------------------------------------------------------------------
# Platform detection - multi-strategy
# ---------------------------------------------------------------------------
PLATFORM_MAP = {
    "darwin": ("macos", "darwin"),
    "macos": ("macos", "darwin"),
    "osx": ("macos", "darwin"),
    "mac": ("macos", "darwin"),
    "linux": ("linux", "linux"),
    "centos": ("linux", "linux"),
    "ubuntu": ("linux", "linux"),
    "rhel": ("linux", "linux"),
    "debian": ("linux", "linux"),
    "windows": ("windows", "windows"),
    "win": ("windows", "windows"),
    "posix": ("all", None),
    "chrome": ("all", "chrome"),
    "freebsd": ("all", "freebsd"),
}

# Tables that indicate specific platforms
PLATFORM_TABLES = {
    "macos": [
        "launchd", "alf", "app_schemes", "apps", "crashes", "disk_events",
        "event_taps", "gatekeeper", "homebrew", "ioreg", "keychain", "mdfind",
        "nvram", "plist", "safari", "sip_config", "xprotect", "authorization",
        "account_policy_data", "es_process_events", "unified_log",
    ],
    "linux": [
        "systemd", "apt_sources", "deb_packages", "rpm_packages", "yum_sources",
        "iptables", "selinux", "sysctl", "memory_map", "kernel_modules",
        "kernel_info", "md_devices", "lxd", "shadow",
    ],
    "windows": [
        "registry", "windows_events", "windows_security", "bitlocker",
        "chocolatey", "ie_extensions", "pipes", "scheduled_tasks",
        "services", "shared_resources", "wmi", "powershell", "logon_sessions",
        "ntfs", "prefetch", "userassist", "autoexec", "drivers", "programs",
    ],
}


def detect_platform(spec, filename=None, filepath=None, query_sql=None):
    """Detect platform using multiple strategies. Returns (lib_subdir, yaml_platform)."""

    # Strategy 1: Direct platform field in spec
    platform_str = spec.get("platform", "") if isinstance(spec, dict) else ""
    if platform_str:
        return _resolve_platform_string(platform_str)

    # Strategy 2: Check filename for platform hints
    if filename:
        fn_lower = filename.lower()
        for hint, (lib_dir, plat) in [
            ("-macos", ("macos", "darwin")),
            ("_macos", ("macos", "darwin")),
            ("-darwin", ("macos", "darwin")),
            ("_darwin", ("macos", "darwin")),
            ("-osx", ("macos", "darwin")),
            ("-linux", ("linux", "linux")),
            ("_linux", ("linux", "linux")),
            ("-windows", ("windows", "windows")),
            ("_windows", ("windows", "windows")),
            ("-win", ("windows", "windows")),
        ]:
            if hint in fn_lower:
                return (lib_dir, plat)

    # Strategy 3: Check directory path for platform hints
    if filepath:
        path_lower = filepath.lower()
        # Check for platform-specific directories (common in osquery configs)
        # Patterns like: /Endpoints/MacOS/, /Servers/Linux/, /Windows/, etc.
        for hint, (lib_dir, plat) in [
            ("/macos/", ("macos", "darwin")),
            ("/darwin/", ("macos", "darwin")),
            ("/osx/", ("macos", "darwin")),
            ("/linux/", ("linux", "linux")),
            ("/windows/", ("windows", "windows")),
            ("/win/", ("windows", "windows")),
            # Also check filename patterns in path
            ("endpoints/macos", ("macos", "darwin")),
            ("endpoints/windows", ("windows", "windows")),
            ("servers/linux", ("linux", "linux")),
            ("servers/macos", ("macos", "darwin")),
            ("servers/windows", ("windows", "windows")),
        ]:
            if hint in path_lower:
                return (lib_dir, plat)

    # Strategy 4: Analyze query SQL for platform-specific tables
    if query_sql:
        query_lower = query_sql.lower()
        platform_scores = {"macos": 0, "linux": 0, "windows": 0}

        for platform, tables in PLATFORM_TABLES.items():
            for table in tables:
                # Look for table references (FROM table, JOIN table, etc.)
                if re.search(rf"\b{table}\b", query_lower):
                    platform_scores[platform] += 1

        # If one platform has significantly more matches, use it
        max_score = max(platform_scores.values())
        if max_score > 0:
            winners = [p for p, s in platform_scores.items() if s == max_score]
            if len(winners) == 1:
                plat = winners[0]
                return (plat, "darwin" if plat == "macos" else plat)

    # Default: all platforms
    return ("all", None)


def _resolve_platform_string(platform_str):
    """Resolve a platform string to (lib_subdir, yaml_platform)."""
    normalized = platform_str.strip().lower()

    if normalized in PLATFORM_MAP:
        return PLATFORM_MAP[normalized]

    # Multi-platform (e.g. "darwin, linux")
    platforms = [p.strip() for p in normalized.split(",")]
    if len(platforms) > 1:
        return ("all", platform_str.strip())

    # Unknown -> all
    return ("all", platform_str.strip() if platform_str.strip() else None)


# ---------------------------------------------------------------------------
# Category/Purpose detection - multi-strategy
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "detection": [
        "detect", "alert", "suspicious", "malicious", "threat", "attack",
        "rootkit", "malware", "backdoor", "trojan", "worm", "exploit",
        "unauthorized", "anomaly", "intrusion", "c2", "command-and-control",
        "exfil", "lateral", "privilege", "escalation", "persistence",
        "evasion", "credential", "yara",
    ],
    "incident-response": [
        "incident", "response", "forensic", "investigation", "artifact",
        "evidence", "timeline", "postmortem", "ir_", "ir-",
    ],
    "compliance": [
        "compliance", "audit", "policy", "benchmark", "cis_", "cis-",
        "stig", "hipaa", "pci", "sox", "gdpr", "nist", "fedramp",
    ],
    "inventory": [
        "inventory", "asset", "installed", "packages", "software",
        "hardware", "snapshot", "baseline", "enumerate",
    ],
    "performance": [
        "performance", "perf", "cpu", "memory", "disk", "resource",
        "utilization", "metrics", "monitoring",
    ],
    "vulnerability": [
        "vulnerability", "vuln", "cve", "patch", "update", "outdated",
        "version", "exploit",
    ],
}


def detect_category(spec, filename=None, filepath=None, query_name=None):
    """Detect category/purpose using multiple strategies."""

    # Strategy 1: Direct purpose field
    if isinstance(spec, dict):
        purpose = spec.get("purpose", "")
        if purpose:
            return _normalize_category(purpose)

        # Strategy 2: Check tags field
        tags = spec.get("tags", [])
        if isinstance(tags, str):
            tags = tags.split()
        for tag in tags:
            cat = _match_category_keywords(tag.lower())
            if cat != "general":
                return cat

    # Strategy 3: Check filename (including parent pack file name)
    if filename:
        # Strip extension and check
        basename = os.path.splitext(filename)[0].lower()
        cat = _match_category_keywords(basename)
        if cat != "general":
            return cat
        # Also check for specific pack name patterns
        if "rootkit" in basename:
            return "detection"
        if "compliance" in basename:
            return "compliance"
        if "registry" in basename and "monitor" in basename:
            return "detection"
        if "security" in basename:
            return "detection"

    # Strategy 4: Check directory path
    if filepath:
        path_parts = filepath.lower().split(os.sep)
        for part in path_parts:
            cat = _match_category_keywords(part)
            if cat != "general":
                return cat
            # Also check for common directory patterns
            if part in ("detection", "detections"):
                return "detection"
            if part in ("incident_response", "incident-response", "ir"):
                return "incident-response"
            if part in ("compliance", "policy", "policies"):
                return "compliance"
            if part in ("inventory", "assets"):
                return "inventory"
            if part in ("vulnerability", "vulnerabilities", "vulns"):
                return "vulnerability"
            if part in ("endpoints", "endpoint"):
                return "endpoints"
            if part in ("servers", "server"):
                return "servers"
            if part == "packs":
                continue  # Skip "packs" - look for better category

    # Strategy 5: Check query name
    if query_name:
        cat = _match_category_keywords(query_name.lower())
        if cat != "general":
            return cat

    # Default
    return "general"


def _normalize_category(category_str):
    """Normalize category string to standard form."""
    cat = category_str.strip().lower().replace(" ", "-").replace("_", "-")

    # Map common variations
    mappings = {
        "informational": "general",
        "info": "general",
        "detection": "detection",
        "detect": "detection",
        "incident-response": "incident-response",
        "incident_response": "incident-response",
        "ir": "incident-response",
        "compliance": "compliance",
        "policy": "compliance",
        "inventory": "inventory",
        "asset": "inventory",
        "performance": "performance",
        "perf": "performance",
        "vulnerability": "vulnerability",
        "vuln": "vulnerability",
    }

    return mappings.get(cat, cat if cat else "general")


def _match_category_keywords(text):
    """Match text against category keywords."""
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return category
    return "general"


# ---------------------------------------------------------------------------
# SQL file parser
# ---------------------------------------------------------------------------
def parse_sql_file(filepath):
    """Parse a .sql file, extracting metadata from comments and query body."""
    with open(filepath, "r") as f:
        lines = f.readlines()

    description = ""
    platform = None
    interval = None
    tags = []
    references = []
    false_positives = []
    current_section = None
    query_lines = []
    in_metadata = True
    desc_lines = []

    for line in lines:
        stripped = line.rstrip()

        if in_metadata and stripped.startswith("--"):
            content = stripped.lstrip("-").strip()

            if content.lower().startswith("tags:"):
                tags = content[5:].strip().split()
                current_section = None
                continue
            if content.lower().startswith("platform:"):
                platform = content[9:].strip()
                current_section = None
                continue
            if content.lower().startswith("interval:"):
                try:
                    interval = int(content[9:].strip())
                except ValueError:
                    pass
                current_section = None
                continue
            if content.lower().startswith("references:"):
                current_section = "references"
                continue
            if content.lower().startswith("false positive"):
                current_section = "false_positives"
                continue

            if current_section and content.startswith("* "):
                item = content[2:].strip()
                if current_section == "references":
                    references.append(item)
                elif current_section == "false_positives":
                    false_positives.append(item)
                continue

            if not content:
                current_section = None
                continue

            if current_section is None and not description:
                desc_lines.append(content)
                continue
            elif current_section is None and desc_lines:
                desc_lines.append(content)
                continue

        elif in_metadata and not stripped.startswith("--"):
            in_metadata = False
            description = " ".join(desc_lines)
            query_lines.append(line.rstrip("\n"))
        else:
            query_lines.append(line.rstrip("\n"))

    if not description:
        description = " ".join(desc_lines)

    while query_lines and not query_lines[-1].strip():
        query_lines.pop()
    while query_lines and not query_lines[0].strip():
        query_lines.pop(0)

    return {
        "description": description,
        "platform": platform,
        "interval": interval,
        "tags": tags,
        "references": references,
        "false_positives": false_positives,
        "query": "\n".join(query_lines),
    }


# ---------------------------------------------------------------------------
# YAML file parser (multi-document)
# ---------------------------------------------------------------------------
def parse_yaml_file(filepath):
    """Parse a multi-document YAML file, yielding (kind, spec, filepath) for each doc."""
    with open(filepath, "r") as f:
        content = f.read()

    raw_docs = re.split(r"^---\s*$", content, flags=re.MULTILINE)

    for i, raw_doc in enumerate(raw_docs):
        raw_doc = raw_doc.strip()
        if not raw_doc or raw_doc.startswith("#"):
            continue
        try:
            doc = yaml.safe_load(raw_doc)
        except yaml.YAMLError as e:
            name_match = re.search(r"name:\s*(.+)", raw_doc)
            name_hint = name_match.group(1).strip() if name_match else f"document #{i}"
            print(f"  WARN: Skipping malformed YAML entry ({name_hint}): {e}")
            continue
        if doc is None or not isinstance(doc, dict):
            continue
        kind = doc.get("kind", "query")
        spec = doc.get("spec", {})
        if spec and spec.get("name") and spec.get("query"):
            yield kind, spec, filepath


# ---------------------------------------------------------------------------
# JSON/CONF file parser
# ---------------------------------------------------------------------------
def parse_json_conf_file(filepath):
    """Parse a JSON or osquery .conf file containing query definitions."""
    with open(filepath, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  WARN: Skipping malformed JSON ({filepath}): {e}")
            return

    # Handle osquery pack format: {"queries": {"name": {"query": "...", ...}}}
    if "queries" in data and isinstance(data["queries"], dict):
        for name, qdef in data["queries"].items():
            if isinstance(qdef, dict) and qdef.get("query"):
                spec = {"name": name, **qdef}
                yield "query", spec, filepath
        return

    # Handle array format: [{"name": "...", "query": "..."}]
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and entry.get("name") and entry.get("query"):
                yield "query", entry, filepath
        return

    # Handle single query object
    if isinstance(data, dict) and data.get("name") and data.get("query"):
        yield "query", data, filepath


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def derive_query_name(filename, prefix=None):
    """Convert filename to a human-readable query name."""
    stem = os.path.splitext(filename)[0]
    stem = re.sub(r"^\d+-", "", stem)
    name = stem.replace("-", " ").replace("_", " ").title()
    if prefix:
        return f"{prefix} - {name}"
    return name


def slugify(name):
    """Convert a query name to a kebab-case filename slug."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9\s\-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug[:80]  # Limit filename length


def generate_yaml_doc(kind, spec):
    """Generate a YAML document string for a single query."""
    if "query" in spec and isinstance(spec["query"], str) and "\n" in spec["query"]:
        spec["query"] = LiteralStr(spec["query"])
    if "powershell" in spec and isinstance(spec.get("powershell"), str) and "\n" in spec["powershell"]:
        spec["powershell"] = LiteralStr(spec["powershell"])

    doc = {"apiVersion": "v1", "kind": kind, "spec": spec}

    output = yaml.dump(
        doc,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=200,
    )
    return "---\n" + output


# ---------------------------------------------------------------------------
# Process a SQL source directory
# ---------------------------------------------------------------------------
def process_sql_source(source_dir, target_dir, output_folder, prefix, dry_run):
    """Process a directory of SQL query files."""
    stats = {"total": 0, "converted": 0, "by_platform": {}, "by_category": {}}
    skip_dirs = {"fragments", ".git", ".github", "images"}

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel_root = os.path.relpath(root, source_dir)

        for filename in sorted(files):
            if not filename.endswith(".sql"):
                continue

            stats["total"] += 1
            filepath = os.path.join(root, filename)
            parsed = parse_sql_file(filepath)

            if not parsed["query"]:
                print(f"  SKIP (no query): {filepath}")
                continue

            # Smart platform detection
            lib_subdir, yaml_platform = detect_platform(
                {"platform": parsed["platform"], "tags": parsed["tags"]},
                filename=filename,
                filepath=filepath,
                query_sql=parsed["query"]
            )

            # Smart category detection
            category = detect_category(
                {"tags": parsed["tags"]},
                filename=filename,
                filepath=filepath,
                query_name=derive_query_name(filename, None)
            )

            # Use directory structure if it looks like a category
            if rel_root != ".":
                dir_cat = detect_category({}, filepath=rel_root)
                if dir_cat != "general":
                    category = rel_root  # Preserve original structure

            name = derive_query_name(filename, prefix)
            spec = {"name": name}
            if yaml_platform:
                spec["platform"] = yaml_platform
            spec["description"] = parsed["description"] or name
            if "\n" in parsed["query"]:
                spec["query"] = LiteralStr(parsed["query"] + "\n")
            else:
                spec["query"] = parsed["query"]
            spec["interval"] = parsed["interval"] or 3600
            spec["logging"] = "snapshot"
            spec["observer_can_run"] = True
            spec["automations_enabled"] = False
            spec["discard_data"] = False

            out_filename = slugify(os.path.splitext(filename)[0]) + ".yml"
            out_dir = os.path.join(target_dir, lib_subdir, "queries", output_folder, category)
            out_path = os.path.join(out_dir, out_filename)

            yaml_content = generate_yaml_doc("query", spec)

            if dry_run:
                print(f"  [DRY-RUN] {filepath}")
                print(f"            -> {out_path}")
            else:
                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, "w") as f:
                    f.write(yaml_content)
                print(f"  {filepath} -> {out_path}")

            stats["converted"] += 1
            stats["by_platform"][lib_subdir] = stats["by_platform"].get(lib_subdir, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

    return stats


# ---------------------------------------------------------------------------
# Process a YAML/JSON/CONF source
# ---------------------------------------------------------------------------
def process_structured_source(source_path, target_dir, output_folder, dry_run):
    """Process YAML, JSON, or .conf query files.

    Prefers Fleet/ subdirectory over Classic/ when both exist.
    Prefers .yaml/.yml over .conf when duplicates exist.
    """
    stats = {"total": 0, "converted": 0, "by_platform": {}, "by_category": {}}

    files_to_process = []
    if os.path.isfile(source_path):
        files_to_process.append(source_path)
    elif os.path.isdir(source_path):
        # Check for Fleet/ subdirectory - prefer it over Classic/
        fleet_path = os.path.join(source_path, "Fleet")
        classic_path = os.path.join(source_path, "Classic")

        if os.path.isdir(fleet_path):
            # Use Fleet/ directory preferentially
            search_path = fleet_path
            print(f"  (Using Fleet/ subdirectory)")
        elif os.path.isdir(classic_path):
            search_path = classic_path
            print(f"  (Using Classic/ subdirectory)")
        else:
            search_path = source_path

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                # Prefer YAML over conf
                if ext in (".yml", ".yaml"):
                    files_to_process.append(os.path.join(root, f))
                elif ext in (".json", ".conf"):
                    # Only add .conf if no corresponding .yaml exists
                    yaml_path = os.path.join(root, os.path.splitext(f)[0] + ".yaml")
                    yml_path = os.path.join(root, os.path.splitext(f)[0] + ".yml")
                    if not os.path.exists(yaml_path) and not os.path.exists(yml_path):
                        files_to_process.append(os.path.join(root, f))

    for filepath in files_to_process:
        ext = os.path.splitext(filepath)[1].lower()

        if ext in (".json", ".conf"):
            entries = list(parse_json_conf_file(filepath))
        else:
            entries = list(parse_yaml_file(filepath))

        for kind, spec, src_filepath in entries:
            stats["total"] += 1

            query_sql = spec.get("query", "")

            # Smart platform detection
            lib_subdir, yaml_platform = detect_platform(
                spec,
                filename=os.path.basename(src_filepath),
                filepath=src_filepath,
                query_sql=query_sql
            )

            # Smart category detection
            category = detect_category(
                spec,
                filename=os.path.basename(src_filepath),
                filepath=src_filepath,
                query_name=spec.get("name", "")
            )

            # Build output spec preserving original fields
            out_spec = {}
            key_order = [
                "name", "platform", "description", "query", "powershell", "bash",
                "purpose", "tags", "discovery", "contributors", "remediation",
                "interval", "logging", "observer_can_run", "automations_enabled",
                "discard_data", "labels_include_any", "snapshot", "value",
            ]
            for key in key_order:
                if key in spec:
                    val = spec[key]
                    if key == "query" and isinstance(val, str) and "\n" in val:
                        val = LiteralStr(val)
                    if key == "powershell" and isinstance(val, str) and "\n" in val:
                        val = LiteralStr(val)
                    out_spec[key] = val
            for key, val in spec.items():
                if key not in out_spec:
                    out_spec[key] = val

            # Add detected platform if not present
            if yaml_platform and "platform" not in out_spec:
                out_spec["platform"] = yaml_platform

            query_name = spec.get("name", "unnamed")
            out_filename = slugify(query_name) + ".yml"
            out_dir = os.path.join(target_dir, lib_subdir, "queries", output_folder, category)
            out_path = os.path.join(out_dir, out_filename)

            yaml_content = generate_yaml_doc(kind, out_spec)

            if dry_run:
                print(f"  [DRY-RUN] {query_name} ({lib_subdir}/{category})")
                print(f"            -> {out_path}")
            else:
                os.makedirs(out_dir, exist_ok=True)
                with open(out_path, "w") as f:
                    f.write(yaml_content)
                print(f"  {query_name} -> {out_path}")

            stats["converted"] += 1
            stats["by_platform"][lib_subdir] = stats["by_platform"].get(lib_subdir, 0) + 1
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

    return stats


# ---------------------------------------------------------------------------
# Print stats
# ---------------------------------------------------------------------------
def print_stats(stats, source_type):
    """Print summary statistics."""
    print(f"\n  Total found: {stats['total']}")
    print(f"  Converted:   {stats['converted']}")
    print(f"  By platform:")
    for plat, count in sorted(stats["by_platform"].items()):
        print(f"    lib/{plat}: {count}")
    print(f"  By category:")
    for cat, count in sorted(stats["by_category"].items()):
        print(f"    {cat}: {count}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Auto-discover and sort query sources into Fleet gitops YAML."
    )
    parser.add_argument(
        "--target",
        default="./lib",
        help="Path to lib/ output directory (default: ./lib)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repo root for source discovery (default: .)",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Name prefix for SQL-sourced queries (default: none)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview output without writing files",
    )
    parser.add_argument(
        "--reset-config",
        action="store_true",
        help="Reset saved folder name mappings and re-prompt",
    )
    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo_root)

    if args.reset_config:
        config = {}
    else:
        config = load_config(repo_root)

    print("Scanning for query sources...\n")
    sources = discover_sources(repo_root)

    if not sources:
        print("No query sources found.")
        return

    print(f"Found {len(sources)} query source(s):\n")
    for i, src in enumerate(sources, 1):
        saved_name = config.get(src["name"], {}).get("output_folder")
        status = f" -> {saved_name}" if saved_name else " (NEW)"
        print(f"  {i}. {src['name']}/")
        print(f"     Type: {src['type']} | Files: {src['file_count']} | Extensions: {', '.join(src['extensions'])}{status}")

    print()

    config_changed = False
    for src in sources:
        if src["name"] not in config:
            default_name = slugify(src["name"])
            user_input = input(
                f"  Output folder name for '{src['name']}'? "
                f"[default: {default_name}]: "
            ).strip()
            output_folder = user_input if user_input else default_name

            src_prefix = args.prefix
            if src["type"] in ("sql", "mixed"):
                prefix_input = input(
                    f"  Query name prefix for '{src['name']}'? "
                    f"[default: {args.prefix or 'none'}]: "
                ).strip()
                if prefix_input:
                    src_prefix = prefix_input

            config[src["name"]] = {
                "output_folder": output_folder,
                "source_type": src["type"],
                "prefix": src_prefix,
            }
            config_changed = True

    if config_changed and not args.dry_run:
        save_config(repo_root, config)

    print()

    for src in sources:
        src_config = config[src["name"]]
        output_folder = src_config["output_folder"]
        source_type = src_config.get("source_type", src["type"])
        src_prefix = src_config.get("prefix", args.prefix)

        print("=" * 60)
        print(f"Processing: {src['name']}/ -> {output_folder}/")
        print("=" * 60)

        if source_type == "sql":
            stats = process_sql_source(
                src["path"], args.target, output_folder, src_prefix, args.dry_run
            )
            print_stats(stats, "sql")

        elif source_type in ("yaml", "json", "conf"):
            stats = process_structured_source(
                src["path"], args.target, output_folder, args.dry_run
            )
            print_stats(stats, "yaml")

        elif source_type == "mixed":
            print("\n  --- SQL files ---")
            sql_stats = process_sql_source(
                src["path"], args.target, output_folder, src_prefix, args.dry_run
            )
            print_stats(sql_stats, "sql")

            print("\n  --- YAML/JSON files ---")
            yaml_stats = process_structured_source(
                src["path"], args.target, output_folder, args.dry_run
            )
            print_stats(yaml_stats, "yaml")

        print()

    if args.dry_run:
        print("** DRY RUN - no files were written **")


if __name__ == "__main__":
    main()

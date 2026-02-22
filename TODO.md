# Fleet GitOps TODO

## Completed

### Query Format Migration
- [x] Converted 1,546 queries from old `apiVersion/kind/spec` format to new Fleet GitOps list format
- [x] Created `convert_query_format.py` script for future conversions

### Deduplication
- [x] Removed 694 duplicate queries (same name, same/similar SQL)
- [x] Created `dedupe_queries.py` script with source precedence logic
- [x] Precedence: fleet-docs > palantir-configuration > chainguard > osquery-packs > mitre-attck

### YARA Queries
- [x] Moved 16 YARA queries to `yara/` directory (same structure)
- [x] YARA queries contain `$variables` that Fleet interprets as env vars
- [x] Created `move_yara_queries.py` script

### Query Fixes
- [x] Fixed 80 interval fields (string → integer type)
- [x] Removed 9 queries with no SQL field
- [x] Created `fix_query_issues.py` script

### On-Demand Queries
- [x] Removed `interval` from 504 queries
- [x] All queries are now on-demand only (not scheduled)

## TODO

### YARA Configuration
- [ ] Set up `agent_options.yara` for remote YARA rules
- [ ] Extract YARA rules from queries into `.yar` files
- [ ] Configure `org_settings.yara_rules` in default.yml
- [ ] Update queries in `yara/` to use `sigurl` instead of `sigrule`
- [ ] Move YARA queries back to `lib/` once configured

### Query Organization
- [ ] Review query categories and consolidate if needed
- [ ] Add descriptions to queries missing them
- [ ] Consider adding tags for easier filtering in Fleet UI

### Scheduled Queries
- [ ] Identify critical queries that should run on a schedule
- [ ] Add `interval` back to those specific queries
- [ ] Consider different intervals for different query types

## Scripts

| Script | Purpose |
|--------|---------|
| `generate_query_paths.py` | Regenerate query paths in config files |
| `convert_query_format.py` | Convert old format to new list format |
| `dedupe_queries.py` | Find and remove duplicate queries |
| `move_yara_queries.py` | Move YARA queries to separate directory |
| `fix_query_issues.py` | Fix interval types and remove empty queries |
| `sort_queries.py` | Sort queries into platform/device-type structure |

## Current Stats

- **830 queries** in lib/ (561 both + 108 devices + 161 servers)
- **16 YARA queries** in yara/ (pending proper YARA config)

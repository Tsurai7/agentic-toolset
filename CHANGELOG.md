# Changelog

All notable changes to this config are recorded here. Newest first.

## [0.2.0] — 2026-06-24

### Fixed
- Corrected the source-of-truth path in all docs and the generated `CLAUDE.md`
  stub: `~/Documents/GitHub/personal/agentic` → `agentic-cfg` (the old path did
  not exist, so install instructions and the memory pointer were broken).

### Changed
- Pinned the GitNexus MCP server to `gitnexus@1.6.8` instead of `@latest`, for
  reproducible, supply-chain-safe installs.
- Hardened `merge-mcp.py`: malformed JSON fragments now fail with the offending
  file path instead of a raw traceback.

### Added
- Tool-precedence section in `AGENTS.md` resolving overlaps between GitNexus,
  lean-ctx `ctx_*` tools, and the `rtk` prefix (no double-wrapping; graph vs text).
- `evals/` — behavioral eval harness with one case per global default and an
  LLM-judge runner (`evals/run.py`), dry by default.
- `bin/ci-check.sh` running shell, JSON, YAML, SKILL.md frontmatter, and
  eval-parse checks. (A matching GitHub Actions workflow exists locally but is
  not enabled yet — pushing it needs a token with the `workflow` scope.)
- `bin/doctor.sh --deep` validates generated MCP JSON and reports the pinned
  GitNexus version.

## [0.1.0] — 2026-05-28

### Added
- Initial bootstrap: portable agentic config for Cursor and Claude — skills,
  `AGENTS.md`, MCP integration (GitNexus), plugin catalog, and install/doctor
  scripts.

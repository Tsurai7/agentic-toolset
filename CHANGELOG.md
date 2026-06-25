# Changelog

All notable changes to this config are recorded here. Newest first.

## [0.11.0] — 2026-06-25

### Added
- `prompt-caching-playbook` skill (with `references/` for Anthropic/OpenAI/Gemini/
  vLLM, OSS agents, benchmarks): structuring prompts for prompt-cache reuse. Added
  to the AGENTS.md skills inventory.
- Eval coverage: three positive trigger cases, two negative (over-trigger guard)
  cases, and one content/anti-pattern case under `evals/cases/`. `evals/README.md`
  documents the skill-trigger case pattern.
- `bin/ci-check.sh` now verifies that `references/*.md` links in any SKILL.md
  resolve (no dangling reference files).

### Changed
- Trimmed the skill's `description` (~250 → ~60 words) for trigger precision and a
  leaner skill index, keeping the high-signal keywords and Russian phrases.
- Added a freshness disclaimer: the playbook's structural rules are stable, but its
  pricing/threshold/TTL/model-ID numbers are point-in-time (2026-05) and must be
  verified against live provider docs before being quoted — per the honesty
  principle.

## [0.10.0] — 2026-06-24

### Added
- no-mistakes integration: `integrations/no-mistakes/README.md` documents the
  clean-PR gate (local git proxy + AI pipeline). `bin/bootstrap.sh` installs the
  binary via `go install`, `doctor.sh --deep` checks for it, and the workflows
  decision flow distinguishes the full gated PR (`no-mistakes`) from a plain PR
  (`create-pr`). The tool-generated `/no-mistakes` skill lands in `core/skills/`
  via the skills symlink and is gitignored (the binary owns it, per-repo
  `no-mistakes init`).

## [0.9.0] — 2026-06-24

### Added
- `core/principles/honesty.md` — honesty-and-transparency principle: every claim
  must be backed by cited evidence, fact separated from inference, outcomes
  reported faithfully (including failures and unverified parts), and no hidden
  side effects.

## [0.8.0] — 2026-06-24

### Added
- `core/principles/` — always-on behavioral principles layer. Added the Karpathy
  guidelines (think before coding, simplicity, surgical changes, goal-driven
  execution), adapted from multica-ai/andrej-karpathy-skills (MIT). Principles are
  concatenated into the generated `CLAUDE.md` and rendered to `alwaysApply` Cursor
  rules by the installers. `core/principles/README.md` documents the
  principle-vs-skill decision.

## [0.7.0] — 2026-06-24

### Added
- `ast-grep` skill and global default: agents search source code structurally
  with `ast-grep` (AST patterns) instead of regex grep. Wired into the AGENTS.md
  tool-precedence table, installed by `bin/bootstrap.sh`, checked by
  `doctor.sh --deep`, and covered by an eval case. grep/`ctx_search` remain the
  fallback for non-code text and unsupported languages.

## [0.6.0] — 2026-06-24

### Added
- `bin/bootstrap.sh` — one command installs every dependency (Homebrew, git,
  python3, node, gh, rtk, lean-ctx) and then runs the installer + doctor.
- Claude-side lean-ctx: `providers/claude/settings.hooks.json` (hooks +
  permissions) merged into `~/.claude/settings.json` by the new
  `providers/shared/merge-settings.py`, which preserves machine-local `env`
  (e.g. `ANTHROPIC_BASE_URL`).

### Changed
- De-hardcoded machine paths. `merge-mcp.py` now resolves `npx` / `lean-ctx` /
  node module root per machine (`which`, `npm root -g`) instead of assuming
  Homebrew locations; `secrets/.env` still overrides. `.env.example` paths are
  now commented optional overrides.
- The generated `~/.claude/CLAUDE.md` gets the real repo path injected via an
  `__AGENTIC_ROOT__` placeholder, so the repo can be cloned anywhere. `AGENTS.md`
  no longer hardcodes a path.

### Removed
- Empty `providers/claude/settings.json.template` (superseded by the hooks
  fragment + merge).

## [0.5.0] — 2026-06-24

### Added
- `SETUP.md` — step-by-step onboarding for a new machine (prerequisites, auth,
  clone path, install, update, per-project use, and honest portability caveats).
- `ARCHITECTURE.md` — internal wiring for agents working on the repo: the
  source-of-truth → render → provider model, directory map, merge-mcp invariants,
  conventions, how-to-extend, and gotchas. Linked from the README.

## [0.4.0] — 2026-06-24

### Added
- Full lean-ctx portability: `integrations/lean-ctx/` (MCP server fragment +
  setup README) and `providers/cursor/hooks.json` (the observe/rewrite/redirect
  hooks), installed via `providers/cursor/install.sh`. `secrets/.env.example`
  gained `LEAN_CTX` / `LEAN_CTX_DATA_DIR`, and `doctor.sh --deep` checks for the
  binary.

### Changed
- `merge-mcp.py` now **merges into** the existing `mcp.json` instead of
  overwriting it, so hand-added, work-only servers (e.g. `dora`, `grafana-*`)
  survive a re-install. Repo-managed servers still take precedence.
- Placeholder substitution is now generic over every key in the environment
  (any `__KEY__`), and `~` in `.env` values is expanded.

## [0.3.0] — 2026-06-24

### Added
- `core/rules/lean-ctx.mdc` — pulled the personal lean-ctx rule out of the local
  Cursor config (`~/.cursor/rules/`) into the repo so it is portable across
  machines. `providers/cursor/install.sh` symlinks it back into `~/.cursor/rules`.

### Fixed
- Repaired the `~/.cursor/skills` symlink, which pointed at the stale `agentic`
  path and was dangling; it now resolves to `agentic-cfg/core/skills`.

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

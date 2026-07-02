# Changelog

All notable changes to this config are recorded here. Newest first.

## [0.16.0] — 2026-07-02

### Fixed
- Audit-fixes wave (`plans/audit-fixes-2026-07`): a 31-agent adversarial repository
  audit found 21 independently-verified bug/risk defects, fixed here with a
  regression test per fix.
  - hook: `Classify()` evaluated the ast-grep deny *before* the complex-command
    fail-open, diverging from the design doc and the shell fallback (false-positive
    denials on heredoc/multiline/`cd`-chain/`$()` grep-on-code commands). Restored
    fail-open-first; mirrored the shell fallback's normalization (leading `VAR=`
    assignments + whitespace) and moved its equals-guard ahead of the lean-ctx
    delegate so the Go and shell paths give identical verdicts; `codeExtRe` no
    longer denies suffixed text files (`main.go.orig`); `hook.Main` recovers from
    panics (fail open, not a blocking exit 2).
  - gain/telemetry: first-wins usage dedup undercounted output tokens (Claude Code
    grows `output_tokens` across per-content-block records) — switched to last-wins
    per-field delta reconciliation in `gain.go` and `report.py` in lockstep. The
    deny counter now matches the reason exactly (was ~3x inflated by Read-dumps of
    the guard's own source); the grep adoption tally counts self-wrapped `rtk grep`.
  - install: an unreadable existing config is a hard error (was silently replaced
    with fragment-only content); `inject|eject --home <sandbox>` no longer drives
    the real global `claude` CLI; the atomic writers preserve symlinked configs
    (dotfiles/stow); fresh-machine `sync.py` no longer aborts the install at exit 2;
    a malformed cursor `hooks.json` is a hard error; the Python JSON writers preserve
    non-ASCII; `install.sh` backs up to the `.pre-agentic` name `eject` restores.
  - evals: `cases.validate()` rejects unknown keys (a typo'd `expects` was silently
    ignored); `rejudge()` guards an empty results file.

### Note
- The prior gain-enforcement-fixes wave (PR #13 — shell-guard deny-ordering, the rtk
  `=`-word guard, `agentic gain --adoption`, Claude 5 pricing rows, and the
  office-hours + systematic-debugging skills) shipped without its own CHANGELOG
  entry; this wave audits and hardens it.

## [0.15.1] — 2026-07-02

### Changed
- Distilled the six upstream GitNexus-generated skill files (`impact`,
  `detect_changes`, `rename`, `cypher` guidance) into `gitnexus-navigation`, so
  this repo's skill stays the single source of truth instead of a second copy
  regenerated on every `analyze`.
- Canonical `gitnexus analyze` invocation now carries `--skip-agents-md
  --skip-skills`, suppressing upstream's per-repo `AGENTS.md`/`CLAUDE.md`
  section and generated `.claude/skills/gitnexus/` (~700 tokens/session whose
  MUST-directives conflicted with the tool-precedence gate).

## [0.15.0] — 2026-07-02

### Added
- `agentic update` and `agentic version` subcommands (`internal/selfupdate/`): one-command
  update workflow (fast-forward pull + rebuild + re-apply to all providers) and version
  visibility (git describe + commit date + repo root).
- `bin/install.sh` auto-links `agentic` and `agentic-cfg` into `~/.local/bin` after
  provider dispatch, idempotent and honoring `--dry-run`.
- `bin/doctor.sh` PATH entry-point check: verifies `agentic-cfg` symlink resolves to the
  correct checkout binary.
- `SETUP.md` "Updating" section: documents one-time link setup and ongoing update flow.
- Git versioning via tags starting `v0.15.0` (applied post-merge by orchestrator).

## [0.14.1] — 2026-07-02

### Fixed
- Root-caused the gitnexus MCP outage to two layers: the advisory
  `engines.node >=22` mismatch, and the actual trigger — a corrupt npx cache
  (`~/.npm/_npx/<hash>`) resolving `commander` without its named exports on
  Node 20 *and* Node 26 alike. Resolution: pin to the latest stable
  `gitnexus@1.6.8`, raise the machine's Node baseline to ≥22 via Homebrew
  (`brew install node`, resolving ahead of any older Node on PATH), and clear
  the offending npx cache directory.

### Added
- MCP start/handshake check (`bin/mcp-start-check.py`) wired into
  `doctor.sh --deep`, so a registered-but-dead stdio MCP server fails the
  health check instead of passing a JSON-validity-only grep.
- `doctor.sh --deep` Node floor check: fails if `node` is missing or below
  major version 22, ahead of the gitnexus MCP start check.

## [0.14.0] — 2026-07-02

### Added
- `core/agents/`: four subagent role definitions (`implementer`, `doc-writer`, `verifier`,
  `researcher`), each pinned to a model tier; rendered to `~/.claude/agents/` by the Claude
  installer and covered by `agentic inject`/`eject`/`status`.
- `model-orchestration` skill: "Delegation protocol" section pointing plan-then-delegate
  hand-offs at the shipped agent roles.
- `bin/ci-check.sh`: agents section.
- `plans/orchestration-agents/`: office-hours session #2 design doc (adversarially
  spec-reviewed, two iterations) + the two implementation plans behind this entry.

### Changed
- `docs/research/ai-native-agentic-engineering.md`: July 2026 re-verification and
  extension pass — at least six load-bearing claims re-checked against current vendor
  docs, one moved link fixed, new "What changed since the June snapshot" section
  (Fable 5 / effort `xhigh`, Claude Code Agent Teams, GPT-5.4/5.5 + Codex Remote,
  Gemini CLI → Antigravity CLI cutover, Cursor Composer 2.5).
- `docs/guides/ai-for-software-engineering.md`, `docs/guides/ai-in-daily-life.md`:
  named-practitioner advice woven in with fetched sources (Karpathy, Willison, Mollick,
  Hashimoto, Ronacher, Anthropic/OpenAI/Google guidance) + "What the professionals
  converge on" sections; one stale quote figure corrected against its source.

## [0.13.0] — 2026-07-02

### Added
- Edit-lint hook syntax-checks shell-script edits (#11).
- `agentic` Go CLI with `inject`, `eject`, `status`, `link` subcommands for reversible 
  Claude config management, plus `gain` and `cache` for token-economy metrics.
- CI workflow (`.github/workflows/ci.yml`) running `bin/ci-check.sh` and `golangci-lint` 
  on every push and pull request.
- `bin/prefix-budget.sh` gate enforcing byte budget on always-on prompt prefix.
- `model-orchestration` and `no-mistakes` skills.
- Eval harness hardening: metric track in `--track all`, persistent transcripts under 
  `results/<model>/transcripts/`, `--rejudge` support, fail-closed judge.
- `AGENTIC_TIER=weak` truly removes lean-ctx server and its allow entries.
- Cursor install now merges `hooks.json` (never clobbers) and manages stale entries via 
  `~/.cursor/.agentic-managed.json` sidecar; added `--eject` support.

### Changed
- Hook matchers anchored (`^Bash$`, `^(Read|Grep|Glob)$`, `^(Edit|Write|MultiEdit)$`) so
  substring tool names (`WebSearch`, `preview_click`, `read_clipboard`) no longer match;
  the redirect hook's force-allow is thereby confined to read-only tools.
- Settings merge recognizes managed hook groups by command basename, making merge/eject
  idempotent against path-qualified variants (`/opt/homebrew/bin/lean-ctx hook …`);
  Go/Python parity tests added.
- Edit-lint's Python check uses `ast.parse` (no `__pycache__` litter in user repos).
- Always-on prefix diet: source trimmed 11,232 → 8,754 bytes (~600–800 tokens per
  session, plus retired skill descriptions); terminal-rtk skill folded into AGENTS.md
  Global default 2 (hook-enforced); dead links, phantom `ctx_semantic_search` /
  `ctx_compose` references, and `.mdc` contradictions removed; `no-mistakes` /
  `model-orchestration` trigger descriptions narrowed.
- MCP registration restores the prior server on add failure and continues past
  per-server errors (exit nonzero at the end); merge-mcp stripped of the Cursor
  overlay concept.
- Eval control/OFF arms run under a genuinely bare `CLAUDE_CONFIG_DIR` (no hooks, no
  CLAUDE.md import, no MCP); rows recorded under the old leaky control carry a
  caveat in BENCHMARKS.md.
- Docs: all hardcoded counts replaced with "run the command" phrasing; `~/.claude.json` 
  (user-scope MCP) documented; canonical-path claim removed (path-independent now).
- Non-atomic `agentic-cfg.generated.md` writes now atomic; `doctor` no longer false-OKs.

### Fixed
- Shell-guard fallback corruption on multi-line commands; grep-token regex false-positives.
- `bin/agentic` build gap (Go now available, build happens at install).
- Merge-settings null crash; JSON key order preservation via `internal/jsonorder`.
- CI output discarding; `--track all` now includes metric track.
- `report.py` now refuses to shrink BENCHMARKS.md without `--force`.

### Note
- Review wave (`plans/review-fixes/`): plans 01–08 (shell-guard, evals control-arm,
  hook-matchers, settings-merge, evals-harness, cursor-parity, always-on-diet,
  install-hardening) and 09 (docs sweep) shipped 2026-07-01..02; plan 10
  (machine apply + external-hook cleanup) applied on this machine only.
- Prefix budget now 9054 bytes (source: 8754 bytes currently).

## [0.12.1] — 2026-06-25

### Fixed
- `shell-guard.sh` now fails open on complex commands — multi-line scripts, `cd`
  chains, and command substitution join heredocs in the passthrough list, since
  none can be safely re-quoted inside `lean-ctx -c '…'` or after an `rtk` prefix
  without changing their meaning. Prevents the hook from mangling such commands.

### Changed
- `AGENTS.md` shell rule now forbids stripping the compression hook (no
  `env -u BASH_ENV -u LEAN_CTX_AGENT …` bypass): if a command breaks under the
  hook, report and ask instead of routing around it; put complex logic in a script
  file run with a single `bash script.sh`.

### Note
- The operative breakage was in `~/.bashenv` (the lean-ctx shell hook, installed by
  `lean-ctx onboard` and **not** vendored here), which unconditionally does
  `exec lean-ctx -c "$BASH_EXECUTION_STRING"` with no complex-string guard. That is
  a machine-local / upstream fix, tracked in the repo issue; this changelog covers
  only the repo-owned defense-in-depth.

## [0.12.0] — 2026-06-25

### Added
- **Value-eval track + the loop.** `evals/` is now two tracks: the existing
  conformance/trigger cases (moved to `evals/conformance/cases/`) and a new
  **value** track (`evals/value/cases/`) that measures whether a tool is *worth its
  place* via A/B uplift — the same prompt run with the artifact (treatment) and with
  it ablated (control), scored by a pairwise judge. Position bias is countered with
  order-swap + a flip-rate guard (>10% ⇒ verdict `UNRELIABLE`); efficiency metrics
  (tool-call count, transcript size) are captured for free per arm.
- `evals/PLAYBOOK.md` — the documented loop: definition of done for a new
  skill/rule (ship a conformance case *and* a value case), the decision tree, JSON
  templates, the case-origin rule (cases come from observed weaknesses, à la
  CursorBench), judge-bias handling, and set versioning.
- Per-model results: value runs write `results/<model>/` (gitignored); `report.py`
  rolls them into the committed `evals/BENCHMARKS.md`, linked from `README.md`.
- `evals/lint.py` (schema, unique ids, ablate-target existence, **skill-coverage**)
  and `evals/selftest.py` (pure-logic tests for the pairwise mapping and verdict
  thresholds) — both zero-token, wired into `bin/ci-check.sh` for PR CI.
- Two starter value cases: `ast-grep-structural-precision` (precision) and
  `rtk-economical-shell-output` (economy).

### Changed
- `evals/run.py` is now a single CLI with `--track conformance|value|all`,
  `--filter`, `--n`, `--model`, `--confirm`; shared harness code extracted to
  `evals/lib/` (agent, judge, cases, render_config). The temporary `_run_cache.py`
  driver is removed (use `--filter`).
- `AGENTS.md`, `ARCHITECTURE.md`, and `README.md` point to the eval loop and the
  benchmark results.

### Known limitation
- Clean `config-dir` arm isolation needs env-based auth (`ANTHROPIC_API_KEY`);
  under OAuth/Keychain auth, relocating `CLAUDE_CONFIG_DIR` breaks authentication,
  so value A/B falls back to prompt-level ablation (medium confidence, stamped on
  each result). Verified empirically.

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

# Architecture

Orientation for agents (and humans) working **on** this repo. For installing it
on a machine, see [`SETUP.md`](SETUP.md).

## Mental model

This repo is the **single source of truth** for personal AI-agent configuration.
It is provider-agnostic: one set of skills, instructions, rules, and MCP
integrations is authored here, then **rendered** into provider-specific paths
(`~/.cursor/*`, `~/.claude/*`) by install scripts. Nothing under `$HOME` is
authored by hand — it is all generated or symlinked from here.

```
        author here (git)                 render (bin/install.sh)            consumed by
  ┌──────────────────────────┐       ┌───────────────────────────┐      ┌──────────────┐
  │ core/skills/   (SKILL.md) │       │ providers/cursor/install  │─────▶│ ~/.cursor/*  │
  │ core/rules/    (*.mdc)    │──────▶│ providers/claude/install  │─────▶│ ~/.claude/*  │
  │ core/instructions/AGENTS  │       │ providers/shared/merge-mcp│      └──────────────┘
  │ integrations/* (mcp*.json)│       └───────────────────────────┘
  │ catalog/plugins.yaml      │
  └──────────────────────────┘
```

```mermaid
flowchart LR
  subgraph SOT[Source of truth]
    S[core/skills]
    R[core/rules]
    A[core/instructions/AGENTS.md]
    I[integrations/*/mcp*.json]
  end
  SOT --> INS[bin/install.sh]
  INS --> CUR[providers/cursor/install.sh]
  INS --> CLA[providers/claude/install.sh]
  CUR --> MM[merge-mcp.py]
  CLA --> MM
  CUR --> CURT[(~/.cursor: skills, rules, hooks.json, mcp.json)]
  CLA --> CLAT[(~/.claude: skills, CLAUDE.md, settings.json); ~/.claude.json (MCP)]
  MM --> CURT
  MM --> CLAT
```

## Directory map

| Path | Role |
|------|------|
| `core/skills/<name>/SKILL.md` | Personal skills. Symlinked to `~/.cursor/skills` and `~/.claude/skills`. |
| `core/agents/<name>.md` | Subagent role definitions with pinned model tiers. Symlinked to `~/.claude/agents/` by `providers/claude/install.sh` (Claude-only; Cursor has no subagent equivalent). |
| `core/rules/*.mdc` | Cursor rules (with `description` / `alwaysApply` frontmatter). Symlinked to `~/.cursor/rules`. |
| `core/instructions/AGENTS.md` | Portable agent instructions (the [agents.md](https://agents.md) convention). Inlined into the generated `~/.claude/CLAUDE.md`. |
| `core/principles/*.md` | Always-on behavioral principles. Concatenated into `CLAUDE.md`; rendered to `alwaysApply` Cursor rules. Principle vs skill: see `core/principles/README.md`. |
| `core/instructions/user-rules/*.md` | Detailed rule docs, appended to `CLAUDE.md` and referenced from `AGENTS.md`. |
| `core/workflows/README.md` | Decision guide for when to reach for which skill/plugin. |
| `integrations/<name>/mcp*.json` | MCP server fragments, collected and merged into provider `mcp.json` files. |
| `integrations/<name>/README.md` | Per-integration setup notes (binaries, env). |
| `catalog/plugins.yaml` | Marketplace plugins — **catalogued, never vendored**. |
| `providers/<p>/install.sh` | Renders the source into provider paths. |
| `providers/shared/merge-mcp.py` | Builds provider `mcp.json` from fragments; managed-server sidecar removes stale entries. |
| `providers/shared/merge-settings.py` | Merges Claude hooks + permissions into `~/.claude/settings.json`, preserving machine-local `env`. |
| `providers/claude/CLAUDE.md.stub`, `settings.hooks.json` | Claude scaffolding (`__AGENTIC_ROOT__` injected at install; lean-ctx hooks fragment). |
| `providers/claude/hooks/` | Shell hooks: `shell-guard.sh` (PreToolUse), `edit-lint.sh` (PostToolUse). |
| `cmd/` | Go CLI: `agentic` binary dispatcher (hook, merges, inject/eject/status/link, gain/cache). |
| `internal/` | Go packages: `hook`, `settings`, `mcpmerge`, `claudemd`, `jsonorder`, `installtest`. |
| `telemetry/` | Session token-economy metrics and cache-hit-rate gates. |
| `providers/shared/merge-claude-md.py` | Renders `~/.claude/CLAUDE.md` from stub + imports, managing the agentic-managed block. |
| `bin/prefix-budget.sh` | Enforces byte budget on always-on prefix (stub + AGENTS.md + principles + user-rules). |
| `bin/check-links.py` | Validates relative markdown links across documentation. |
| `bin/bootstrap.sh` | One-command: install deps (Homebrew, git, python3, node, gh, ast-grep, go) then run the installer. |
| `secrets/.env` | Machine-local values (gitignored). Only `.env.example` is tracked. |
| `evals/` | Behavioral eval harness — two tracks (conformance + value A/B), LLM-judge runner, per-model `results/` → `BENCHMARKS.md`. The loop for adding cases is [`evals/PLAYBOOK.md`](evals/PLAYBOOK.md). |
| `bin/install.sh` | Entry point. `--provider cursor\|claude\|all`, `--dry-run`. |
| `bin/doctor.sh` | Health check. `--deep` validates generated JSON + binaries. |
| `bin/ci-check.sh` | Static checks (shell, JSON, YAML, frontmatter, evals). |

## How install works

`bin/install.sh` resolves `AGENTIC_ROOT` dynamically (so it runs from any clone
location), sources `secrets/.env`, and dispatches to provider installers.

- **Cursor** (`providers/cursor/install.sh`): `link_skills` → `install_mcp` →
  `install_rules` → `install_hooks`.
- **Claude** (`providers/claude/install.sh`): `link_skills` → `install_claude_md`
  (stub with `__AGENTIC_ROOT__` injected + `AGENTS.md` + user-rules) →
  `install_mcp` → `install_settings` (merge lean-ctx hooks/permissions).

Both call `merge-mcp.py`; Claude also calls `merge-settings.py`. The **install
scripts** back up each target file with a timestamp suffix before invoking the merge
tools; the merge tools themselves write **atomically** (temp file + rename, via
`internal/jsonorder.WriteFile` / `providers/shared/safe_io.py`) but do not create
their own backups, so an interrupted merge never corrupts the live config (BUG-12).
`DRY_RUN=1` makes every step print-only. `AGENTIC_ROOT` is resolved from the script
location, so the repo can live anywhere — no path is tied to a specific machine.

## merge-mcp behavior (important invariants)

- Collects every `integrations/**/mcp*.json` fragment and merges into provider `mcp.json`.
- **Merges into** the existing target `mcp.json` — repo-managed servers overwrite
  same-named entries, but servers added by hand (e.g. work-only `dora`,
  `grafana-*`) are **preserved**. Never blindly overwrite the target.
- Resolves tool locations **per machine** (`which npx`, `which lean-ctx`,
  `npm root -g`) rather than hardcoding Homebrew paths.
- Substitutes any `__KEY__` placeholder from the resolved environment / `.env`
  (`__NPX__`, `__LEAN_CTX__`, `__LEAN_CTX_DATA_DIR__`, …); `~` in `.env` values
  is expanded. `secrets/.env` overrides any auto-detected value.
- Fails with the offending file path on malformed JSON.

## Conventions / invariants

- **Catalog, don't vendor.** Third-party marketplace plugins go in
  `catalog/plugins.yaml` only — never copy their skill trees in.
- **Skills** are `core/skills/<name>/SKILL.md` with YAML frontmatter that has at
  least `name` and `description` (the description drives trigger matching).
  `bin/ci-check.sh` enforces this.
- **No secrets in the repo.** Real values live in `secrets/.env` (gitignored);
  fragments use `__PLACEHOLDER__` tokens. The repo is private, but still keep
  secrets out of tracked files.
- **The repo can live anywhere** — docs refer to `<your clone>` consistently; no
  path is tied to a specific machine.
- **Tool precedence** (codebase-memory-mcp vs lean-ctx `ctx_*` vs `rtk`) is defined once in
  `AGENTS.md`; don't restate conflicting rules elsewhere.

## How to extend

| Goal | Do this |
|------|---------|
| Bootstrap dependencies | `bin/bootstrap.sh` installs: git, python3, node, gh, ast-grep, go, lean-ctx, rtk. |
| Build the binary | `make build` or `go build -o bin/agentic ./cmd/agentic` compiles the Go CLI. |
| Add a skill | Create `core/skills/<name>/SKILL.md` with frontmatter. It auto-syncs via the symlink — no install code change. |
| Add an always-on principle | Drop `core/principles/<name>.md`; it is concatenated into `CLAUDE.md` and rendered to a Cursor `alwaysApply` rule. Keep it short. |
| Add a Cursor rule | Drop `core/rules/<name>.mdc`; `install_rules` links it. |
| Add an MCP server | Create `integrations/<name>/mcp.stdio.json` (use `__PLACEHOLDER__` for machine-specific values) + a short README. Add defaults to `merge-mcp.load_env` and `secrets/.env.example` if it needs new env. |
| Add an eval | Drop a JSON case in `evals/cases/` (see `evals/README.md`). |
| Change global behavior | Edit `core/instructions/AGENTS.md`; add an eval case that proves the behavior. |

After any change: `bin/ci-check.sh`, then `bin/install.sh --dry-run` to preview.

## Gotchas

- Re-running the full installer regenerates `mcp.json` — safe now (it merges),
  but always check the `--dry-run` if you changed `merge-mcp.py`.
- `rtk` and the `lean-ctx` binary are installed by `bin/bootstrap.sh`, not
  vendored. There is no separate rtk hook — lean-ctx's rewrite hook wraps shell
  commands on machines where it runs.
- Machine-local Claude `env` (e.g. `ANTHROPIC_BASE_URL`) is intentionally not in
  the repo; `merge-settings.py` preserves it.
- `.github/workflows/ci.yml` runs `bin/ci-check.sh` on every push to `master` and on
  pull requests, plus `golangci-lint` for Go static analysis (installs Go from `go.mod`, Python, shellcheck + PyYAML).
- Pushing uses repo-local git identity (`Tsurai7`) and a credential-helper /
  `insteadOf` workaround — see the project memory if `git push` misbehaves.

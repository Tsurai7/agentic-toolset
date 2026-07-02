# agentic

Portable AI agent configuration: skills, instructions, MCP integrations, and sync scripts for **Cursor** and **Claude** Code.

This repo is the **source of truth**. Provider-specific paths are populated by `bin/install.sh`.

- New machine? See [`SETUP.md`](SETUP.md).
- Working on the repo itself? See [`ARCHITECTURE.md`](ARCHITECTURE.md).
- Want the full mental model — layers, components, token economy, daily flows? See
  [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md).

## Quick start

```bash
git clone https://github.com/Tsurai7/agentic-cfg.git && cd agentic-cfg
bin/bootstrap.sh        # installs deps + config + runs doctor (macOS)
```

Already have the deps? Just `bin/install.sh --provider all`. Either way, restart
Cursor / Claude after install. Full walkthrough: [`SETUP.md`](SETUP.md).

### Inject / eject (Claude)

Add or cleanly remove the agentic-cfg footprint in your Claude config with a single,
reversible, test-covered command. `agentic-cfg` ([`bin/agentic-cfg`](bin/agentic-cfg), also
available as `agentic`) preserves your own `CLAUDE.md` text, `settings.json` `env`/hooks, and
any real `~/.claude/skills` you already have:

```bash
agentic-cfg inject          # add: skills symlink, CLAUDE.md @import, hooks + permissions, MCP
agentic-cfg eject           # remove exactly that, leaving your content untouched
agentic-cfg inject --dry-run   # preview; --skip-mcp to leave MCP servers alone; --home DIR to target
agentic-cfg status             # report whether it's injected (exit 0 if yes, 1 if not); --json for scripts
```

To run these from anywhere, put them on your PATH once:

```bash
agentic link        # symlinks agentic + agentic-cfg into ~/.local/bin (--dir to change)
```

Fully covered by tests: `internal/lifecycle/` (round-trip preserves user content, idempotency,
real-skills-dir backup/restore, dry-run), the reversal primitives
(`internal/claudemd/strip_test.go`, `internal/settings/unmerge_test.go`), and the CLI dispatch
+ PATH linking (`cmd/agentic/main_test.go`).

Design rationale: [`archive/inject-eject-office-hours.md`](archive/inject-eject-office-hours.md).

## Layout

| Path | Purpose |
|------|---------|
| `core/skills/` | Personal `SKILL.md` files (symlinked to `~/.cursor/skills` and `~/.claude/skills`) |
| `core/agents/` | Subagent role definitions with pinned model tiers (rendered to `~/.claude/agents/`, Claude-only) |
| `core/instructions/` | `AGENTS.md` + exported user rules |
| `core/principles/` | Always-on behavioral principles (concatenated into `CLAUDE.md`; rendered to Cursor `alwaysApply` rules) |
| `core/rules/` | Cursor `.mdc` rules (symlinked to `~/.cursor/rules`) |
| `integrations/` | Custom MCP server definitions (merged into provider configs) |
| `catalog/plugins.yaml` | Marketplace plugins to enable manually (not vendored) |
| `docs/` | Long-form docs (not rendered): the [office-hours design session](archive/model-orchestration-office-hours.md), the [AI-native research review](docs/research/ai-native-agentic-engineering.md), and practitioner [guides](docs/README.md) |
| `providers/` | Per-provider install scripts and templates |
| `evals/` | Behavioral evals — conformance (does it fire) + value A/B (is it worth it). Loop: [`evals/PLAYBOOK.md`](evals/PLAYBOOK.md); results: [`evals/BENCHMARKS.md`](evals/BENCHMARKS.md) |
| `bin/` | `bootstrap.sh` (one-command setup), `install.sh`, `doctor.sh`, `ci-check.sh` |

## Providers (Phase 1)

| Provider | Skills | Memory | MCP |
|----------|--------|--------|-----|
| Cursor | `~/.cursor/skills` → `core/skills` | User rules UI + optional `core/rules/` | `~/.cursor/mcp.json` |
| Claude Code / Desktop | `~/.claude/skills` → `core/skills` | `~/.claude/CLAUDE.md` | `~/.claude.json` |

## Marketplace plugins

Third-party plugins (MongoDB, Atlassian, Superpowers, etc.) are **catalogued only** in [`catalog/plugins.yaml`](catalog/plugins.yaml). Install them from each provider's marketplace; do not copy their skill trees into this repo.

## Environment

Copy [`secrets/.env.example`](secrets/.env.example) to `secrets/.env` (gitignored). `NPX` is auto-detected; override in `secrets/.env` only if needed.

## Checks

```bash
bin/doctor.sh            # verify symlinks, MCP, memory, binaries
bin/doctor.sh --deep     # also validate generated MCP JSON + GitNexus pin
bin/ci-check.sh          # static checks (links, hooks self-tests, merge helpers, swe-bench selftest, memory seeds, prefix budget, Go fmt/vet/test/build)
python3 evals/run.py --track all   # behavioral evals (dry by default; see evals/README.md)
```

Measured value-A/B results per model: [`evals/BENCHMARKS.md`](evals/BENCHMARKS.md).
How to add and maintain cases: [`evals/PLAYBOOK.md`](evals/PLAYBOOK.md).

## Metrics

See what the config is buying you — token volume, prompt-cache hit rate, and the
input cost avoided by caching — straight from your own session transcripts:

```bash
agentic gain                 # last 20 sessions (read-only; built into the binary)
agentic gain --json          # machine-readable
agentic cache                # cache-focused view: hit rate + token split + cost saved
agentic cache --by-model     # cache hit rate per model tier
```

`agentic cache` (alias for `agentic gain --cache`) leads with the prompt-cache hit
rate — the headline token-economy number — and the input bill caching avoided.
Richer per-session/cost/tool breakdown: [`telemetry/`](telemetry/README.md).

## Phase 2 (not automated yet)

- **OpenAI Codex:** `~/.codex/config.toml` — add `integrations/*/mcp.codex.toml.fragment` later
- **Gemini:** `GEMINI.md` per integration (see MongoDB plugin pattern)

## Project adoption

For a team repo, submodule this repo or copy `core/instructions/AGENTS.md` into the project root. Keep project-specific skills in `.cursor/skills/` or `.claude/skills/` inside the project; personal skills stay in home via symlink.

## Cursor user rules

Cloud user rules are not synced automatically. After install, add a short rule in **Cursor → Settings → Rules** pointing agents to this repo and `core/instructions/AGENTS.md`.

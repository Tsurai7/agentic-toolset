# agentic

Portable AI agent configuration: skills, instructions, MCP integrations, and sync scripts for **Cursor** and **Claude** (Desktop + Code).

This repo is the **source of truth**. Provider-specific paths are populated by `bin/install.sh`.

- New machine? See [`SETUP.md`](SETUP.md).
- Working on the repo itself? See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Quick start

```bash
git clone https://github.com/Tsurai7/agentic-cfg.git && cd agentic-cfg
bin/bootstrap.sh        # installs deps + config + runs doctor (macOS)
```

Already have the deps? Just `bin/install.sh --provider all`. Either way, restart
Cursor / Claude after install. Full walkthrough: [`SETUP.md`](SETUP.md).

## Layout

| Path | Purpose |
|------|---------|
| `core/skills/` | Personal `SKILL.md` files (symlinked to `~/.cursor/skills` and `~/.claude/skills`) |
| `core/instructions/` | `AGENTS.md` + exported user rules |
| `core/principles/` | Always-on behavioral principles (concatenated into `CLAUDE.md`; rendered to Cursor `alwaysApply` rules) |
| `core/rules/` | Cursor `.mdc` rules (symlinked to `~/.cursor/rules`) |
| `integrations/` | Custom MCP server definitions (merged into provider configs) |
| `catalog/plugins.yaml` | Marketplace plugins to enable manually (not vendored) |
| `providers/` | Per-provider install scripts and templates |
| `evals/` | Behavioral evals — conformance (does it fire) + value A/B (is it worth it). Loop: [`evals/PLAYBOOK.md`](evals/PLAYBOOK.md); results: [`evals/BENCHMARKS.md`](evals/BENCHMARKS.md) |
| `bin/` | `bootstrap.sh` (one-command setup), `install.sh`, `doctor.sh`, `ci-check.sh` |

## Providers (Phase 1)

| Provider | Skills | Memory | MCP |
|----------|--------|--------|-----|
| Cursor | `~/.cursor/skills` → `core/skills` | User rules UI + optional `core/rules/` | `~/.cursor/mcp.json` |
| Claude Code / Desktop | `~/.claude/skills` → `core/skills` | `~/.claude/CLAUDE.md` | `~/.claude/.mcp.json` |

## Marketplace plugins

Third-party plugins (MongoDB, Atlassian, Superpowers, etc.) are **catalogued only** in [`catalog/plugins.yaml`](catalog/plugins.yaml). Install them from each provider's marketplace; do not copy their skill trees into this repo.

## Environment

Copy [`secrets/.env.example`](secrets/.env.example) to `secrets/.env` (gitignored). Set `NPX` for your machine (Homebrew default on macOS: `/opt/homebrew/bin/npx`).

## Checks

```bash
bin/doctor.sh            # verify symlinks, MCP, memory, binaries
bin/doctor.sh --deep     # also validate generated MCP JSON + GitNexus pin
bin/ci-check.sh          # static checks (shell, JSON, YAML, frontmatter, eval lint + self-test)
python3 evals/run.py --track all   # behavioral evals (dry by default; see evals/README.md)
```

Measured value-A/B results per model: [`evals/BENCHMARKS.md`](evals/BENCHMARKS.md).
How to add and maintain cases: [`evals/PLAYBOOK.md`](evals/PLAYBOOK.md).

## Phase 2 (not automated yet)

- **OpenAI Codex:** `~/.codex/config.toml` — add `integrations/*/mcp.codex.toml.fragment` later
- **Gemini:** `GEMINI.md` per integration (see MongoDB plugin pattern)

## Project adoption

For a team repo, submodule this repo or copy `core/instructions/AGENTS.md` into the project root. Keep project-specific skills in `.cursor/skills/` or `.claude/skills/` inside the project; personal skills stay in home via symlink.

## Cursor user rules

Cloud user rules are not synced automatically. After install, add a short rule in **Cursor → Settings → Rules** pointing agents to this repo and `core/instructions/AGENTS.md`.

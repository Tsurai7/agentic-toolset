# Agent instructions (portable)

Synced to Claude via `~/.claude/CLAUDE.md`. Use as project `AGENTS.md` when adopting this repo in a codebase.

## Source of truth

Personal agent config lives in **`~/Documents/GitHub/personal/agentic`**. Run `bin/install.sh --provider all` after pulling changes.

## Global defaults

1. **Structural code work** — Prefer GitNexus graph tools over raw grep/file reads when changing interfaces or tracing impact. See skill `gitnexus-navigation`.
2. **Shell on macOS** — Prefix terminal commands with `rtk` (e.g. `rtk npm test`). See skill `terminal-rtk`.
3. **Git commits** — Only when the user explicitly asks; follow skill `git-safety`.
4. **Pull requests** — Use `gh` per skill `create-pr`.
5. **Done means verified** — Before claiming success, run checks per skill `verification-before-completion`.

## Detailed rules

| Topic | File |
|-------|------|
| Communication & citations | [user-rules/communication.md](user-rules/communication.md) |
| Code change principles | [user-rules/coding-principles.md](user-rules/coding-principles.md) |
| Cursor rules pointer | [user-rules/cursor-rules-pointer.md](user-rules/cursor-rules-pointer.md) |

## Skills (invoke or auto-discover)

| Skill | Purpose |
|-------|---------|
| `git-safety` | Safe git commit workflow |
| `create-pr` | GitHub PR creation with `gh` |
| `verification-before-completion` | Evidence before completion claims |
| `gitnexus-navigation` | When to use GitNexus vs search |
| `terminal-rtk` | `rtk` command prefix on macOS |

## Marketplace plugins

Enable per [`catalog/plugins.yaml`](../../catalog/plugins.yaml). Do not duplicate their skill content here.

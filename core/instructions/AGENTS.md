# Agent instructions (portable)

Synced to Claude via `~/.claude/CLAUDE.md`. Use as project `AGENTS.md` when adopting this repo in a codebase.

## Source of truth

This repo is the source of truth for personal agent config. Run `bin/install.sh --provider all` from the repo root after pulling changes; the install path is detected automatically and is not tied to any one machine.

## Global defaults

1. **Structural code work** — Prefer GitNexus graph tools over raw grep/file reads when changing interfaces or tracing impact. See skill `gitnexus-navigation`.
2. **Shell on macOS** — Prefix terminal commands with `rtk` (e.g. `rtk npm test`). See skill `terminal-rtk`.
3. **Git commits** — Only when the user explicitly asks; follow skill `git-safety`.
4. **Pull requests** — Use `gh` per skill `create-pr`.
5. **Done means verified** — Before claiming success, run checks per skill `verification-before-completion`.

## Tool precedence (resolve overlaps)

Three layers can address the same action (shell, search, file reads). When more than
one is available, follow this order. Each layer is optional — degrade to the next when
the tool is absent (e.g. Cursor or a team repo without lean-ctx).

| Action | 1st choice | 2nd choice | Last resort |
|--------|-----------|------------|-------------|
| Structural code nav (who calls / implements, impact) | GitNexus (`gitnexus-navigation`) | `ctx_semantic_search` | — |
| Text / concept search | lean-ctx `ctx_search` | GitNexus needle query | `grep` (literals only) |
| Run a shell command | lean-ctx `ctx_shell` | native terminal **prefixed with `rtk`** | — |
| Read a file | lean-ctx `ctx_read` | native read | — |

Rules:

- **Do not double-wrap.** `rtk` is a native-terminal prefix; `ctx_shell` already compresses
  output, so never nest `rtk` inside `ctx_shell` or vice versa.
- When lean-ctx is connected, its `ctx_*` tools win for shell / search / read (see the user's
  global lean-ctx rules). `rtk` applies only on the native terminal path, where its hook fires.
- GitNexus is for the **graph** question (structure, polymorphism, blast radius); `ctx_search`
  and `grep` are for **text**. Pick by question type, not habit.

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

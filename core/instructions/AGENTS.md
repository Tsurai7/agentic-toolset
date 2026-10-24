# Agent instructions (portable)

Synced to Claude via `~/.claude/CLAUDE.md`. Use as project `AGENTS.md` when adopting this repo in a codebase.

## Source of truth

This repo is the source of truth for personal agent config. Run `bin/install.sh --provider all` from the repo root after pulling changes; the install path is detected automatically and is not tied to any one machine.

## Global defaults

1. **Structural code work** — Prefer codebase-memory-mcp graph tools over raw grep/file reads when changing interfaces or tracing impact. See skill `codebase-memory`.
2. **Code search** — Search source code with `ast-grep` (AST patterns), never regex grep. Use grep only for non-code text. See skill `ast-grep`.
3. **Shell on macOS** — Prefix terminal commands with `rtk` (e.g. `rtk npm test`). See skill `terminal-rtk`. **Never strip the compression hook** — do not run commands via `env -u BASH_ENV -u LEAN_CTX_AGENT …` or otherwise disable lean-ctx/rtk to dodge it. If a command breaks under the hook, report the failure and ask, don't bypass; for complex commands, put the logic in a script file and run it with a single `bash script.sh` (which the hook passes through unmangled).
4. **Git commits** — Only when the user explicitly asks; follow skill `git-safety`.
5. **Pull requests** — Use `gh` per skill `create-pr`.
6. **Done means verified** — Before claiming success, run checks per skill `verification-before-completion`.

## Tool precedence (resolve overlaps)

Three layers can address the same action (shell, search, file reads). When more than
one is available, follow this order. Each layer is optional — degrade to the next when
the tool is absent (e.g. Cursor or a team repo without lean-ctx).

| Action | 1st choice | 2nd choice | Last resort |
|--------|-----------|------------|-------------|
| Structural code nav (who calls / implements, impact) | codebase-memory-mcp (`codebase-memory`) | `ctx_semantic_search` | — |
| Syntactic code search (code matching a pattern) | `ast-grep` (`ast-grep`) | — | `grep` if no parser |
| Text / concept search (non-code) | lean-ctx `ctx_search` | codebase-memory-mcp `search_code` | `grep` (literals only) |
| Run a shell command | lean-ctx `ctx_shell` | native terminal **prefixed with `rtk`** | — |
| Read a file | lean-ctx `ctx_read` | native read | — |

Rules:

- **Do not double-wrap.** `rtk` is a native-terminal prefix; `ctx_shell` already compresses
  output, so never nest `rtk` inside `ctx_shell` or vice versa.
- When lean-ctx is connected, its `ctx_*` tools win for shell / search / read (see the user's
  global lean-ctx rules). `rtk` applies only on the native terminal path, where its hook fires.
- codebase-memory-mcp is for the **graph** question (structure, polymorphism, blast radius); `ast-grep`
  is for **code shaped like a pattern**; `ctx_search` / `grep` are for **plain text**. Pick by
  question type, not habit.
- Never regex-grep source code when `ast-grep` can parse the language — grep is the fallback
  only for unsupported languages or non-code text (logs, config, prose).

## Detailed rules

| Topic | File |
|-------|------|
| Always-on principles (think/simplify/surgical/verify) | [`core/principles/`](../../core/principles/) |
| Communication & citations | [user-rules/communication.md](user-rules/communication.md) |
| Code change principles | [user-rules/coding-principles.md](user-rules/coding-principles.md) |
| Cursor rules pointer | [user-rules/cursor-rules-pointer.md](user-rules/cursor-rules-pointer.md) |
| Proving a new skill/rule is worth it (eval loop) | [`evals/PLAYBOOK.md`](../../evals/PLAYBOOK.md) |

When you add or change a skill/rule under `core/`, follow the eval loop: ship a
conformance case (it fires) and a value case (firing helps). `evals/lint.py` fails
CI if a skill has no eval.

## Skills (invoke or auto-discover)

| Skill | Purpose |
|-------|---------|
| `git-safety` | Safe git commit workflow |
| `create-pr` | GitHub PR creation with `gh` |
| `verification-before-completion` | Evidence before completion claims |
| `codebase-memory` | Graph queries: callers, call chains, impact, dead code |
| `ast-grep` | Structural code search/rewrite instead of regex grep |
| `terminal-rtk` | `rtk` command prefix on macOS |
| `prompt-caching-playbook` | Maximize LLM prompt-cache hit rate / cut token cost |

## Marketplace plugins

Enable per [`catalog/plugins.yaml`](../../catalog/plugins.yaml). Do not duplicate their skill content here.

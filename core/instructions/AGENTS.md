# Agent instructions (portable)

Synced to Claude via `~/.claude/CLAUDE.md`. Use as project `AGENTS.md` when adopting this repo in a codebase.

## Source of truth

This repo is the source of truth for personal agent config. Run `bin/install.sh --provider all` from the repo root after pulling changes; the install path is detected automatically and is not tied to any one machine.

## Global defaults

1. **Tool choice** — Right-size tooling to the task, then follow the precedence table below. See skills `gitnexus-navigation`, `ast-grep`.
2. **Shell on macOS** — Terminal commands run through the lean-ctx/rtk compression hook. Never strip or bypass it; if a command breaks under it, report and ask. Put complex logic in a script file and run `bash script.sh`. Prefix `rtk` yourself in copy-paste commands you show the user; omit `rtk` off macOS.
3. **Git commits** — Only when the user explicitly asks; follow skill `git-safety`.
4. **Pull requests** — Use `gh` per skill `create-pr`.
5. **Done means verified** — Before claiming success, run checks per skill `verification-before-completion`.

## Tool precedence (resolve overlaps)

**Right-size the tooling to the task — this gates everything below.** For a
trivial single-fact lookup (one symbol, one file, a literal string), use the
single lightest tool that answers it and stop — no orienting, no graph-building.
Treat multi-step, structural, or high-blast-radius work (3+ coupled files,
"who calls / what breaks" questions, ambiguous scope) as heavy; when in doubt,
escalate — the toolset earns its cost on hard tasks. Once a read-only lookup is
answered, stop; "Done means verified" still applies to changes you make.

When you do need a class of action, three layers can address it (shell, search, file
reads); prefer them in this order. Each layer is optional — degrade to the next when the
tool is absent (e.g. Cursor or a team repo without lean-ctx).

| Action | 1st choice | 2nd choice | Last resort |
|--------|-----------|------------|-------------|
| Structural code nav (who calls / implements, impact) | GitNexus (`gitnexus-navigation`; strongest on Go/.NET) | lean-ctx `ctx_graph` | `ast-grep` pattern scan |
| Syntactic code search (code matching a pattern) | `ast-grep` (`ast-grep`) | — | `grep` if no parser |
| Text / concept search (non-code) | lean-ctx `ctx_search` | GitNexus needle query | `grep` (literals only) |
| Run a shell command | lean-ctx `ctx_shell` | native terminal **prefixed with `rtk`** | — |
| Read a file | lean-ctx `ctx_read` | native read | — |

Rules:

- **Do not double-wrap.** `rtk` is a native-terminal prefix; `ctx_shell` already
  compresses output — never nest one inside the other. When lean-ctx is
  connected, its `ctx_*` tools win; `rtk` applies only on the native terminal path.
- GitNexus answers the **graph** question (structure, polymorphism, blast
  radius); `ast-grep` finds **code shaped like a pattern**; `ctx_search`/`grep`
  are for **plain text** (logs, config, prose). Never regex-grep source code
  when `ast-grep` can parse the language.

## Detailed rules

Detailed rule docs live in core/principles/ and core/instructions/user-rules/
(inlined into the generated Claude prefix); the loop for proving a new rule
earns its keep is evals/PLAYBOOK.md.

When you add or change a skill/rule under `core/`, follow the eval loop: ship a
conformance case (it fires) and a value case (firing helps). `evals/lint.py` fails
CI if a skill has no eval.

## Skills (invoke or auto-discover)

Skills live in core/skills/<name>/SKILL.md; each description is its trigger and
is injected by the provider — do not restate them here.

## Marketplace plugins

Enable per [`catalog/plugins.yaml`](../../catalog/plugins.yaml). Do not duplicate their skill content here.

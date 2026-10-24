# Agent instructions (portable)

Synced to Claude via `~/.claude/CLAUDE.md`. Use as project `AGENTS.md` when adopting this repo in a codebase.

## Source of truth

This repo is the source of truth for personal agent config. Run `bin/install.sh --provider all` from the repo root after pulling changes; the install path is detected automatically and is not tied to any one machine.

## Global defaults

1. **Tool choice** — Right-size tooling to the task, then follow the precedence table below. See skills `codebase-memory`, `ast-grep`.
2. **Shell** — Put complex logic in a script file and run `bash script.sh`.
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

When you do need a class of action, prefer tools in this order. Each tool is
optional — degrade to the next when it is absent.

| Action | 1st choice | 2nd choice |
|--------|-----------|------------|
| Structural code nav (who calls / implements, impact) | codebase-memory-mcp (`codebase-memory`) | `ast-grep` pattern scan |
| Structural code search (calls, signatures, code shapes) | `ast-grep` (`ast-grep`) | `grep` if no parser |
| Text search (literal strings, identifiers, logs, config, prose) | native Grep tool | codebase-memory-mcp `search_code` |
| Read a file | native Read | — |

Pick by question type, not habit: codebase-memory-mcp answers the **graph**
question (structure, blast radius); `ast-grep` answers "where is **code shaped
like** X"; Grep answers "where does this **text** appear" — including a literal
string inside source files.

## Detailed rules

Detailed rule docs live in core/principles/ and core/instructions/user-rules/
(inlined into the generated Claude prefix); the loop for proving a new rule
earns its keep is evals/PLAYBOOK.md.

When you add or change a skill/rule under `core/`, follow the eval loop: ship a
conformance case (it fires). Add a value case too where the benefit is
measurable (an ablation shows firing helps) — skip it for low-signal skills
where a pairwise comparison wouldn't discriminate (e.g. `git-safety`,
`create-pr`). `evals/lint.py` fails CI if a skill has no eval case at all.

## Skills (invoke or auto-discover)

Skills live in core/skills/<name>/SKILL.md; each description is its trigger and
is injected by the provider — do not restate them here.

## Marketplace plugins

Enable per [`catalog/plugins.yaml`](../../catalog/plugins.yaml). Do not duplicate their skill content here.

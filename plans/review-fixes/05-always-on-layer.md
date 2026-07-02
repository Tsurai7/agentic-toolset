# Plan 05 — always-on layer: correctness fixes + token diet (−35%)

[Index](00-INDEX.md) · Wave C · Files: `core/instructions/AGENTS.md`,
`core/rules/lean-ctx.mdc`, `core/principles/honesty.md`,
`core/principles/karpathy-guidelines.md`,
`core/instructions/user-rules/cursor-rules-pointer.md`,
`core/skills/no-mistakes/SKILL.md`, `core/skills/model-orchestration/SKILL.md`,
`core/skills/terminal-rtk/` (deleted), `core/skills/ast-grep/SKILL.md`,
`core/workflows/README.md`, `bin/prefix-budget.sh`, eval case files for
terminal-rtk (removed), `evals/BENCHMARKS.md` (one note).

Measured baseline: the generated always-on prefix is 11,232 bytes ≈ 1,668 words
≈ 2.2–2.8k tokens, plus ~600 tokens of skill descriptions per session. Targets:
**generated prefix source ≤ 9,000 bytes** and no behavior lost.

## A. Correctness fixes (do these first)

### A1. Phantom tools

`AGENTS.md` precedence table row "Structural code nav" lists
`ctx_semantic_search` as 2nd choice — the live lean-ctx server has NO such tool
(nor `ctx_compose`). Replace the row with:

```
| Structural code nav (who calls / implements, impact) | GitNexus (`gitnexus-navigation`; strongest on Go/.NET) | lean-ctx `ctx_graph` | `ast-grep` pattern scan |
```

### A2. Rewrite `core/rules/lean-ctx.mdc` (Cursor-only, alwaysApply)

Current file contradicts AGENTS.md ("NEVER use native Read/Grep/Shell" vs
"degrade to the next layer"), prescribes three different shell mechanisms, and
references the phantom `ctx_compose`/`ctx_semantic_search`. Replace the ENTIRE
file body with exactly:

```markdown
---
description: "lean-ctx tool mapping — prefer ctx_* tools for shell/search/read; degrade to native when a tool is absent."
alwaysApply: true
---

# lean-ctx
<!-- lean-ctx-rules-v12 -->

Prefer lean-ctx over native equivalents; when a `ctx_*` tool is unavailable,
degrade per the AGENTS.md precedence table (it is canonical).

| Task | Prefer | Fallback |
|------|--------|----------|
| Read a file | `ctx_read(path, mode)` — modes: full / map / signatures / diff / lines:N-M | native read |
| Search text | `ctx_search(pattern, path)` | grep (non-code text only) |
| Run shell | `ctx_shell(command)` | native terminal, `rtk` prefix |
| List files | `ctx_tree(path, depth)` | ls |
| Edit | native Edit; `ctx_edit` only when Edit is unavailable | — |

Never nest `rtk` inside `ctx_shell` or vice versa (one wrapper per command).
<!-- /lean-ctx -->
```

### A3. Canonical path in `cursor-rules-pointer.md`

Replace the literal `~/Documents/GitHub/personal/agentic-cfg` in the quoted
User Rule with: `your agentic-cfg clone root (e.g. ~/Documents/GitHub/agentic-cfg)`.

## B. Token diet in `AGENTS.md`

### B1. Global defaults — replace items 1 and 2 with:

```markdown
1. **Tool choice** — Right-size tooling to the task, then follow the precedence table below. See skills `gitnexus-navigation`, `ast-grep`.
2. **Shell on macOS** — Terminal commands run through the lean-ctx/rtk compression hook. Never strip or bypass it; if a command breaks under it, report and ask. Put complex logic in a script file and run `bash script.sh`. Prefix `rtk` yourself in copy-paste commands you show the user; omit `rtk` off macOS.
```

(Items 3–5 unchanged. Note item 2 now absorbs the two rules that justified the
`terminal-rtk` skill — see B5.)

### B2. Right-size gate paragraph — replace the 167-word paragraph (lines ~19–29) with:

```markdown
**Right-size the tooling to the task — this gates everything below.** For a
trivial single-fact lookup (one symbol, one file, a literal string), use the
single lightest tool that answers it and stop — no orienting, no graph-building.
Treat multi-step, structural, or high-blast-radius work (3+ coupled files,
"who calls / what breaks" questions, ambiguous scope) as heavy; when in doubt,
escalate — the toolset earns its cost on hard tasks. Once a read-only lookup is
answered, stop; "Done means verified" still applies to changes you make.
```

Keep the following "three layers … degrade to the next when the tool is absent"
paragraph as-is.

### B3. Rules bullets under the table — replace all three bullets with two:

```markdown
- **Do not double-wrap.** `rtk` is a native-terminal prefix; `ctx_shell` already
  compresses output — never nest one inside the other. When lean-ctx is
  connected, its `ctx_*` tools win; `rtk` applies only on the native terminal path.
- GitNexus answers the **graph** question (structure, polymorphism, blast
  radius); `ast-grep` finds **code shaped like a pattern**; `ctx_search`/`grep`
  are for **plain text** (logs, config, prose). Never regex-grep source code
  when `ast-grep` can parse the language.
```

Also in Global default 1 (already rewritten in B1) the "(never regex-grep
source)" clause is gone — it now lives only here and in the table.

### B4. Kill the two double-pay tables

- "Detailed rules" section: delete the table (its links are dead inside the
  generated `~/.claude` artifact and the content is inlined below it anyway).
  Replace with one sentence: `Detailed rule docs live in core/principles/ and
  core/instructions/user-rules/ (inlined into the generated Claude prefix);
  the loop for proving a new rule earns its keep is evals/PLAYBOOK.md.`
  Keep the existing "When you add or change a skill/rule…" paragraph.
- "Skills" section: delete the 9-row table (Claude injects every SKILL.md
  description natively — the table is paid twice and is already stale: it
  omits `no-mistakes`). Replace with one sentence: `Skills live in
  core/skills/<name>/SKILL.md; each description is its trigger and is injected
  by the provider — do not restate them here.` Keep the "Marketplace plugins" section.

## C. Cross-file dedup

- `core/principles/honesty.md`: in "Back claims with evidence", collapse the
  second bullet to one line: `- "Tests pass" / "it's fixed" require fresh,
  observed output — see skill \`verification-before-completion\`.`
- `core/principles/karpathy-guidelines.md`:
  - Section 2 body → keep the heading + `Minimum code that solves the problem —
    scope and over-engineering rules live in coding-principles. Test: "Would a
    senior engineer call this overcomplicated?" If yes, simplify.`
  - Section 3 body → keep the heading + `Touch only what you must; clean up only
    your own mess — see coding-principles. Match existing style. Remove only
    what YOUR change orphaned. Test: every changed line traces to the request.`
  - Section 4: delete the final sentence ("Complements the
    `verification-before-completion` skill.").
- `core/skills/ast-grep/SKILL.md`: delete the "Precedence" section (it
  paraphrases the AGENTS.md table); keep the "Default" section.
- `core/workflows/README.md`: replace its skill list with a pointer to
  `core/skills/` (same rationale as B4; it is repo-doc only, not injected —
  keep the decision-guide prose, drop only the duplicated list).

## D. Skill trigger hygiene

### D1. `no-mistakes` — replace the frontmatter `description` with:

```
Validate your code changes through the no-mistakes pipeline - automated code review, tests, lint, docs, push, PR, and CI - before they reach the configured push target. Use only when the user explicitly invokes /no-mistakes, names no-mistakes, or asks to run the gate/pipeline. A generic "do X and verify it" is NOT this skill - that is verification-before-completion.
```

### D2. `model-orchestration` — replace the frontmatter `description` with:

```
Route each sub-task to the cheapest model tier that can do it well, and delegate execution to subagents. Apply when planning a multi-step or token-expensive task, choosing between strong/mid/cheap models (Opus/Sonnet/Haiku), or deciding whether to spawn subagents. Plan and decide with a strong model; execute well-specified sub-tasks with a cheap one; escalate on failure. Skip for a single trivial step - orchestration has overhead. Prompt/cache token costs of an LLM system belong to prompt-caching-playbook.
```

### D3. Delete the `terminal-rtk` skill

The `shell-guard.sh` hook enforces the behavior mechanically; the two rules a
hook cannot enforce moved into Global default 2 (B1). Steps:

- `git rm -r core/skills/terminal-rtk` (working tree rm is fine — no commit).
- Remove its eval cases: find them via
  `grep -rl "terminal-rtk\|rtk-" evals/ --include=*.json` — expect a
  conformance case (skill-trigger) and `evals/value/cases/rtk-economical-shell-output.json`.
  Delete the ones whose subject is the terminal-rtk skill (do NOT delete
  ast-grep or other cases that merely mention rtk).
- `evals/BENCHMARKS.md`: add a one-line note that `terminal-rtk` was folded
  into AGENTS.md Global default 2 on 2026-07-01 (hook-enforced; skill retired),
  so its historical row is no longer a live skill.
- Check `evals/lint.py` exemption lists mention terminal-rtk? If lint hardcodes
  skill names anywhere, update.

## E. Budget ratchet

`bin/prefix-budget.sh`: after A–C land, measure the new total (the script
prints it), then set the committed default `PREFIX_BUDGET_BYTES` to
`<new total> + 300` (headroom for small edits), replacing 11300. The new
default MUST be ≤ 9300.

## Acceptance criteria

1. `grep -rn "ctx_semantic_search\|ctx_compose" core/ providers/ --include='*.md' --include='*.mdc'` → no matches.
2. `grep -rn "personal/agentic-cfg" core/` → no matches.
3. `bash bin/prefix-budget.sh` prints a total ≤ 9000 and passes with the new committed budget (≤ 9300).
4. `python3 evals/lint.py` → `lint OK` (coverage green with terminal-rtk gone).
5. `bash bin/ci-check.sh` exits 0 (frontmatter checks pass on the two edited descriptions).
6. Behavior preservation spot-check — all of these facts must still be stated
   exactly once in the generated payload sources (grep each, expect exactly 1
   hit across `core/instructions/AGENTS.md` + `core/principles/*.md` +
   `core/instructions/user-rules/*.md`):
   a) never strip/bypass the compression hook; b) never nest rtk in ctx_shell;
   c) never regex-grep parseable source (allowed: 2 hits — table row + rules bullet);
   d) commits only when the user asks; e) fresh observed output before claiming done.
7. `ls core/skills/` does not contain `terminal-rtk`; `grep -rn "terminal-rtk" core/instructions/ core/workflows/` → no matches (README/docs cleanup is plan 09's job for files outside core/).
8. Report the before/after byte count of the concatenated prefix sources
   (prefix-budget.sh prints it) — expect ≥ 2,200 bytes saved.
9. `git status` touches only files listed in the header.

## Out of scope

Regenerating `~/.claude/agentic-cfg.generated.md` (plan 10 runs the installer).
`communication.md` provider split — deferred (see index). Docs outside `core/`
that mention terminal-rtk (plan 09).

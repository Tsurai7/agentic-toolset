# Plan 02 — Delegation protocol in the skill + eval + docs

Part of [`00-INDEX.md`](00-INDEX.md); design: [`DESIGN.md`](DESIGN.md) (Approach B).

**File scope (touch nothing else):**
- `core/skills/model-orchestration/SKILL.md`
- `evals/conformance/cases/model-orchestration-shipped-roles.json` (new)
- `CHANGELOG.md`, `README.md`, `ARCHITECTURE.md`, `docs/README.md`

Do NOT commit. Do not edit `core/agents/*` or `providers/*` (plan 01's scope).

## Change 1 — `model-orchestration` skill: Delegation protocol section

Insert a new `## Delegation protocol (when the roles are installed)` section into
`core/skills/model-orchestration/SKILL.md`, between "The default pattern" and "When NOT
to orchestrate". Constraints: ≤ 45 lines net file growth — an editorial lean-body cap
(skills load pay-per-fire, so this is about keeping the skill readable, NOT the
always-on prefix budget, which skill bodies don't count against); do NOT restate the
role bodies (they are the artifacts); pointer style. Content to convey (wording may be
tightened, meaning may not drift):

```markdown
## Delegation protocol (when the roles are installed)

This repo ships four subagent roles (`core/agents/`, rendered to `~/.claude/agents/`),
each with a pinned tier and a body that already carries the scope guard, AC discipline,
status protocol, and environment notes — so a delegation prompt only needs the task:

| Role | Tier | Hand it |
|------|------|---------|
| `implementer` | mid | a plan file with hard AC (code changes) |
| `doc-writer` | cheap | an explicit item list (mechanical docs) |
| `verifier` | mid | an AC list + gate commands (read-only check) |
| `researcher` | mid + web | a question or doc to refresh, citations required |

The wave mechanics that two live waves (June–July 2026) proved out:

1. **Plan files, not chat specs.** Each delegation gets a written plan with hard
   acceptance criteria and an explicit file scope; plans in the same wave never share
   files, so agents can run in parallel without conflicts.
2. **AC is the definition of done.** An agent that cannot meet an AC stops and reports
   the blocker; it does not improvise around it.
3. **Verify per wave.** The orchestrator (or the `verifier` role) runs the repo gates
   after each wave, before the next starts.
4. **Expect deaths.** Agents die mid-run (API errors); relaunch with a precise
   done/remaining map derived from the working tree, not from memory.
5. **Diff-check cheap-tier claims.** Reports from the cheap tier get compared against
   the actual diff before acceptance — measured failure mode: overstated docs claims.
6. **Statuses are structured.** `DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT`,
   with per-AC evidence, so the orchestrator parses instead of re-reading transcripts.

Claims discipline: the roles mechanize delegation; any token-savings number is a
hypothesis until the side-by-side measurement lands (see the design doc's follow-up).
```

Also: in the existing "The default pattern" section, add one sentence at the end of step
2 pointing at the roles, e.g. "With this repo's roles installed, delegate to
`implementer`/`doc-writer`/`verifier`/`researcher` instead of hand-authoring the
boilerplate." (1–2 lines max.)

Do not change the skill's frontmatter `description`.

## Change 2 — new conformance eval case (exact content)

`evals/conformance/cases/model-orchestration-shipped-roles.json`:

```json
{
  "id": "model-orchestration-shipped-roles",
  "rule": "When delegating in an environment where this config's agent roles are installed (implementer/doc-writer/verifier/researcher, each with a pinned model tier and a body carrying scope/status boilerplate), the skill routes sub-tasks through those roles instead of hand-authoring boilerplate prompts or running mechanical work on the strong tier.",
  "prompt": "This machine has the agentic-cfg agent roles installed (implementer=sonnet, doc-writer=haiku, verifier=sonnet, researcher=sonnet). I have a reviewed plan file at plans/x/01-fix.md with hard acceptance criteria: mechanical edits across 12 files, plus a docs sweep with an explicit item list. Drive it efficiently.",
  "expect": [
    "delegates the 12-file mechanical implementation to the implementer role (mid tier) rather than doing it inline on the strong tier",
    "routes the explicit-item docs sweep to the cheap-tier doc-writer role",
    "keeps verification separate (verifier role or explicit gate commands) before declaring done"
  ],
  "expect_not": [
    "hand-authors a from-scratch delegation prompt that duplicates the scope/status boilerplate the installed roles already carry",
    "runs the mechanical edits inline on the strong tier"
  ]
}
```

## Change 3 — docs (mechanization-only claims; no performance numbers)

1. `CHANGELOG.md`: new `0.14.0 (2026-07-02)` entry ABOVE 0.13.0, same style. Content —
   ONLY facts from this wave's plans 01+02, no adjectives: adds `core/agents/` (four
   subagent role definitions with pinned model tiers), rendered to `~/.claude/agents/`
   by the Claude installer and covered by `agentic inject/eject/status`; adds the
   Delegation-protocol section to `model-orchestration`; adds the ci-check agents
   section. Do NOT mention the docs/research or docs/guides refreshes — that work is
   outside this plan's scope and verification reach; the orchestrator appends those
   lines after diff-verifying them (wave B). FORBIDDEN: any token-savings or
   performance number (the design doc explicitly parks those as unmeasured).
2. `README.md`: if it has a repo-structure list/table mentioning `core/skills`, add
   `core/agents` alongside with a half-line description. If no such list exists, change
   nothing and report so.
3. `ARCHITECTURE.md`: same rule — extend the existing structure/render description with
   one short paragraph or table row: `core/agents/` → symlinked to `~/.claude/agents/`
   by `providers/claude/install.sh` (Claude-only; Cursor has no subagent equivalent).
4. `docs/README.md`: add one table row linking `plans/orchestration-agents/DESIGN.md`
   (as a markdown link with href `../plans/orchestration-agents/DESIGN.md`, relative to
   docs/) — "office-hours session #2: mechanized orchestration (agent roles as repo
   artifacts)".

## Acceptance criteria

1. `SKILL.md` contains the new section with the role table and all six numbered
   mechanics; net growth ≤ 45 lines (`git diff --stat` shown in report); frontmatter
   description unchanged (byte-identical).
2. The new JSON case is valid (`python3 -m json.tool`), and `python3 evals/lint.py`
   passes. Count the conformance cases BEFORE and AFTER your change (`find
   evals/conformance/cases -name '*.json' | wc -l`): after = before + 1, and report both
   observed numbers (do not assume a baseline — the working tree has unrelated pending
   eval-case deletions from an earlier wave). Coverage crediting works because the case
   `id` contains the skill name as a substring (`evals/lint.py` matches skill name
   against `rule + id`).
3. `python3 evals/selftest.py` passes.
4. CHANGELOG 0.14.0 entry present, above 0.13.0, contains NO numeric performance/token
   claim (grep for `%`, `token`, `×`/`x` factors in the new entry and justify each hit —
   expected hits: none, or purely descriptive like "model tiers"), and does NOT mention
   docs/research or docs/guides work.
5. README/ARCHITECTURE: either the structure mention is added, or the report states the
   file has no structure list (checked, not skipped).
6. `docs/README.md` row added and its relative link resolves (`test -f` the target from
   the docs/ directory).
7. `bash bin/ci-check.sh` exits 0.
8. `git status --porcelain` shows only this plan's files (plus pre-existing dirty files,
   listed at start, unchanged set at end).

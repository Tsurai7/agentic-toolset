# 05 — office-hours skill + eval

**Rationale:** [DESIGN.md](DESIGN.md) Part 1 — the improvement loop mandates an
office-hours vet, the upstream definition (gstack) is unreachable (404), and the
question set exists in-repo only as fragments across archived sessions. Codify it as one
on-demand skill with zero always-on prefix cost.

## Change specification

### `core/skills/office-hours/SKILL.md`

Frontmatter matching the other skills in `core/skills/*/SKILL.md` (inspect one, e.g.
`model-orchestration`, and copy the exact frontmatter shape). Description (the trigger —
keep to ~2 sentences):

> Pressure-test an idea before building it — premise challenge, status quo, evidence of
> value, narrowest wedge, risk, cost of keeping. Use when asked to vet/scope a proposal,
> decide whether something is worth adding ("стоит ли внедрять X"), or before writing an
> implementation plan for a new capability. Skip for bug fixes with an obvious cause and
> for work already scoped by an accepted plan.

Body (~1 page, hard cap 120 lines) containing exactly these sections:

1. **Provenance note** — adapted from the gstack `office-hours` skill; upstream
   (`github.com/DietrichGebert/gstack`) is no longer public (404 as of 2026-07-02); the
   question set below is the canonical in-repo reconstruction from our archived sessions
   (`archive/inject-eject-office-hours.md`, `archive/model-orchestration-office-hours.md`).
2. **The six forcing questions** (each with one sentence of guidance):
   - Q1 Premise challenge — restate the ask in your own words; is it the right problem?
     Reframe before answering if not.
   - Q2 Status quo — what already addresses this (the real competitor is rarely
     "nothing")? What is genuinely missing?
   - Q3 Evidence of value — who benefits and what measurable number moves?
   - Q4 Narrowest wedge — the smallest version shippable now; name what is explicitly
     out of scope.
   - Q5 Risk & verification — blast radius; which existing test/gate proves nothing
     broke, or what new one must ship with the change?
   - Q6 Cost of keeping — ongoing token/maintenance cost; what would make us remove it?
3. **Smart routing** (don't run all six every time):
   | Change type | Run |
   |---|---|
   | Pure infra/tooling | premise + Q2 + Q4 (+ Q5 when hooks/CI are touched) |
   | New user-facing capability or skill | Q1 + Q3 + Q4 + Q6 |
   | Recurring-cost change (always-on prefix, hooks on hot paths) | Q2 + Q4 + Q6 |
   | "Should we adopt X?" decisions | all six |
4. **Capture convention** — write the session to `docs/design/<topic>-office-hours.md`
   with an explicit **Verdict** section; move to `archive/` once shipped (per
   `archive/README.md`). End every vet with a verdict + the narrowest wedge, never with
   an open-ended options list.

### Eval case

`evals/conformance/cases/office-hours-vet-before-building.json` — follow the existing
case schema exactly (inspect `evals/conformance/cases/model-orchestration-*.json` for
shape). Sketch:

- `id`: `office-hours-vet-before-building` (must contain `office-hours` so
  `evals/lint.py` credits coverage).
- `rule`: names the `office-hours` skill: an "is it worth adding X?" ask must be vetted
  with the forcing questions (premise, status quo, narrowest wedge) before any
  implementation plan.
- `prompt`: e.g. "We should add a Redis-backed cache layer to this CLI tool so repeated
  runs are faster. Is it worth building? How would you approach it?"
- `expect`: challenges/restates the premise; names the status quo / existing alternative;
  proposes a narrowest first version; gives an explicit verdict.
- `expect_not`: jumps straight into implementation steps or code without questioning
  whether the capability is warranted.

### Pointer (non-prefix)

In `core/workflows/README.md`, where office-hours is currently referenced only via the
archived session link, add a clause pointing to the new skill (one line edit). Do **not**
touch `core/instructions/AGENTS.md`, `core/principles/`, or `core/instructions/user-rules/`
— the always-on prefix must stay byte-identical.

## Acceptance criteria (hard)

1. `python3 evals/lint.py` passes and its output counts one more covered skill than
   before (office-hours covered by the new case).
2. `bash bin/prefix-budget.sh` reports **exactly the same byte total as before the
   change** (8754 on this machine) — the always-on prefix is untouched.
3. `core/skills/office-hours/SKILL.md` exists, ≤120 lines, contains the provenance note,
   all six questions, the routing table, and the capture convention.
4. The eval case validates (lint), has both `expect` and `expect_not`, and its `id`
   contains `office-hours`.
5. `bash bin/ci-check.sh` passes.
6. Diff touches only: `core/skills/office-hours/SKILL.md`,
   `evals/conformance/cases/office-hours-vet-before-building.json`,
   `core/workflows/README.md`.

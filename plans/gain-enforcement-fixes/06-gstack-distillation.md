# 06 — gstack distillation: systematic-debugging skill, office-hours provenance fix, catalog entry

**Rationale:** [docs/design/gstack-adoption-office-hours.md](../../docs/design/gstack-adoption-office-hours.md)
— the gstack upstream exists locally at `/Users/tsurai/Documents/GitHub/gstack`; its
skills are runtime-coupled and cannot be vendored, but two method-level takes survived
the vet: a distilled debugging protocol from `/investigate`, and a provenance correction
to our office-hours adaptation. Plus a documented-but-disabled catalog entry.

## Change specification

### 1. `core/skills/systematic-debugging/SKILL.md` (new)

Read the method source first: `/Users/tsurai/Documents/GitHub/gstack/investigate/SKILL.md`
— extract the **method only** (ignore every preamble/telemetry/gbrain/AskUserQuestion
section; do not reference gstack binaries or `~/.gstack` paths). Read
`core/skills/office-hours/SKILL.md` for the frontmatter shape and provenance-note style.

Frontmatter description (the trigger, ~2 sentences):

> Systematic root-cause debugging: investigate before fixing, log hypotheses, trace data
> flow, and stop to reassess after 3 failed fix attempts. Use when debugging a
> non-obvious failure, when a fix attempt did not work, or when asked to find a root
> cause. Skip for trivial errors whose cause is stated in the error message.

Body (hard cap 100 lines) with exactly these sections:

1. **Provenance** — distilled from the gstack `/investigate` skill (local checkout,
   `/Users/tsurai/Documents/GitHub/gstack/investigate/SKILL.md`); method only, none of
   the gstack runtime.
2. **The Iron Law** — no fixes without investigation: reproduce first, read the actual
   error, locate the failing layer before editing anything.
3. **Hypothesis loop** — state the current hypothesis in one line before each probe;
   design the cheapest observation that can falsify it; record what each probe ruled
   out (in-conversation is fine — the point is an explicit trail, not a file format).
4. **Trace the data, not the blame** — follow the value through the layers
   (input → transform → output) until the first place reality diverges from expectation;
   fix at the divergence point, not at the symptom.
5. **The 3-strikes stop rule** — after 3 failed fix attempts, STOP: re-read the evidence,
   list what every failed attempt assumed in common, and question that shared assumption;
   escalate or ask rather than trying variant #4 of the same idea.
6. **Exit criteria** — a fix ships with the reproducing check that now passes (ties into
   `verification-before-completion`; reference that skill by name, don't restate it).

### 2. `core/skills/office-hours/SKILL.md` — provenance correction (edit in place)

Replace the current provenance paragraph (which says upstream is 404/unreachable) with:
upstream exists as a local checkout at `/Users/tsurai/Documents/GitHub/gstack`
(`office-hours/SKILL.md` v2.0.0; the GitHub URL is not public). Name upstream's
canonical six (demand reality, status quo, desperate specificity, narrowest wedge,
observation & surprise, future-fit) and state ours is a **deliberate adaptation**:
upstream's own smart-routing sends "pure engineering/infra" work to Q2+Q4 only, so the
four product-stage questions were replaced with repo-relevant ones (premise challenge,
evidence of value, risk & verification, cost of keeping). Keep the archived-sessions
links. Keep the file ≤120 lines.

### 3. `catalog/plugins.yaml` — gstack entry (documented, not enabled)

Read the file first and copy its exact entry schema/field style. Add a `gstack` entry
marked disabled/not-enabled (whatever the schema's convention is), with a comment or
description field noting: local checkout at `/Users/tsurai/Documents/GitHub/gstack`;
~60 skills; not enabled because each skill invocation runs a ~180-line preamble
(telemetry/config/gbrain) and the core review/ship/QA flows overlap Claude Code
built-ins; method-level distillations live in `core/skills/office-hours` and
`core/skills/systematic-debugging`.

### 4. Eval case

`evals/conformance/cases/systematic-debugging-stop-after-failures.json` — schema per the
existing cases. Sketch:

- `id`: `systematic-debugging-stop-after-failures` (contains the skill name — lint
  coverage credit).
- `rule`: names `systematic-debugging`: after repeated failed fix attempts the agent
  must stop and re-examine its shared assumption instead of trying another variant.
- `prompt`: a scenario — "I've tried three different fixes for this flaky test (added
  sleep 1s, then sleep 5s, then retry-on-failure) and it still fails intermittently in
  CI. Give me the next fix."
- `expect`: refuses to propose a fourth variant of the same idea; names the shared
  assumption of the prior attempts (timing/flakiness is the cause); proposes an
  investigation step (reproduce/trace the actual failure) before any new fix.
- `expect_not`: proposes another sleep/retry tweak without questioning the diagnosis.

## Acceptance criteria (hard)

1. `python3 evals/lint.py` passes; covered-skills count is one higher than before this
   plan (systematic-debugging covered).
2. `bash bin/prefix-budget.sh` byte total unchanged (no always-on files touched).
3. `core/skills/systematic-debugging/SKILL.md` exists, ≤100 lines, contains all six
   sections, references no gstack binary or `~/.gstack` path.
4. `core/skills/office-hours/SKILL.md` names upstream's canonical six and the local
   checkout path; the word "404" no longer appears in it; still ≤120 lines.
5. `catalog/plugins.yaml` parses (run whatever YAML check `bin/ci-check.sh` uses — the
   full `bash bin/ci-check.sh` must pass) and contains a gstack entry that is not
   enabled.
6. `bash bin/ci-check.sh` passes.
7. Diff touches only: `core/skills/systematic-debugging/SKILL.md`,
   `core/skills/office-hours/SKILL.md`, `catalog/plugins.yaml`,
   `evals/conformance/cases/systematic-debugging-stop-after-failures.json`.

# Impl 06: Weak-model reasoning-uplift scaffolds + model-aware render

**Implements:** [ADR-0006 — Ship weak-model reasoning-uplift scaffolds](../adr/0006-weak-model-reasoning-uplift.md)
**Status:** Proposed (not started)
**Wave:** 2 (content levers, gated by the Wave-1 measurement backbone)
**Depends on:** [ADR-0003](../adr/0003-eval-backbone-canary.md) differential-uplift harness + canary track (Wave 1); [MAT-07] byte-stable render and [MAT-08] minimal-context profile; [BUG-01..23] P0 hook hardening (the edit-lint hook reuses the corrected JSON-envelope handling).

## Scope and deliverables

Four reasoning-uplift content levers plus the render mechanics that let them ship
without taxing Opus, each with the conformance + value case `AGENTS.md` lines
54-56 require:

1. `core/skills/plan-first/SKILL.md` — fillable decomposition scaffold with two
   few-shot exemplars (bug-fix, refactor).
2. `core/skills/self-critique/SKILL.md` — bounded, conditionally-triggered
   self-critique checklist, distinct from external-evidence
   `verification-before-completion`.
3. `core/skills/answer-shapes/SKILL.md` — opt-in structured-output skeletons.
4. `providers/claude/hooks/edit-lint.sh` — deterministic Edit/Write syntax/lint
   guardrail hook, sibling to `shell-guard.sh`, wired into `settings.hooks.json`.
5. A **model-tier render dimension** in `providers/claude/install.sh` (and the
   shared render) keyed off `AGENTIC_TIER`, extending the MAT-07 golden with a
   per-tier byte-stability check.
6. Eval cases: one conformance + one value case per scaffold; the value cases use
   the `weak_uplift_exceeds_strong` pass condition from ADR-0003. Requires adding
   that pass condition to `evals/lib/cases.py:17`.

**Out of scope (referenced, not re-done):** the differential harness `evals/uplift.py`
and the `weak_uplift_exceeds_strong` verdict logic are owned by
[ADR-0003](../adr/0003-eval-backbone-canary.md)/impl-03; this plan only *consumes*
them and registers the pass-condition string. The quality proxies (edit-revert,
tool-error) that measure the lint hook's effect are owned by
[ADR-0002](../adr/0002-quality-latency-proxies.md)/impl-02.

## File-by-file changes

### 1. `core/skills/plan-first/SKILL.md` (new)

Frontmatter matching the existing skill convention
([`core/skills/verification-before-completion/SKILL.md:1-6`](../../core/skills/verification-before-completion/SKILL.md)):
`name: plan-first`, a `description` that triggers on multi-step coding tasks. Body
is the fillable scaffold:

```markdown
## Plan-first decomposition
1. Goal in one line: <restate>
2. Ordered sub-steps, each with a verifiable check:
   - [ ] step — check: <command/assertion that proves it>
3. Riskiest step: <which, and why>
4. Act on steps in order; tick each check after acting.
```

Then **two few-shot exemplars** (a filled bug-fix and a filled refactor) — these
are the weak-tier-only payload. Promote the prose at
[`core/principles/karpathy-guidelines.md:51`](../../core/principles/karpathy-guidelines.md)
("state a brief plan with a verifiable check per step") by linking to it as the
principle this skill operationalizes; do **not** delete or rewrite line 51 (surgical
scope — it stays the always-on principle, the skill is its executable form).

### 2. `core/skills/self-critique/SKILL.md` (new)

`name: self-critique`. Body: the bounded pre-completion checklist, explicitly
**distinct** from `verification-before-completion` (that skill gates on *external*
evidence — run the test; this one checks the model's *own reasoning*). Key
elements:

- **Trigger gate (load-bearing):** "Apply only to non-trivial or uncertain tasks.
  Do NOT apply to trivially-verified tasks — a critique loop helps below ~35% base
  accuracy and *hurts* above ~75%
  ([Snorkel](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/))."
- **Checklist:** restate the request; list each explicit requirement; for each,
  point at the output line that satisfies it; name one thing that could be wrong
  and check it.
- **Bound:** "Cap at one reflect iteration." (Prevents latency/token blow-up.)
- One weak-model-friendly few-shot exemplar (weak-tier only).

### 3. `core/skills/answer-shapes/SKILL.md` (new)

`name: answer-shapes`. A few fillable, **opt-in / task-triggered** output skeletons
(not always-on, to protect the prefix): bug-fix (root cause / fix / verification /
risk), code-review, investigation — each a few-line schema with one exemplar. Plus:
"When a step's output feeds another step (a plan, a route decision, a tool-arg
set), emit it against an explicit schema or enum." This is the parseable handoff
[ADR-0005](../adr/0005-model-tiering-routing.md) relies on for Opus→Haiku
delegation.

### 4. `providers/claude/hooks/edit-lint.sh` (new) + `settings.hooks.json` wiring

A sibling to [`providers/claude/hooks/shell-guard.sh`](../../providers/claude/hooks/shell-guard.sh).
**Reuse shell-guard's `extract()` JSON-envelope parser** (`shell-guard.sh:20-29`)
and its **fail-open discipline** verbatim — do not invent a new parser; the
BUG-01..23 hardening will have corrected `extract()` and this hook must inherit it.

```bash
# PostToolUse on Edit|Write|MultiEdit. Read tool_name + file_path from the envelope.
# Skip (exit 0) unless the path extension is one we can cheaply check.
case "$FILE" in
  *.py)        OUT=$(python3 -m py_compile "$FILE" 2>&1) || FAIL=1 ;;
  *.ts|*.tsx)  OUT=$(tsc --noEmit "$FILE" 2>&1)        || FAIL=1 ;;
  *.go|*.js|*.jsx|*.rs|...) OUT=$(ast-grep --lang <lang> -p '$X' "$FILE" 2>&1) || FAIL=1 ;;  # parse check
  *) exit 0 ;;   # fail open on unsupported languages
esac
# On FAIL, return the error to the agent so it retries before the bad edit persists.
```

Use **PostToolUse** on `Edit|Write|MultiEdit` (the edit has to exist on disk before
a syntax check can read it); the hook surfaces the lint error so the agent
self-corrects on the next turn. Fail **open** on any parser ambiguity, missing
tool, or unsupported language (Risk R4). Wire it into
[`providers/claude/settings.hooks.json`](../../providers/claude/settings.hooks.json)
as a new `PostToolUse` entry with matcher `Edit|Write|MultiEdit`, sibling to the
existing shell-guard `PreToolUse` entry at lines 4-13. Make it executable in
[`install.sh:90`](../../providers/claude/install.sh) (the existing
`chmod +x .../hooks/*.sh` already covers any new `.sh`).

### 5. Model-tier render dimension in `providers/claude/install.sh`

The render that builds the generated CLAUDE.md is
[`install_claude_md()` at `install.sh:33-71`](../../providers/claude/install.sh):
it concatenates the stub, `AGENTS.md`, every `core/principles/*.md`, and every
`core/instructions/user-rules/*.md`. Add a tier fork keyed off `AGENTIC_TIER`
(values `weak` | `strong`, default `strong` to keep Opus lean unless opted in):

```bash
TIER="${AGENTIC_TIER:-strong}"
# In the skill/scaffold render step:
#   weak  -> include the full SKILL.md body (scaffold + exemplars)
#   strong-> include only a one-line pointer ("Skill: plan-first — see core/skills/plan-first")
```

Implement the fork as a render helper so the three scaffold skills
(plan-first, self-critique, answer-shapes) share one code path. The exemplar blocks
must be the part dropped in strong-tier, since exemplars are what carry the
strong-model penalty
([Agarwal et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)). Keep the
render **byte-deterministic** per tier so each tier stays independently
cache-stable (extends MAT-07).

### 6. `evals/lib/cases.py` — register the new pass condition

At [`cases.py:17`](../../evals/lib/cases.py) today:

```python
PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse"}
```

Add the differential pass condition (the verdict itself is implemented in impl-03):

```python
PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse", "weak_uplift_exceeds_strong"}
```

This is the only edit this plan makes to `cases.py`; it lets the scaffold value
cases declare the differential gate without a schema-validation error at
[`cases.py:60-62`](../../evals/lib/cases.py).

### 7. Eval cases (new files under `evals/`)

Per scaffold, one conformance case (`evals/conformance/cases/`) and one value case
(`evals/value/cases/`):

- **plan-first** — value: a multi-step refactor prompt; `pass_condition:
  weak_uplift_exceeds_strong`; rubric scores whether the response decomposed before
  acting. Target: Haiku margin − Opus margin ≥ 0.20.
- **self-critique** — value: a prompt with a buried second constraint ("do X and
  ALSO ensure Y"), run at an EASY and a HARD band (a prompt's band is assigned by
  the control arm's measured base pass-rate on it: EASY when control passes > 75%,
  HARD when < 35% — the Snorkel paradox zones); rubric scores both constraints;
  PASS only if Haiku's satisfies-both gain exceeds Opus's **AND** the EASY band is
  not regressed by critique (Risk R1). Conformance: a should-trigger and a
  should-NOT-trigger case for trigger precision.
- **answer-shapes** — conformance: a bug-fix prompt; `expect: ["root cause", "fix",
  "verification"]`. Value: completeness/structure scored under Haiku vs Opus;
  `weak_uplift_exceeds_strong`.

## Why each change (one cited finding + impact figure each)

- **plan-first scaffold** — least-to-most decomposition took text-davinci-002 from
  **6% to 76%** on SCAN versus **16%** for CoT
  ([Zhou et al., arXiv:2205.10625](https://arxiv.org/abs/2205.10625)); Cursor calls
  planning "the most impactful change"
  ([Cursor](https://cursor.com/blog/agent-best-practices)). Highest-leverage Goal-1
  lever.
- **self-critique scaffold** — Reflexion hit **91% vs 80% pass@1** on HumanEval
  ([Shinn et al., arXiv:2303.11366](https://arxiv.org/abs/2303.11366)); but the
  paradox (<35% helps, >75% hurts,
  [Snorkel](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/))
  is why it is conditional and two-band-validated.
- **answer-shapes scaffold** — strict-JSON lifts a **1B model 15.2%→39.0%** and a
  **1.5B model 49.4%→73.9%**; a constrained 7B beat an unconstrained 70B
  ([Geng et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)). Outsized
  small-model gain, and the parseable handoff for [ADR-0005] delegation.
- **edit-lint hook** — removing linting drops SWE-agent resolve rate **15.0%
  relative**; **51.7%** of trajectories hit a failed-lint edit
  ([Yang et al., arXiv:2405.15793](https://arxiv.org/abs/2405.15793)). Weak models
  produce more malformed edits, so the gate disproportionately lifts them.
- **model-tier render** — bloated instruction files make strong models ignore
  instructions
  ([Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)),
  and exemplars hurt strong models
  ([Agarwal et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)); the
  tier fork is what lets the scaffolds ship without taxing Opus's prefix or cache.

## Build order (step by step)

1. **Register the pass condition** — edit `evals/lib/cases.py:17`; run
   `python3 evals/selftest.py` to confirm nothing breaks. (Unblocks writing the
   value cases.)
2. **Author the three scaffold skills** (`plan-first`, `self-critique`,
   `answer-shapes`) with exemplars. No render change yet — they read as ordinary
   skills.
3. **Add the model-tier render fork** to `install.sh:33-71`; add a per-tier
   byte-stability golden (extends MAT-07). Verify `AGENTIC_TIER=strong` render is
   byte-smaller than `AGENTIC_TIER=weak`.
4. **Write the edit-lint hook** reusing shell-guard's parser; wire it into
   `settings.hooks.json` as a `PostToolUse` Edit/Write entry; confirm it fails open.
   (Land only after BUG-01..23 — Risk R4.)
5. **Author the conformance + value cases** per scaffold; run them through
   `evals/run.py` on Haiku and Opus and through `evals/uplift.py` (ADR-0003) to
   confirm the differential gate evaluates.
6. **Run the canary** (ADR-0003/0004) before and after each scaffold to capture the
   ≥15pp Haiku / <5pp Opus target.

## Validation commands and targets

- `python3 evals/lint.py` — the new cases pass schema validation (the
  `weak_uplift_exceeds_strong` pass condition is now accepted at `cases.py:60-62`).
- `python3 evals/selftest.py` — green after the `cases.py:17` edit.
- `python3 evals/run.py --track value --model claude-haiku-4-5-20251001` and
  `--model claude-opus-4-8`, then `python3 evals/uplift.py` — each scaffold value
  case is `treatment_preferred` on Haiku with `flip_rate < 0.10` **and** the
  Haiku−Opus differential ≥ **0.20**.
- **Canary** (ADR-0003): on the 10-task multi-step suite, **Haiku success +≥15pp,
  Opus +<5pp** with the plan-first scaffold active.
- **Self-critique two-band value case:** PASS only if the EASY band is not regressed
  and the HARD-band Haiku gain exceeds Opus (Risk R1).
- **Edit-lint telemetry** (ADR-0002 proxies over real transcripts): Haiku/Sonnet
  **edit-error / edit-revert rate down ≥ 30%** over a 20-session window.
- **Render / cache:** `AGENTIC_TIER=strong` golden byte-smaller than `weak` and
  stable across runs; `python3 telemetry/gate.py` shows weighted cache hit ≥ 0.85
  (gate fails < 0.80) before-vs-after each prefix edit.
- `bin/ci-check.sh` — the repo's aggregate gate stays green.

## Dependencies and sequencing

- **Wave placement:** Wave 2. The content levers are only falsifiable once the
  Wave-1 backbone exists.
- **depends_on:**
  - ADR-0003 differential-uplift harness (`evals/uplift.py`) + the
    `weak_uplift_exceeds_strong` verdict + the canary track in `cases.py` — this
    plan registers the pass-condition string and consumes the verdict.
  - MAT-07 byte-stable render + MAT-08 minimal-context profile — the tier fork
    extends these.
  - BUG-01..23 P0 hook hardening — the edit-lint hook reuses the corrected
    `extract()` envelope handling (Risk R4); it must land after.
  - ADR-0002 quality proxies (edit-revert, tool-error) — measure the lint hook's
    effect.
- **Enables:** ADR-0005's Opus→Haiku delegation (answer-shapes parseable handoff);
  ADR-0007's flywheel can harvest real weak-model failures into new scaffold
  exemplars.

## Risks and mitigations

- **R1 — self-critique paradox, no runtime accuracy gate** (critique P1-7): the
  two-band value case fails if critique regresses the EASY band; the conformance
  case measures trigger precision but not help/harm, so the value case is the real
  guard.
- **R2 — scaffolds add prefix bytes that tax Opus/cache** (critique P2-13): the
  model-tier render keeps full scaffolds + exemplars off the strong tier; run
  `telemetry/gate.py` before/after each prefix edit and block on a cache-hit drop.
- **R3 — equal uplift masquerades as a win** (the differential proof): every value
  case passes only at Haiku−Opus margin ≥ 0.20 via `evals/uplift.py`; the harness
  must normalize `claude-haiku-4-5-20251001` / `claude-opus-4-8` to tier labels.
- **R4 — hook on un-hardened plumbing**: land after BUG-01..23; reuse shell-guard's
  parser; fail open on ambiguity, missing tool, or unsupported language.

## Effort and checklist

Effort: **L** (four content artifacts, a hook, a render dimension, two goldens,
six eval cases). The scaffolds themselves are M; the model-tier render fork and the
per-tier golden are the L driver.

- [ ] `evals/lib/cases.py:17` adds `weak_uplift_exceeds_strong`; `selftest.py` green
- [ ] `core/skills/plan-first/SKILL.md` with two exemplars
- [ ] `core/skills/self-critique/SKILL.md` with trigger gate + one-iteration bound
- [ ] `core/skills/answer-shapes/SKILL.md`, opt-in
- [ ] `providers/claude/hooks/edit-lint.sh` reusing shell-guard's parser, fail-open
- [ ] `settings.hooks.json` PostToolUse Edit/Write entry wired
- [ ] `install.sh` model-tier render fork keyed off `AGENTIC_TIER`; per-tier golden
- [ ] conformance + value case per scaffold; self-critique value case is two-band
- [ ] differential ≥ 0.20 on each scaffold; canary Haiku +≥15pp / Opus +<5pp
- [ ] edit-error rate down ≥ 30% on Haiku/Sonnet; cache hit ≥ 0.85 post-edit

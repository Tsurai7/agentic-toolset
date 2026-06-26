# W4 — Cheap uplift (make the weak model smarter without breaking the budget)

> Parent: [../06-overhead-and-uplift.md](../06-overhead-and-uplift.md). Adopts and
> **reprioritizes** ADR-0006 (weak-model reasoning uplift) on branch `722d6e2`. Gated on
> W1–W3 proving the ratio is under control.

## Goal

Add weak-model reasoning uplift, but ordered by **token cost**, so the ≤1.5× gate from
[W3](03-overhead-kpi-and-gate.md) is never breached to buy capability. Every lever must
clear two gates: the **≤1.5× overhead gate** *and* ADR-0003/0006's **differential floor**
(`weak_margin − strong_margin ≥ 0.20`, `flip_rate < 0.10`) — a scaffold that helps both
models equally is a token regression dressed as a win.

## Why reprioritize ADR-0006

ADR-0006 lists four levers; their token costs differ sharply (from the ADR digest):

| Lever | Claimed gain | Token cost | W4 order |
|---|---|---|---|
| **Answer-shapes** (opt-in structured output skeletons) | strict-JSON lifted a 1B model 15→39%, a 1.5B 49→74%; constrained 7B beat unconstrained 70B | **~neutral / can save** (opt-in, not always-on; parseable handoff avoids re-asks) | **1st** |
| **Edit-lint hook** (PostToolUse parse check) | removing lint dropped SWE-agent resolve 15% rel.; 51.7% of trajectories hit a failed-lint edit | **prefix-neutral** (a hook, not prefix text); prevents costly revert round-trips | **2nd** |
| **Conditional self-critique** (one bounded reflect, trigger-gated) | Reflexion 80→91% pass@1 | **adds tokens** (extra pass + body); paradox: helps <35% base, **hurts >75%** → must be conditional & weak-tier-only | **3rd** |
| **Plan-first** (decompose template + 2 exemplars) | least-to-most 6→76% on SCAN | **adds the most** (template + exemplars) | **4th, weak-tier-render only** |

## Changes (concrete)

1. **Answer-shapes first.** Add `core/skills/answer-shapes/SKILL.md` (opt-in skeletons:
   bug-fix, code-review, investigation). Not always-on — task-triggered. Verify it is
   token-neutral on the prefix (W2 budget) and reduces orchestrator re-asks (a structured
   worker reply an Opus caller consumes without a follow-up question).

2. **Edit-lint hook second.** Add `providers/claude/hooks/edit-lint.sh` (PostToolUse on
   Edit/Write/MultiEdit; `py_compile` / `tsc --noEmit` / `ast-grep --lang` parse check;
   **fail-open**; reuse the Go `agentic hook` plumbing and shell-guard's `extract()`).
   Budget: < 50 ms/call (ADR-0006). Prefix cost: zero (it is a hook). Target: Haiku
   edit-revert rate down ≥ 30% over a 20-session window (ADR-0002 metric).

3. **Conditional self-critique third.** Add `core/skills/self-critique/SKILL.md` with a
   **trigger gate** (fire only when the task is hard / base accuracy is low) and a
   **one-iteration bound**. Two-band value case (EASY: control passes >75% — must NOT
   regress; HARD: control passes <35% — must improve). Render weak-tier-only.

4. **Plan-first last, weak-tier-render-only.** Add `core/skills/plan-first/SKILL.md`
   (fillable template + 2 exemplars). Ship the exemplar-heavy body **only** through the
   ADR-0006 model-tier render fork on the weak tier (strong tier gets a one-line pointer),
   so the bytes that lift Haiku never reach Opus's prefix — and the weak-tier render still
   must fit the W2 budget.

5. **Author correctness-uplift cases.** The 2026-06-26 hard task showed uplift as
   *efficiency* (both arms correct). To demonstrate **correctness** uplift, author 2–3
   harder cases under `evals/value/` and `evals/canary/` where bare Haiku actually fails
   (e.g. multi-file impact where grep misses a call site; noisy-output triage where
   compression prevents context overflow). Each scaffold is accepted only if it lifts the
   weak arm on these.

## Validation

For every lever, on the [W3](03-overhead-kpi-and-gate.md) instrument:

- **Overhead gate:** easy-regime ratio stays ≤ 1.5 and hard-regime ≤ 1.0 *after* the
  lever is added (no scaffold may push the prefix or turn count past budget).
- **Differential floor:** `weak_margin − strong_margin ≥ 0.20`, `flip_rate < 0.10`
  (`evals/uplift.py`, ADR-0003).
- **Self-critique two-band:** fails if it regresses the EASY band.
- **Edit-lint:** edit-error/edit-revert rate down ≥ 30% (ADR-0002), parse-check overhead
  < 50 ms.

## Projected gain

Capability uplift on hard/weak-model tasks (per ADR-0006's cited deltas) **at ≤1.5×
overhead**, because the cheap levers are token-neutral and the expensive ones are gated +
weak-tier-only. No quantified token *saving* here — W4 spends a controlled token budget to
buy capability, bounded by W3's gate.

## Risks

- **Stacking cost.** Four scaffolds together could creep the weak-tier prefix past budget
  even if each passes alone. Mitigate: re-run the W3 gate after *each* lever and on the
  full stack; the budget is on the *rendered prefix*, not per-skill.
- **Self-critique paradox.** Blanket self-critique hurts easy tasks. Mitigate: hard
  trigger gate + the EASY-band no-regression test.
- **Exemplar penalty on strong models.** Exemplars carry a documented strong-model
  penalty — hence plan-first is weak-tier-render-only.

## Decisions for the owner

- Adopt all four levers (in this order) or stop after the token-cheap two (answer-shapes +
  edit-lint)? Recommended: ship the cheap two, measure, then decide on self-critique /
  plan-first based on the W3 numbers.
- Merge the ADR-0006 render fork from `722d6e2` as the delivery mechanism, or re-author?
  (Recommended: merge the fork plumbing; it is the prerequisite for weak-tier-only content.)

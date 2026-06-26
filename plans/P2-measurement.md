# P2 — north-star measurement (token-delta + bounded Haiku sample)

What was built for measurement, the first real numbers, and what they imply.
Companion to [00-master-plan.md](00-master-plan.md) and [05-test-coverage.md](05-test-coverage.md).

## Instrument: real token usage per arm

`evals/lib/agent.py` `metrics()` now parses the terminal stream-json `result`
event's `usage` (input / output / cache-read / cache-creation, plus a derived
`total_input_tokens`) in addition to tool-call count and transcript size. The
value track records `metrics()` per arm, so every A/B run now yields a **measured
token delta** between treatment and control, not just a transcript-size proxy
(doc 05 TEST-11). Covered by `evals/selftest.py::test_metrics_parses_token_usage`.

## First bounded sample (Haiku, n=1, illustrative)

A read-only code-search task ("find every Go function whose last return type is
`error`") run on `claude-haiku-4-5` in a throwaway scratch repo, toolset-on (real
config) vs toolset-off (prompt-isolation: instructed to use only plain tools).

| metric | toolset ON | toolset OFF |
|--------|-----------:|------------:|
| answer correct | yes (A,B,D,E = 4) | yes (A,B,D,E = 4) |
| tool calls | 10 | 5 |
| total input tokens | 335,085 | 115,905 |
| output tokens | 2,563 | 958 |
| transcript chars | 64,719 | 27,480 |

### Honest reading

- **On an easy task the toolset is net overhead, not uplift.** Both arms reached
  the same correct answer; toolset-on cost ~2.9× the input tokens and 2× the tool
  calls. `cache_read` is cumulative across turns, so the gap is roughly
  (more turns) × (heavier per-turn prefix ~32k vs ~20k).
- **Implication 1 — measure uplift on hard tasks.** A weak model already succeeds
  here unaided, so this task cannot show uplift. The Haiku-uplift case suite must
  use tasks where the *control* arm fails or flails (multi-step refactors,
  cross-file impact, noisy-output triage) — that is where the guidance/tools earn
  their prefix cost. This is the next eval-authoring step.
- **Implication 2 — the always-on prefix is a real cost (validates P3).** ~12k
  extra input tokens per turn from the loaded instruction/skill layer compounds
  every turn. This is concrete evidence for P3's instruction de-dup (doc 02
  MAT-05: triple-stated "verify-before-done", coding-principles/Karpathy overlap)
  and for a "minimal-context" rendered profile for short/cheap tasks (doc 02).

### Caveats

n=1, single task, Haiku only, **prompt isolation** (the control arm still loads
the full config and is merely *told* to ignore it — medium confidence, per
`evals/README.md`). These numbers are illustrative of the method and the
overhead, not a verdict on the toolset's value. A fuller, judged suite (multiple
hard tasks, n≥3, config-dir isolation under an API key) is the follow-up, gated on
the cost decision.

## Status

- Token-delta instrument: shipped (`732fd39`), covered by selftest.
- Bounded Haiku sample: run, recorded above.
- Follow-ups: author hard-task Haiku-uplift cases; run a judged suite (cost-gated);
  act on the prefix-overhead finding in P3 (de-dup + minimal-context profile).

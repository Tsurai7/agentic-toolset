# ADR-0003: Build a falsifiable eval backbone — differential-uplift harness, deterministic canary, and judge calibration

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** measurement, weak-model, process
- **Related:** [ADR-0001](0001-real-usage-measurement-baseline.md) (real-usage baseline + session reconstruction), [ADR-0002](0002-quality-latency-proxies.md) (quality/latency proxies), [ADR-0004](0004-gain-scorecard-experiment.md) (the `gain` scorecard that consumes these signals), [ADR-0005](0005-model-tiering-routing.md) (routing, which this backbone gates), [ADR-0006](0006-weak-model-reasoning-uplift.md) (the scaffolds this backbone makes falsifiable), [ADR-0007](0007-adoption-flywheel.md) (the harvester that feeds canary rotation). Implementation plan: [`plans/impl/03-eval-backbone-canary.md`](../impl/03-eval-backbone-canary.md). Prior corpus (read-only): [`plans/05-test-coverage.md`](../05-test-coverage.md) TEST-08 (the "works together" E2E prompts), TEST-10 (Haiku-uplift suite), TEST-11 (per-arm token capture), TEST-14 (multi-sample judge); [`plans/02-maturity-review.md`](../02-maturity-review.md) MAT-09 (conformance firing), MAT-10 (weak-agent regression gate).

## Context and problem statement

The repository already owns a real eval harness: two tracks (`conformance`, `value`) plus a non-LLM `metric` track in [`evals/run.py`](../../evals/run.py), a position-bias-controlled pairwise judge in [`evals/lib/judge.py`](../../evals/lib/judge.py), and pure-logic self-tests in [`evals/selftest.py`](../../evals/selftest.py). That harness is good enough to ask "did a skill change behavior?" but it cannot answer the two questions this uplift program lives or dies on:

1. **Is a reasoning scaffold actually weak-specific, or is it dead weight on Opus?** The value track compares treatment-vs-control *within one model* (`run_value` at [`run.py:62-106`](../../evals/run.py)). It has no way to express a delta-of-deltas — "the uplift on Haiku exceeds the uplift on Opus." [`plans/05-test-coverage.md`](../05-test-coverage.md) TEST-10 asserts exactly this property, but only in prose. Without a falsifiable differential, a scaffold that helps both models equally (and therefore wastes Opus prefix tokens, working against Goal 2) is indistinguishable from one that closes the weak-strong gap (serving Goal 1).

2. **Is a change a real improvement, or did we just get lucky once?** `run_conformance` ([`run.py:48-57`](../../evals/run.py)) runs each case **exactly once** and grades it PASS/FAIL. A single trial cannot distinguish "Haiku reliably prefixes `rtk`" from "Haiku prefixed `rtk` this time." Reliability — not best-case capability — is what makes a weak model trustworthy unattended.

This matters because the owner's real telemetry shows the measurement surface is noisy and confounded. The 205-session corpus is Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 assistant records, with `isSidechain=true` on 28% of records and only 452 of 3948 user turns carrying text. Real-session quality proxies (tool-error rate, edit-revert rate) are therefore rare-event signals at personal-usage scale: a routing change that silently lowers Haiku's quality can hide inside daily task-mix noise for an entire measurement week. We need a *controlled, frozen, task-mix-normalized* quality signal that does not depend on the day's workload — and it must be cheap, because the heavy model is governed by subscription usage limits, not per-token billing, so an expensive eval suite directly consumes the Opus headroom Goal 2 is trying to protect.

The gap, precisely: the harness can run an A/B, but it produces **no longitudinal time series**, **no reliability number**, **no weak-vs-strong differential**, and **no deterministic (judge-free) quality check** — and its judge is uncalibrated against any ground truth. Every content decision in [ADR-0005](0005-model-tiering-routing.md) and [ADR-0006](0006-weak-model-reasoning-uplift.md) is unfalsifiable until this backbone exists.

## Decision drivers

- **Goal 1 (weak-model uplift) must be *provable*, not asserted.** A scaffold ships only if a number shows it helps the weak model more than the strong one.
- **Goal 2 (less Opus consumption / latency) constrains the eval itself.** The measurement apparatus cannot itself become a major Opus token sink. Per the cost-framing correction, the primary cost is Opus token consumption against subscription caps, so the eval backbone must prefer **zero-LLM deterministic checks** and reserve LLM-judge A/Bs for periodic spot-checks (critique P2-9).
- **Balanced scorecard, never one KPI.** A change is accepted on the joint scorecard ([ADR-0004](0004-gain-scorecard-experiment.md)); a canary that improves while the quality proxies regress is a rejection, not an acceptance (critique P1-6).
- **Falsifiability and attribution.** Every signal must be reproducible day-over-day on a frozen task set so a measured move is attributable to a config change, not to that week's task mix.
- **Honest units.** Reliability (`pass^k`), not best-of-k capability, is the weak-model trust metric; a judge is trusted only after it is calibrated against human labels.

## Considered options

1. **Keep the current single-shot harness; argue uplift from the within-model value track and real-session proxies.** No new code; rely on TEST-10's prose claim and the noisy daily metrics.
2. **Add an LLM-judge-heavy longitudinal suite** — re-grade a large rotating prompt set daily with the pairwise judge and a scored rubric, treating the judge as the primary signal.
3. **Build a layered backbone (chosen):** a deterministic-first canary track for the longitudinal signal, a differential-uplift reporter (`evals/uplift.py` + a `weak_uplift_exceeds_strong` verdict) for weak-specificity, a `pass^k` reliability extension to conformance, trajectory grading and a scored 0-1 judge mode as cheap quality signals, and reference-anchored judge calibration — with deterministic/trajectory graders as the primary signal and the LLM judge reserved for periodic spot-checks.

## Decision outcome

**Chosen: Option 3 — the layered, deterministic-first eval backbone.** It is the only option that makes later content changes falsifiable while respecting the Opus token budget Goal 2 protects. Concretely, this ADR commits to six interlocking pieces, each grounded in a primary source from the research digest.

**A deterministic, scheduled canary track.** We add a `canary` track to [`evals/lib/cases.py`](../../evals/lib/cases.py) (which validates only `conformance`/`value`/`metric` today, [`cases.py:21-22`](../../evals/lib/cases.py)) and a `run_canary` runner. Each canary case carries a `deterministic_check` — a script returning 0/1 (every Bash command `rtk`-prefixed; the exact `ast-grep` call-site set produced; an edit makes a fixture test pass) — so the daily signal is **judge-free wherever possible**. A scheduler (`mcp__scheduled-tasks__create_scheduled_task` / cron, available in this environment) runs the suite daily on a pinned model and appends tokens, tool-call count, latency, and `pass@1` to a committed `evals/canary/history.jsonl`. The justification is the benchmark literature: Terminal-Bench grades strict Pass@1 with no judge, and SWE-bench Verified grades by running tests, precisely to remove judge variance from the longitudinal signal ([Terminal-Bench 2.0](https://explainx.ai/blog/terminal-bench-2-0-ai-agent-benchmark-evaluation); [OpenAI evals guide](https://developers.openai.com/api/docs/guides/evals)). Deterministic checks cost zero judge tokens and have zero judge variance, which is exactly what a flat-or-up daily trend needs to be readable.

**A differential-uplift harness.** New `evals/uplift.py` reads `results/<weak>/` and `results/<strong>/` for the same case id and emits `weak_margin − strong_margin` per artifact against a configurable floor (default `0.20`), surfaced through a new `weak_uplift_exceeds_strong` `pass_condition` in [`cases.py`](../../evals/lib/cases.py) and a verdict in [`run.py`](../../evals/run.py). This is the construct that makes weak-specificity falsifiable rather than asserted: the differential is the only thing that distinguishes a scaffold that closes the weak-strong gap from one that helps both models. The methodology is corroborated by the finding that exemplar/in-context benefit is inversely related to model strength — many-shot ICL and reference-anchored scaffolds help weaker models more ([VLRMBench / many-shot ICL synthesis, arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)) — so a positive weak-minus-strong differential is the expected signature of a working scaffold.

**A `pass^k` reliability metric.** `run_conformance` ([`run.py:48-57`](../../evals/run.py)) gains a `--k` flag and emits `pass^k` per case (the fraction of cases where **all k** repeats pass), with a gate that fails if `pass^5` on the Haiku conformance set drops below target. tau-bench shows best-of-k `pass@k` overstates reliability badly — gpt-4o was `pass^8 < 25%` in retail despite ~50% single-trial success ([tau-bench, arXiv:2406.12045](https://arxiv.org/abs/2406.12045)) — so a change that lifts Haiku's mean but makes it more erratic passes a mean-based gate and fails `pass^k`, catching exactly the regression the current single-shot harness misses. Because conformance runs each case once today, `--k` is genuinely new code, not a flag tweak, and gets its own self-test.

**Trajectory grading.** Each conformance/canary case gains an optional `reference_trajectory` (ordered tool names); we compute `in_order_match` + precision + recall from the tool calls `agent.metrics()` already extracts ([`agent.py:74-95`](../../evals/lib/agent.py)) — **zero LLM cost**. Vertex's agent-eval computes exactly these trajectory metrics because "it's not enough to check outputs; understand the path" ([Vertex agent evaluation](https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service)). For weak models this surfaces tool-misuse regressions — grepping source instead of `ast-grep`, skipping `rtk` — that a final-answer judge hides, and it does so deterministically.

**A scored 0-1 judge mode.** Beside the existing PASS/FAIL and `FLIP_THRESHOLD` pairwise logic in [`judge.py`](../../evals/lib/judge.py), we add a rubric-scored mode that returns a 0-1 score with explicit criteria and a `pass_threshold`. OpenAI's grader guidance is that a graded score "produce[s] a smooth score, not a pass/fail stamp," which detects small uplift/regression where a binary flips noisily ([OpenAI graders](https://developers.openai.com/api/docs/guides/graders)). The scored mode feeds the canary's optional quality dimension so day-over-day variance is small enough to distinguish a real change from noise.

**Reference-anchored judge calibration.** We add a `reference`/gold-answer field to value and conformance cases, a small human-labeled calibration set under `evals/judge_calibration/`, and a script reporting judge-vs-human divergence that fails above 25%. Documented judge biases are large — position bias up to 75% first-slot preference, self-preference from −38% to +90% on ArenaHard ([CalibraEval, arXiv:2410.15393](https://arxiv.org/pdf/2410.15393); [Self-Preference Bias, arXiv:2410.21819](https://arxiv.org/abs/2410.21819)) — so an uncalibrated judge makes every Haiku-uplift and routing cost A/B claim suspect. The value track already controls position via order-swap (good), but uses no reference answers and no human calibration.

### Consequences

**Good.**
- Every content change in ADR-0005/0006 becomes falsifiable: a scaffold ships only when `uplift.py` shows `weak_margin − strong_margin ≥ 0.20`, and routing ships only when the deterministic canary holds flat-or-up.
- The deterministic canary and trajectory grader give a **zero-LLM-token primary signal**, directly honoring the Goal-2 eval budget.
- `pass^k` converts the harness from a capability check into a reliability check — the property that actually licenses delegating work to Haiku unattended (ADR-0005).
- A calibrated judge means the spot-check A/Bs we *do* spend Opus tokens on are trustworthy.

**Cost.**
- New code: `evals/uplift.py`, `evals/canary/` with cases + `history.jsonl`, the `canary` track and `weak_uplift_exceeds_strong` verdict, the `--k`/`pass^k` path, the scored judge mode, the trajectory grader, the calibration set + script, and matching self-tests.
- A standing meta-cost: each scheduled canary run spends some tokens on a pinned model. This is bounded by an explicit eval-token budget (below) and kept small by making deterministic checks the default.

**Risks and mitigations** (critique points folded in as named risks):

- **R1 — Canary Goodhart / overfitting to the frozen prompts (critique P1-6).** A tiny fixed suite reused as both the optimization target and the longitudinal metric invites unconscious fitting. *Mitigation:* hold out a **rotating subset** of canary cases (an `active`/`holdout` split in `history.jsonl`), wire [ADR-0007](0007-adoption-flywheel.md)'s `harvest.py` output **into** canary rotation so the suite refreshes from real observed failures, and adopt the hard rule that **no config change is accepted solely because the canary improved** — it must also hold on the joint scorecard ([ADR-0004](0004-gain-scorecard-experiment.md)).
- **R2 — Eval meta-cost works against Goal 2 (critique P2-9).** Value A/Bs at n≥5 across two models, the differential harness, and judge-calibration runs are themselves Opus/Sonnet spend during the measurement window. *Mitigation:* state an explicit **eval-token budget** (below); make the **zero-LLM deterministic canary + trajectory grader the primary daily signal**; reserve LLM-judge differential A/Bs for a **weekly/periodic spot-check**, never daily.
- **R3 — Write-path value cases trusting only a pairwise judge (critique P2-12).** A cheaper editor model can emit a subtly-wrong-but-plausible diff that a verbosity-biased pairwise judge waves through. *Mitigation:* every write-path value/canary case **must** include an apply-and-run-tests `deterministic_check` (SWE-bench-style: does the edit make a fixture test pass), not only a pairwise judge. The pairwise judge is advisory; the deterministic test is dispositive.
- **R4 — `results/<model>/` keyed on raw `--model` strings won't match across tiers (minor critique).** `run_value` writes `results/<model_label>/` from the raw `--model` string ([`run.py:63-64`](../../evals/run.py)), e.g. `claude-haiku-4-5-20251001`. *Mitigation:* `uplift.py` normalizes raw model ids to **tier labels** (`weak`/`mid`/`strong`) via a small map before matching case ids across directories, and filters `<synthetic>` records.
- **R5 — `pass^k` is real new code, not a flag (minor critique).** Conformance runs each case once today, so `--k` adds a repeat loop and an all-pass reduction. *Mitigation:* give the `pass^k` reducer its own pure-logic self-test in [`selftest.py`](../../evals/selftest.py), mirroring the existing `_value_verdict` tests at [`selftest.py:44-52`](../../evals/selftest.py).
- **R6 — Judge calibration can't fix what it can't see.** Self-preference bias is family-correlated. *Mitigation:* where feasible, prefer a **different-family judge model** for spot-check A/Bs (the digest's calibration proposal), and treat the 25% divergence gate as a release blocker for any judge-graded scorecard row.

## Pros and cons of the options

**Option 1 — keep the single-shot harness.**
- *Pro:* zero new code; lowest immediate token cost.
- *Con:* leaves the program's two central claims (weak-specific uplift, reliability) unfalsifiable; TEST-10 stays prose. No longitudinal signal, so a routing regression hides in daily noise for a week. This is the status quo the digest critique calls the single highest-value gap to close.

**Option 2 — LLM-judge-heavy longitudinal suite.**
- *Pro:* a scored rubric is smooth and catches small moves a binary misses.
- *Con:* directly violates the Goal-2 eval budget — daily LLM grading of a rotating set is a standing Opus/Sonnet token sink, and judge variance/bias (position up to 75%, self-preference up to +90%) makes the day-over-day trend itself noisy unless calibrated, which adds yet more runs. The benchmark SOTA (Terminal-Bench, SWE-bench) deliberately moves *away* from judges for the reproducible signal.

**Option 3 — layered deterministic-first backbone (chosen).**
- *Pro:* deterministic + trajectory graders give a zero-token, zero-variance primary signal; `pass^k` adds reliability; `uplift.py` adds falsifiable weak-specificity; the scored judge and calibration are reserved for periodic spot-checks. Serves both goals: provable Goal-1 uplift, bounded Goal-2 eval cost.
- *Con:* the most new code and the most moving parts; requires discipline to keep the canary suite from being overfit (mitigated by R1).

## Validation — how we confirm it worked

This backbone is validated by its own self-tests plus named target numbers on the live harness (all reproducible from a throwaway scratch repo per [`run.py`](../../evals/run.py)'s isolation convention):

- **Differential harness, self-test:** in [`selftest.py`](../../evals/selftest.py), two synthetic result files where `weak_margin > strong_margin` expects PASS and equal margins expects FAIL (mirrors the existing verdict tests at [`selftest.py:44-52`](../../evals/selftest.py)). **Live target:** on the plan-first scaffold case across Haiku and Opus, `uplift.py` reports **`weak_margin − strong_margin ≥ 0.20`** with `flip_rate < 0.10`.
- **`pass^k`, self-test + live:** a pure-logic test of the all-pass reducer in `selftest.py`. **Live target:** `evals/run.py --track conformance --k 5 --model claude-haiku-4-5-20251001` emits `pass^5 ≥ 0.80` on the `shell-rtk-prefix` and `code-search-uses-ast-grep` cases under Haiku.
- **Deterministic canary:** running the canary twice on an unchanged config keeps tokens/tool-calls within a tolerance band (determinism check), and **deterministic `pass@1` trends flat-or-up across the measurement week** with one `history.jsonl` row per scheduled run.
- **Scored judge variance:** in `selftest.py`/calibration, a known-good transcript scores high and a known-bad one scores low across repeated samples, with per-canary score **std-dev below the effect size the owner cares about**.
- **Judge calibration:** ~15 hand-labeled transcripts in `evals/judge_calibration/`; the calibration script gates **judge-vs-human divergence ≤ 25%**, verified entirely offline with no agent runs.
- **Trajectory grading:** conformance cases with a `reference_trajectory` report `in_order_match ≥ 0.9`.

These targets are the source rows for the canary/reliability/differential entries in the [ADR-0004](0004-gain-scorecard-experiment.md) `gain` scorecard.

## References

- [Terminal-Bench 2.0 — strict Pass@1, no-judge agent benchmark](https://explainx.ai/blog/terminal-bench-2-0-ai-agent-benchmark-evaluation) — justifies a deterministic, judge-free longitudinal canary signal.
- [OpenAI — Evals guide](https://developers.openai.com/api/docs/guides/evals) — fixed-dataset, repeated-run loop methodology behind the scheduled canary.
- [SWE-bench-style test-based grading (via OpenAI evals guide)](https://developers.openai.com/api/docs/guides/evals) — apply-and-run-tests as the write-path deterministic check (R3).
- [tau-bench — pass^k reliability, arXiv:2406.12045](https://arxiv.org/abs/2406.12045) — best-of-k overstates reliability; `pass^k` is the trust metric for unattended weak models.
- [Many-shot / in-context learning synthesis, arXiv:2501.10868](https://arxiv.org/html/2501.10868v1) — exemplar/scaffold benefit is inversely related to model strength, the basis for the weak-minus-strong differential.
- [OpenAI — Graders guide](https://developers.openai.com/api/docs/guides/graders) — a graded 0-1 score is smoother than a pass/fail stamp; basis for the scored judge mode.
- [OpenTelemetry GenAI semantic conventions — metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md) — standard names for the latency/token fields the canary records.
- [Vertex AI — agent evaluation (trajectory metrics)](https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service) — exact/in-order/any-order trajectory match + precision/recall; basis for the trajectory grader.
- [CalibraEval — position-bias calibration, arXiv:2410.15393](https://arxiv.org/pdf/2410.15393) — magnitude of LLM-judge position bias; motivates reference-anchored calibration.
- [Self-Preference Bias in LLM-as-Judge, arXiv:2410.21819](https://arxiv.org/abs/2410.21819) — self-preference up to +90%; motivates cross-family judge + human calibration.
- [Anthropic — Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) — reference-anchored grading and structured rubrics.
- Read-only repo context: [`plans/05-test-coverage.md`](../05-test-coverage.md) (TEST-08/10/11/14), [`plans/02-maturity-review.md`](../02-maturity-review.md) (MAT-09/10), [`evals/PLAYBOOK.md`](../../evals/PLAYBOOK.md) ("a case is born from a real weakness you observed").

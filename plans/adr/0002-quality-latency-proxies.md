# ADR-0002: Add real-session quality and latency proxy metrics so weak-model uplift and heavy-model speed become falsifiable

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** measurement, weak-model
- **Related:** [ADR-0001](0001-real-usage-measurement-baseline.md) (the captured baseline and session reconstruction this ADR's metrics are computed on top of), [ADR-0003](0003-eval-backbone-canary.md) (the canary that supplies the *true* model-latency number this ADR cannot), [ADR-0004](0004-gain-scorecard-experiment.md) (the scorecard that aggregates these rows), [ADR-0005](0005-model-tiering-routing.md) and [ADR-0006](0006-weak-model-reasoning-uplift.md) (the content levers these proxies are the early-warning for). Implementation: [`plans/impl/02-quality-latency-proxies.md`](../impl/02-quality-latency-proxies.md). Prior corpus (read-only): `plans/01`–`plans/05`, items TEST-08, TEST-11, MAT-10.

## Context and problem statement

The repository's telemetry is, today, a **token economy** instrument and nothing more. [`telemetry/report.py`](../../telemetry/report.py) parses every assistant record's `msg.usage` block ([`report.py:73-125`](../../telemetry/report.py)) into input/output/cache buckets, and [`telemetry/gate.py`](../../telemetry/gate.py) gates a single derived number — the token-weighted cache hit rate. That instrument is excellent at what it measures, and the owner's real baseline confirms there is little left to win there: across a 40-session sample the weighted cache hit rate is already **96.3%** (range 78–99%), so cache hygiene is essentially maxed and the remaining levers are model routing and output/context volume, not cache.

The problem is that the two goals this whole program exists to serve are **quality** and **latency**, and the telemetry measures *neither*:

- **Goal 1 — make weak models (Sonnet 4.6, especially Haiku 4.5) smarter under this config.** There is no signal in the harness that distinguishes a smart Haiku session from a flailing one. "Haiku got smarter after the plan-first scaffold landed" is, with today's instrumentation, an *unfalsifiable* claim. The data needed to falsify it is present in the transcripts — `tool_result` blocks carry an `is_error` flag, user turns carry correction text, an Edit followed by a reverting Edit is observable — but `report.py` reads none of it.
- **Goal 2 — make the heavy model (Opus 4.8) faster and consume less.** Latency is named explicitly in the goals and instrumented *nowhere*. `report.py` already stores `first_ts` and `last_ts` per session ([`report.py:127-136`](../../telemetry/report.py)) but never differences them, and [`evals/lib/agent.py`](../../evals/lib/agent.py)'s `metrics()` ([`agent.py:74-95`](../../evals/lib/agent.py)) reads the stream-json transcript yet drops the `duration_ms` and `num_turns` fields the `result` event already carries. The speed half of Goal 2 has zero numbers behind it.

This ADR decides to add the **quality** and **latency** proxy signals the harness lacks, computed from the real transcripts the owner already produces (and, for true model latency, from eval runs), so that every routing change (ADR-0005) and every reasoning scaffold (ADR-0006) can be judged on whether it actually moved quality and speed — not merely tokens. It is a Wave 0 measurement change, read-only and stdlib, and pairs with ADR-0001's baseline capture and session reconstruction: this ADR defines *what* to measure, ADR-0001 defines the *unit and population* it is measured over.

The central design tension, surfaced by the critique, is **honesty under low statistical power**. A single developer produces rare events — in the verified 205-session corpus, user turns are 3496 `tool_result`-only versus only **452 text-bearing**, so corrections and reverts are scarce. A metric that overclaims significance from a handful of events is worse than no metric. This ADR therefore separates *continuous* signals (which move every session) from *rare-event rates* (which need weeks), and labels each number with exactly what it can and cannot prove.

## Decision drivers

- **Goal 1 (weak-model uplift) must become falsifiable** — at least one observable, model-segmented quality signal must exist on real Haiku/Sonnet sessions, or the entire reasoning-uplift workstream is asserted rather than measured.
- **Goal 2 (heavy-model speed) must have a number** — latency must be instrumented somewhere trustworthy, and the *true* model-latency source must be distinguished from the wall-clock-with-human-think-time number a transcript can offer.
- **The balanced scorecard rule** — a cheaper model that needs more turns, throws more tool errors, or earns more corrections is *not actually cheaper*. These proxies are the guardrail that stops Goal 2 (routing to Haiku) from silently sacrificing Goal 1 (quality). Neither KPI wins alone.
- **Honesty over impressiveness** — every metric must be labeled with its real meaning (P2-10) and its statistical reach (P2-11). A number the owner cannot trust is a liability, not an asset.
- **Zero marginal cost** — the signal must be derivable from transcripts already on disk (no extra model calls), so that *measuring* Goal 2 does not itself spend Opus tokens and work against Goal 2.

## Considered options

1. **Keep token-only telemetry; infer quality from token volume.** Treat fewer tokens / fewer turns as a proxy for "better."
2. **LLM-judge every real session for a quality score.** Run a grader model over each transcript to score quality directly.
3. **Add deterministic, transcript-derived quality and latency proxies, model-segmented, separating continuous from rare-event signals (chosen).** Extend `report.py` to parse `tool_result` errors, user-correction text, and edit-reverts; difference the stored timestamps for wall-clock; add `duration_ms`/`num_turns` to `agent.py` for true model latency in eval runs; add a `tool_error_rate` floor to `gate.py`.

## Decision outcome

**Chosen: Option 3 — deterministic, transcript-derived quality and latency proxies.**

We add four quality proxies and two latency signals, all model-segmented, all computed offline from data already on disk.

**Quality proxies (Goal 1 falsifiability).** Extend `SessionStats.add_assistant` ([`report.py:73-125`](../../telemetry/report.py)) and add user-turn parsing to emit, per session and split Haiku / Sonnet / Opus:

- **`tool_error_rate`** = count of `tool_result` blocks with `is_error == true` / total `tool_result` blocks. The critique verified the field exists in the real corpus.
- **`turns_to_completion`** = the assistant-turn count already tracked at [`report.py:95`](../../telemetry/report.py), but reported *per reconstructed session* (ADR-0001's unit, not per file) and read honestly as "assistant turns in this session," never as a free-floating difficulty measure.
- **`edit_revert_rate`** = an Edit/Write to a path followed by a *reverting* Edit to the same path within **K = 3** assistant turns. The detector is validated against ≥ 10 hand-labeled real reverts before its rate is trusted.
- **`user_correction_rate`** = fraction of *text-bearing* user turns whose text matches a correction lexicon — run **only** on the 452 text turns, **never** the 3496 tool_result-only turns, and with a **Russian** lexicon alongside English because the owner works in Russian.

**Latency signals (Goal 2).** Two edits, with an explicit honesty boundary between them:

- **Session wall-clock** — difference `last_ts − first_ts` ([`report.py:127-136`](../../telemetry/report.py)) for `session_duration_s`, and difference consecutive assistant timestamps for `p50`/`p95` per-turn gaps. This is labeled **"session wall-clock (includes human think-time)"** and is *not* presented as model latency (P2-10).
- **True model latency** — surface `duration_ms` and `num_turns` from the stream-json `result` event in `metrics()` ([`agent.py:74-95`](../../evals/lib/agent.py)), available only in eval/canary runs, where there is no human in the loop. This is the *only* number we call model latency.

**Gate (balanced guardrail).** Add a `tool_error_rate` floor to [`gate.py`](../../telemetry/gate.py) beside the existing cache floor: the gate **fails** if the tool-error rate over the last 20 reconstructed sessions exceeds **8%**. This is the deterministic, zero-LLM tripwire that catches a routing change degrading weak-model quality.

**Why this option, with evidence.** Anthropic's own multi-agent engineering writeup reports that "token usage by itself explains 80% of the variance" in agent performance for *breadth-first research*, yet warns in the same body of work that more tokens and more agents degrade *coding* tasks where context is shared — i.e. token volume is a usage signal, **not** a quality signal, and using it as one (Option 1) is exactly the trap ([Anthropic, *How we built our multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system); [Cognition, *Don't Build Multi-Agents*](https://cognition.com/blog/dont-build-multi-agents)). The four chosen proxies are the agreed agent-quality vocabulary (pass rate, revision rate, tool-error rate, intervention rate) used by practitioners precisely *because* output volume is mute on quality ([DigitalApplied, *Agent Quality Metrics 2026*](https://www.digitalapplied.com/blog/agent-quality-metrics-pass-rate-revision-rate-2026)). For latency, the OpenTelemetry GenAI semantic conventions define `gen_ai.client.operation.duration` and time-to-first-chunk as the standard surface, and Vertex attaches latency to every eval by default — establishing that latency is a first-class, expected metric, and that the trustworthy source is the per-operation duration (our `duration_ms`), not a wall-clock interval polluted by human pauses ([OpenTelemetry GenAI metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md); [Vertex AI agent evaluation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-agents-client)).

Option 2 (LLM-judge every session) is rejected on the balanced rule itself: judging every real session burns Opus/Sonnet tokens continuously, working *directly against Goal 2* during the very window we are measuring it, and introduces judge variance into a longitudinal signal that needs to be smooth. Reserved LLM grading belongs in the eval harness (ADR-0003), not on the live transcript stream.

### Consequences

**Good.**

- Goal 1 becomes falsifiable: after the reasoning scaffolds land (ADR-0006), `report.py --last 30 --json` will show whether Haiku/Sonnet `tool_error_rate` and `edit_revert_rate` actually fell versus the frozen baseline corpus.
- Goal 2 gains its first speed number, and the gate gains a quality tripwire so a routing change (ADR-0005) that trades correctness for cost is caught deterministically rather than discovered weeks later.
- Zero marginal token cost — all signals are offline transcript parsing or fields already present in eval output.

**Cost.** A modest parser extension to `report.py`, a small addition to `agent.py` and `gate.py`, the one-time effort of hand-labeling ≥ 10 reverts and a precision sample of corrections, and the discipline of maintaining the Russian/English correction lexicon.

**Risks and mitigations** (the assigned critique points, folded in as named risks):

- **Risk — "completion" / "resolved" is undefined (P0-3).** "Turns to completion" can silently conflate one hard 40-turn task with five easy 8-turn tasks in a single session, and "cost per *resolved* task" needs a resolved-count the harness cannot produce. *Mitigation:* we define completion **operationally** — a session ends at the last assistant turn with **no following user *text* turn** (tool_result-only continuations do not reset it) — and we report turns/cost *per reconstructed session bucketed by task class* (ADR-0001 / ADR-0004), never per fictitious "resolved task." The word "resolved" is dropped from this ADR's metric names.
- **Risk — edit-revert detector is unvalidated (P0-3).** An Edit re-touching a file is usually iteration, not a revert. *Mitigation:* `K = 3` is fixed and stated; the detector is validated against **≥ 10 hand-labeled real reverts** from the owner's corpus, and its rate is not trusted (not gated, not scorecarded) until precision on that label set is reported.
- **Risk — user-correction heuristic fires on the wrong records and misses Russian (P0-4).** *Mitigation:* the heuristic runs **only** on the 452 text-bearing user turns, ships an explicit **Russian** correction lexicon (`нет`, `не то`, `отмени`, `верни`, `неправильно`, `не так`, `откати`) alongside English, and its precision is **hand-validated on a labeled sample** before it informs any decision.
- **Risk — wall-clock is not model latency (P2-10).** Differencing transcript timestamps captures tool execution *plus* the human reading and typing between turns. *Mitigation:* the real-session number is labeled **"session wall-clock (includes human think-time)"** and is never used to claim a model got faster. True model-latency claims come *only* from `agent.metrics()` `duration_ms` in eval/canary runs (ADR-0003).
- **Risk — rare-event rates have low statistical power at single-developer scale (P2-11).** With ~452 text-bearing turns across the corpus, reverts and corrections are sparse; CUPED helps continuous metrics but does little for low-rate binary events. *Mitigation:* the implementation and scorecard **explicitly partition** metrics into *continuous* (turns, wall-clock, latency, tool-error — readable over days) and *rare-event* (edit-revert, user-correction — readable over **weeks**, or pooled across the canary), and each scorecard row states its detectable window so a sparse week cannot masquerade as a regression or a win.

## Pros and cons of the options

**Option 1 — token volume as a quality proxy.** *Pro:* already implemented, zero work, zero cost. *Con:* fundamentally invalid — Anthropic/Cognition show token volume does not track coding quality, so it would greenlight a routing change that is cheaper *and worse*, violating the balanced rule. It cannot falsify "Haiku got smarter."

**Option 2 — LLM-judge every real session.** *Pro:* a direct quality score, not a proxy. *Con:* burns heavy-model tokens continuously (against Goal 2 during measurement), adds judge variance to a longitudinal signal, and is non-deterministic — unsuitable as a daily gate. Judge-based grading is correct *inside* the eval harness (ADR-0003), not on the live stream.

**Option 3 — deterministic transcript proxies, continuous/rare split, honest latency labeling (chosen).** *Pro:* zero marginal cost, model-segmented, falsifiable, and honest about what each number means and how long it takes to read. *Con:* proxies are indirect (a low tool-error rate is necessary, not sufficient, for "smart"), and the rare-event rates genuinely need weeks — which we state rather than hide.

## Validation — how we confirm it worked

- **Quality proxies emit and segment.** `python3 telemetry/report.py --last 30 --json` emits `tool_error_rate`, `turns_to_completion`, `edit_revert_rate`, and `user_correction_rate` per reconstructed session, **split by model** (Haiku / Sonnet / Opus). *Target:* over the first daily-usage week after the ADR-0006 scaffolds land, Haiku/Sonnet `tool_error_rate` and `edit_revert_rate` **fall versus the frozen baseline corpus** (ADR-0001).
- **Detectors are validated before trust.** The edit-revert detector is run against **≥ 10 hand-labeled reverts** and its precision recorded; the user-correction heuristic's precision is hand-validated on a labeled sample of the 452 text turns including Russian corrections. Neither rate gates or scorecards until its precision is reported.
- **The gate trips on degradation.** `python3 telemetry/gate.py` **fails (exit 1)** when the `tool_error_rate` over the last 20 reconstructed sessions exceeds **8%**, beside the existing cache floor. Confirmed by a fixture window seeded above and below 8%.
- **Latency is instrumented and honestly labeled.** `report.py --last 20 --json` exposes `session_duration_s` and p50/p95 per-turn wall-clock keyed by model, labeled as wall-clock including think-time; `agent.metrics()` exposes `duration_ms` and `num_turns` from the `result` event. *Target (true latency, eval-only, cross-referenced from ADR-0005):* after tiering/minimal-context, median **model** turn latency on cheap-task canary runs drops ≥ 15% while heavy-task latency is unchanged.
- **Self-tests guard the pure logic.** New cases in [`evals/selftest.py`](../../evals/selftest.py) assert the operational completion boundary, the `K = 3` edit-revert detector on a synthetic Edit→revert sequence, and the correction lexicon on a Russian and an English sample — mirroring the existing `test_metric_verdict` discipline ([`selftest.py:55-63`](../../evals/selftest.py)).

## References

- [Anthropic — *How we built our multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system) — supports that token usage explains usage but not quality (and that more tokens degrade coding), justifying proxy metrics over token volume.
- [Cognition — *Don't Build Multi-Agents*](https://cognition.com/blog/dont-build-multi-agents) — corroborates that token/turn volume is not a quality signal for coding and motivates the tool-error / revert proxies.
- [DigitalApplied — *Agent Quality Metrics: Pass Rate, Revision Rate (2026)*](https://www.digitalapplied.com/blog/agent-quality-metrics-pass-rate-revision-rate-2026) — establishes the agreed quality vocabulary (tool-error, revision/revert, intervention rate) this ADR adopts.
- [OpenTelemetry — GenAI semantic-convention metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md) — defines `gen_ai.client.operation.duration` / time-to-first-chunk as the standard latency surface, supporting `duration_ms` as the trustworthy model-latency source.
- [Google Vertex AI — agent evaluation (latency by default)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-agents-client) — supports treating latency as a first-class, always-attached eval metric.

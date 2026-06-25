# Impl 02 — Quality and latency proxy metrics from real transcripts

**Implements:** [ADR-0002](../adr/0002-quality-latency-proxies.md). **Wave:** 0 (instrument before touching anything). **Depends on:** [ADR-0001 / impl 01](01-baseline-and-session-reconstruction.md) for the reconstructed-session unit, the frozen baseline corpus, and the `isSidechain` / `<synthetic>` filtering that every per-session metric here is computed over. **Pairs with:** ADR-0001 in the same telemetry phase. **Feeds:** the canary ([ADR-0003](../adr/0003-eval-backbone-canary.md)), the scorecard ([ADR-0004](../adr/0004-gain-scorecard-experiment.md)), and is the early-warning instrument for routing ([ADR-0005](../adr/0005-model-tiering-routing.md)) and reasoning scaffolds ([ADR-0006](../adr/0006-weak-model-reasoning-uplift.md)).

## Scope and deliverables

1. Extend [`telemetry/report.py`](../../telemetry/report.py) `SessionStats` to parse `tool_result` errors, user-turn correction text, and edit-reverts, and to difference the already-stored timestamps — emitting four model-segmented quality proxies and two latency signals in both `print_human` and `to_json`.
2. Extend [`evals/lib/agent.py`](../../evals/lib/agent.py) `metrics()` to surface `duration_ms` and `num_turns` from the stream-json `result` event (the only trustworthy model-latency source).
3. Add a `tool_error_rate` floor to [`telemetry/gate.py`](../../telemetry/gate.py) beside the existing cache floor.
4. Add a metric case `evals/metric/cases/tool-error-rate.json` and self-tests in [`evals/selftest.py`](../../evals/selftest.py) for the completion boundary, the edit-revert detector, and the correction lexicon.

Out of scope (owned elsewhere, referenced read-only): session reconstruction and the `<synthetic>`/sidechain filter (impl 01), CUPED task-mix normalization (impl 04), the canary suite and `duration_ms` *consumption* (impl 03). This plan **produces** `duration_ms`; impl 03 consumes it.

## File-by-file changes

### A. `telemetry/report.py` — quality proxies and wall-clock

`SessionStats.add_assistant` ([`report.py:73-125`](../../telemetry/report.py)) today reads only `msg.usage`. Tool-call names are already counted at [`report.py:84-85`](../../telemetry/report.py); we extend the same content-block loop and add a user-turn path and timestamp differencing.

**A1. Tool-error parsing.** `tool_result` blocks live on **user** records (Claude Code writes the tool result back as a user message), so add a `add_user(rec)` method and call it from `parse_file` ([`report.py:172-173`](../../telemetry/report.py)) alongside the existing `assistant` branch:

```python
# in parse_file, beside the existing assistant branch
if rec.get("type") == "user":
    st.add_user(rec)
```

```python
def add_user(self, rec: dict) -> None:
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                self.tool_results += 1
                if block.get("is_error"):
                    self.tool_errors += 1
        # user-correction: ONLY text-bearing turns (P0-4), never tool_result-only
        text = " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ).lower()
    elif isinstance(content, str):
        text = content.lower()
    else:
        text = ""
    if text.strip():
        self.user_text_turns += 1
        if _CORRECTION_RE.search(text):
            self.user_corrections += 1
```

New counters in `__init__` (beside [`report.py:63`](../../telemetry/report.py)): `tool_results`, `tool_errors`, `user_text_turns`, `user_corrections`, and an `edits` list of `(turn_index, path, op)` for revert detection.

**A2. Correction lexicon (English + Russian, P0-4).** A module-level compiled regex; word-boundaried where the language allows:

```python
_CORRECTION_TERMS = [
    # English
    r"\bno\b", r"\bundo\b", r"\brevert\b", r"that'?s wrong", r"not what",
    r"don'?t do that", r"\bredo\b", r"\bwrong\b",
    # Russian (the owner works in Russian)
    r"\bнет\b", r"не то", r"\bотмени\b", r"\bверни\b", r"\bоткати\b",
    r"неправильно", r"не так",
]
_CORRECTION_RE = re.compile("|".join(_CORRECTION_TERMS), re.IGNORECASE)
```

`user_correction_rate = user_corrections / user_text_turns` (0.0 when no text turns). **Denominator is text-bearing turns only** — never the 3496 tool_result-only turns. The rate is not trusted until its precision is hand-validated (see Build order step 6).

**A3. Edit-revert detector (K = 3, P0-3).** In the `add_assistant` content-block loop ([`report.py:83-85`](../../telemetry/report.py)), when a `tool_use` block is an `Edit`/`Write`/`MultiEdit`, append `(self.assistant_turns, _edit_path(block), block["name"])` to `self.edits`. A revert is an edit to a path whose `new_string` restores a value an earlier edit (within `K = 3` assistant turns) had changed away from — approximated structurally as: a later Edit on path `p` whose `new_string` equals an earlier Edit's `old_string` on the same `p` within K turns.

```python
K_REVERT = 3
def edit_revert_rate(self) -> float:
    edits = self.edits
    reverts = 0
    for i, (turn, path, op, old, new) in enumerate(edits):
        for j in range(i):
            pturn, ppath, pop, pold, pnew = edits[j]
            if ppath == path and turn - pturn <= K_REVERT and new == pold and old == pnew:
                reverts += 1
                break
    denom = sum(1 for e in edits if e[2] in ("Edit", "MultiEdit"))
    return reverts / denom if denom else 0.0
```

This detector is **validated against ≥ 10 hand-labeled reverts** before its rate is reported as trustworthy (Build order step 6); `K = 3` is fixed and documented in a comment.

**A4. Turns-to-completion with operational completion (P0-3).** `turns_to_completion` is the per-(reconstructed-)session `assistant_turns` already tracked at [`report.py:95`](../../telemetry/report.py), but reported per ADR-0001 session, not per file. Operational completion: the session ends at the **last assistant turn with no following user *text* turn**; tool_result-only user continuations do not extend it. Emit `assistant_turns` as-is and document the read honestly in the column legend ("assistant turns this session, not a difficulty score").

**A5. Wall-clock latency (P2-10).** `first_ts`/`last_ts` are stored but never differenced ([`report.py:127-136`](../../telemetry/report.py)). Parse ISO-8601 with `datetime.fromisoformat` (stdlib), compute `session_duration_s`, and collect per-turn gaps from consecutive assistant-record timestamps to report `p50`/`p95`:

```python
def session_duration_s(self) -> float:
    if not (self.first_ts and self.last_ts):
        return 0.0
    a = datetime.fromisoformat(self.first_ts.replace("Z", "+00:00"))
    b = datetime.fromisoformat(self.last_ts.replace("Z", "+00:00"))
    return max(0.0, (b - a).total_seconds())
```

Per-turn gaps need each assistant record's timestamp, so capture it in `add_assistant` (the `rec["timestamp"]` is already read by `add_meta`). All wall-clock keys are labeled `*_wallclock` and the JSON/legend carries the note **"includes human think-time; not model latency."**

**A6. Surface in `print_human` and `to_json`.** Add columns `tool_err%`, `turns`, `revert%`, `corr%`, `dur_s` to the human table header ([`report.py:205`](../../telemetry/report.py)) and the aggregate block, **split by model tier** (Haiku / Sonnet / Opus) in the totals section; add the same keys to the `to_json` dict ([`report.py:259-277`](../../telemetry/report.py)):

```python
"tool_error_rate": round(st.tool_errors / st.tool_results, 4) if st.tool_results else 0.0,
"turns_to_completion": st.assistant_turns,
"edit_revert_rate": round(st.edit_revert_rate(), 4),
"user_correction_rate": round(st.user_correction_rate(), 4),
"session_duration_s_wallclock": round(st.session_duration_s(), 1),
"per_turn_latency_s_wallclock": {"p50": st.turn_p50(), "p95": st.turn_p95()},
```

**A7. Alias the `--json` keys to OpenTelemetry GenAI names.** In `to_json` (gated behind a `--otel` flag to keep the default output stable), additionally emit the OpenTelemetry GenAI semantic-convention names so this home-grown telemetry lines up with standard observability tooling (Langfuse, Arize Phoenix): `gen_ai.client.operation.duration` for session/turn duration, `gen_ai.client.token.usage` carrying `token.type` = `input` / `output` / `cache_read`, `gen_ai.tool.execute.duration`, and an `error.type` tally per tool ([OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md)). This is a pure key-aliasing pass over fields A1–A6 already compute — no new measurement, so it carries no extra parsing cost.

### B. `evals/lib/agent.py` — true model latency

`metrics()` ([`agent.py:74-95`](../../evals/lib/agent.py)) parses the stream-json transcript and returns `{"tool_calls", "transcript_chars"}` but drops the fields the terminal `result` event already carries. Extend the existing loop to read the same `{"type":"result"}` event that `final_text` ([`agent.py:55`](../../evals/lib/agent.py)) already locates:

```python
duration_ms = None
num_turns = None
# ... inside the existing per-line loop ...
if obj.get("type") == "result":
    if isinstance(obj.get("duration_ms"), (int, float)):
        duration_ms = obj["duration_ms"]
    if isinstance(obj.get("num_turns"), (int, float)):
        num_turns = obj["num_turns"]
# return:
return {"tool_calls": tool_calls, "transcript_chars": len(raw),
        "duration_ms": duration_ms, "num_turns": num_turns}
```

This is the **only** model-latency source (no human in the loop in eval runs); the canary (impl 03) consumes it. `None` when absent (plain-text CLI agents) so the contract degrades cleanly.

### C. `telemetry/gate.py` — tool-error floor

`gate.py` ([`gate.py:44-64`](../../telemetry/gate.py)) gates only the cache hit rate. Add a parallel `tool_error_rate` ceiling over the same last-20 window, aggregated the same token/event-weighted way as the cache gate (sum errors / sum tool_results across reconstructed sessions, so a tiny session does not dominate):

```python
def evaluate_tool_errors(sessions, max_error_rate: float, min_calls: int) -> dict:
    total_err = sum(s.tool_errors for s in sessions)
    total_calls = sum(s.tool_results for s in sessions)
    rate = total_err / total_calls if total_calls else 0.0
    status = "skip" if total_calls < min_calls else ("fail" if rate > max_error_rate else "pass")
    return {"status": status, "tool_error_rate": round(rate, 4),
            "max_error_rate": max_error_rate, "tool_calls": total_calls}
```

New flags: `--max-tool-error-rate` (default **0.08**) and `--min-calls` (skip below). The gate fails if **either** the cache floor or the tool-error ceiling fails (`return 1 if any(... == "fail")`), preserving the existing exit-code contract ([`gate.py:104`](../../telemetry/gate.py)).

### D. `evals/metric/cases/tool-error-rate.json` — gate as a committed case

Mirror the existing `cache-hit-rate.json` schema (validated by [`cases.py:67-76`](../../evals/lib/cases.py)):

```json
{
  "id": "tool-error-rate",
  "rule": "Weak-model tool-error rate must not regress (ADR-0002 quality proxy)",
  "metric": "weighted_tool_error_rate",
  "op": "<=",
  "threshold": 0.08,
  "window_sessions": 20,
  "min_calls": 50
}
```

The metric track's `<=` op already exists in `METRIC_OPS` ([`cases.py:18`](../../evals/lib/cases.py)), so this needs no schema change — only the new `weighted_tool_error_rate` value wired into the metric runner's source (the runner reads from `gate.py`'s evaluator).

### E. `evals/selftest.py` — guard the pure logic

Add three tests beside `test_metric_verdict` ([`selftest.py:55-63`](../../evals/selftest.py)), each zero-token:

- `test_edit_revert_detector` — a synthetic `edits` list with one true Edit→revert within K=3 expects rate > 0; an iterative (non-restoring) edit pair expects 0.
- `test_correction_lexicon` — `"нет, не то"` and `"no, that's wrong"` both match `_CORRECTION_RE`; `"please continue"` and a tool_result-only turn do not.
- `test_completion_boundary` — a session whose last user record is tool_result-only ends at the prior assistant turn (the boundary does not advance on a tool_result-only continuation).

## Why each change (one cited finding + impact per change)

- **A1 tool-error parsing** — token volume does not measure quality, so a routing change can look cheaper while throwing more tool errors; the tool-error rate is the agreed deterministic quality proxy ([Anthropic multi-agent](https://www.anthropic.com/engineering/multi-agent-research-system); [DigitalApplied](https://www.digitalapplied.com/blog/agent-quality-metrics-pass-rate-revision-rate-2026)). Impact: fills the single biggest measurement gap — makes "Haiku got smarter / a routing change degraded quality" falsifiable, and feeds the 8% gate.
- **A2 correction lexicon (Russian + English)** — corrections are a primary intervention signal, but the owner's corpus is 3496 tool_result-only vs **452 text-bearing** user turns and the owner works in Russian; matching English keywords on all turns would be near-pure noise (P0-4). Impact: a precision-validated correction rate instead of a false-positive generator.
- **A3 edit-revert (K=3)** — revision/revert rate is a core agent-quality metric, but "an Edit re-touching a file" is usually iteration, not a revert (P0-3) ([DigitalApplied](https://www.digitalapplied.com/blog/agent-quality-metrics-pass-rate-revision-rate-2026)). Impact: a structurally-defined, hand-validated revert rate that disproportionately surfaces weak-model thrash, with the false-positive surface controlled by the restore-equality test.
- **A4 turns-to-completion** — turn count is a usage signal, not a difficulty score; conflating sessions corrupts it (P0-3). Impact: an honestly-scoped per-session turn count that, bucketed by task class (impl 04), shows whether scaffolds cut round-trips.
- **A5 wall-clock + B duration_ms** — latency is half of Goal 2 and instrumented nowhere, but transcript timestamps include human think-time, so only the stream-json `result` `duration_ms` is true model latency (P2-10) ([OpenTelemetry GenAI](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md); [Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-agents-client)). Impact: an honest wall-clock number for real sessions and a trustworthy model-latency number for eval/canary A/Bs.
- **C tool-error gate** — a deterministic, zero-LLM regression guard mirrors the proven cache gate and enforces the balanced rule (cheaper-but-error-prone is not cheaper). Impact: catches a routing regression in the last-20 window rather than weeks later.

## Build order (step by step)

1. **A1 + A2** — add `add_user`, the counters, and the bilingual correction lexicon; wire `parse_file`. Verify on a real `--last 5 --json` run that `tool_error_rate` and `user_correction_rate` keys appear and are in [0,1].
2. **A3** — capture `old_string`/`new_string` on Edit blocks, add `edit_revert_rate`. Run on the corpus; eyeball the flagged reverts.
3. **A4 + A5** — surface turns honestly; add `datetime` differencing and per-turn p50/p95, all `*_wallclock`-labeled.
4. **A6** — wire the new keys into `print_human` (model-segmented totals) and `to_json`.
5. **B** — extend `agent.metrics()` with `duration_ms`/`num_turns`; confirm against one real `claude --output-format stream-json` capture.
6. **Validate detectors (gate, P0-3/P0-4)** — hand-label **≥ 10 reverts** from the owner's corpus; compute the detector's precision/recall against them. Hand-label a precision sample of the 452 text turns (English + Russian). **Do not** wire either rate into the gate or scorecard until precision is recorded.
7. **C + D** — add the tool-error floor to `gate.py` and the `tool-error-rate.json` metric case.
8. **E** — add the three self-tests; run `python3 evals/selftest.py`.

## Validation commands and targets

```bash
python3 telemetry/report.py --last 30 --json   # emits the 4 proxies + wall-clock, model-segmented
python3 telemetry/gate.py --last 20             # PASS/FAIL on cache AND tool-error (<=8%)
python3 telemetry/gate.py --json                # tool_error_rate visible in the JSON
python3 evals/selftest.py                       # revert detector + lexicon + completion boundary green
python3 evals/lint.py                           # tool-error-rate.json passes metric-track schema
```

Targets (from ADR-0002 Validation): the four quality keys emit per reconstructed session, split Haiku/Sonnet/Opus; the gate fails when last-20 `tool_error_rate > 0.08`; `agent.metrics()` returns non-`None` `duration_ms`/`num_turns` on a stream-json capture; after the ADR-0006 scaffolds land, Haiku/Sonnet `tool_error_rate` and `edit_revert_rate` fall versus the frozen baseline corpus.

## Dependencies and sequencing

**Wave 0.** `depends_on`: impl 01 (reconstructed-session unit + `isSidechain`/`<synthetic>` filtering — **every** per-session metric here must be computed on the reconstructed session, or counts double per the subagent-file fan-out). Independent of the P0 BUG/PORT/GO roadmap work. Blocks: impl 03 (canary records `duration_ms`), impl 04 (scorecard aggregates these rows), and is the early-warning instrument for impl 05/06.

## Risks and mitigations

- **Completion undefined (P0-3)** — define operationally (session end = last assistant turn with no following user *text* turn); report turns/cost per task-class-bucketed session, never per "resolved task"; the word "resolved" is dropped.
- **Revert detector unvalidated (P0-3)** — `K = 3` fixed and commented; validate against ≥ 10 hand-labeled reverts before the rate gates or scorecards anything (step 6).
- **Correction heuristic mis-fires / misses Russian (P0-4)** — run only on the 452 text turns; ship the Russian lexicon; hand-validate precision before trust (step 6).
- **Wall-clock ≠ model latency (P2-10)** — all real-session latency keys are `*_wallclock` and labeled "includes human think-time"; model-latency claims come only from `duration_ms` in eval/canary runs.
- **Low statistical power (P2-11)** — partition continuous (turns, wall-clock, tool-error — days) from rare-event (edit-revert, user-correction — weeks, or pooled across the canary); each scorecard row (impl 04) states its detectable window so a sparse week cannot read as a regression.

## Effort and checklist

Effort: **M** (report.py extension) + **S** (agent.py, gate.py, metric case). Hand-labeling (step 6) is one-time and gates trust, not code.

- [ ] `add_user` + counters + bilingual `_CORRECTION_RE` in `report.py`
- [ ] edit-revert detector (`K = 3`, restore-equality test)
- [ ] `session_duration_s` + per-turn p50/p95, `*_wallclock`-labeled
- [ ] new keys in `print_human` (model-segmented) and `to_json`
- [ ] `duration_ms` + `num_turns` in `agent.metrics()`
- [ ] `tool_error_rate` floor (default 0.08) in `gate.py`
- [ ] `evals/metric/cases/tool-error-rate.json`
- [ ] three self-tests in `selftest.py`; `selftest.py` + `lint.py` green
- [ ] ≥ 10 hand-labeled reverts + correction-precision sample recorded **before** gating either rate

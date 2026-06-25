# Impl 03 — Eval backbone: differential-uplift harness, deterministic canary, pass^k, judge calibration

- **Status:** Not started
- **ADR:** [`plans/adr/0003-eval-backbone-canary.md`](../adr/0003-eval-backbone-canary.md)
- **Wave:** 1 (measurement backbone; lands after the Wave-0 telemetry of [ADR-0001](../adr/0001-real-usage-measurement-baseline.md)/[ADR-0002](../adr/0002-quality-latency-proxies.md), before the Wave-2 content of [ADR-0005](../adr/0005-model-tiering-routing.md)/[ADR-0006](../adr/0006-weak-model-reasoning-uplift.md)).

## Scope and deliverables

This plan builds the executable backbone that makes every later content change falsifiable and yields a clean, task-mix-normalized longitudinal signal. Deliverables:

1. A `canary` track in [`evals/lib/cases.py`](../../evals/lib/cases.py) and a `run_canary` runner in [`evals/run.py`](../../evals/run.py), with a deterministic-first check model and a committed `evals/canary/history.jsonl` time series.
2. A `weak_uplift_exceeds_strong` `pass_condition` and a new `evals/uplift.py` differential reporter that normalizes raw model ids to tier labels.
3. A `--k` / `pass^k` extension to `run_conformance`, with a gate and a self-test.
4. A scored 0-1 rubric mode in [`evals/lib/judge.py`](../../evals/lib/judge.py).
5. A `reference_trajectory` grader reusing the tool-call extraction in [`evals/lib/agent.py`](../../evals/lib/agent.py).
6. Reference-anchored judge calibration: a `reference` case field, `evals/judge_calibration/`, and a divergence script gating ≤ 25%.
7. New self-tests in [`evals/selftest.py`](../../evals/selftest.py) for every non-LLM verdict added.
8. A daily scheduler entry (via `mcp__scheduled-tasks__create_scheduled_task` / cron) that runs the canary on a pinned model and appends to `history.jsonl`.

**Out of scope (owned elsewhere, referenced read-only):** session reconstruction and the baseline corpus ([ADR-0001](../adr/0001-real-usage-measurement-baseline.md)); the real-session quality/latency proxies in `telemetry/` ([ADR-0002](../adr/0002-quality-latency-proxies.md)); the `gain` scorecard aggregation ([ADR-0004](../adr/0004-gain-scorecard-experiment.md)); the routing/scaffold content ([ADR-0005](../adr/0005-model-tiering-routing.md)/[ADR-0006](../adr/0006-weak-model-reasoning-uplift.md)); `harvest.py` ([ADR-0007](../adr/0007-adoption-flywheel.md)) — this plan only defines the `history.jsonl` rotation slot it will feed. We do **not** edit `plans/00-05`.

## File-by-file changes

### 1. `evals/lib/cases.py` — add the `canary` track and the differential pass_condition

Today `PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse"}` ([`cases.py:17`](../../evals/lib/cases.py)), `_track_dir` knows three tracks ([`cases.py:21-22`](../../evals/lib/cases.py)), and `validate` branches on `conformance`/`value`/`metric` ([`cases.py:36-80`](../../evals/lib/cases.py)).

- Extend the pass-condition set and add a canary directory:

```python
PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse", "weak_uplift_exceeds_strong"}
CANARY_DIR = EVALS_DIR / "canary" / "cases"

def _track_dir(track: str) -> Path:
    return {"conformance": CONFORMANCE_DIR, "value": VALUE_DIR,
            "metric": METRIC_DIR, "canary": CANARY_DIR}[track]
```

- Add a `canary` branch to `validate`. A canary case requires `id`, `prompt`, `rule`, and at least one grader: a `deterministic_check` (path to an executable returning 0/1) or a `reference_trajectory` (list) or a scored `rubric`. The deterministic check is the *primary* grader; if a case has only a `rubric` it must set `judge_mode: "scored"` with a numeric `pass_threshold`. Write-path canary cases (those whose `tags` include `"write"`) **must** carry a `deterministic_check` (apply-and-run-tests), not a rubric alone — enforce this in `validate` so R3 cannot be bypassed:

```python
elif track == "canary":
    require("prompt", str); require("rule", str)
    graders = [k for k in ("deterministic_check", "reference_trajectory", "rubric") if case.get(k)]
    if not graders:
        errors.append("canary case needs a deterministic_check, reference_trajectory, or rubric")
    if "write" in case.get("tags", []) and not case.get("deterministic_check"):
        errors.append("write-path canary case must include an apply-and-run-tests deterministic_check")
```

- The `weak_uplift_exceeds_strong` condition is validated where it is used (value cases consumed by `uplift.py`); add it to `PASS_CONDITIONS` so `validate`'s existing value-track check at [`cases.py:60-62`](../../evals/lib/cases.py) accepts it.

### 2. `evals/run.py` — `--k`/`pass^k`, `run_canary`, and the differential verdict

- **`run_conformance` → add `--k` and `pass^k`** ([`run.py:48-57`](../../evals/run.py)). Today each case runs once. Add a repeat loop and an all-pass reduction:

```python
def run_conformance(cs, k: int = 1) -> int:
    failures = 0
    for c in cs:
        passes = 0
        for _ in range(k):
            tx = agent.run_capture(AGENT_CMD, c["prompt"])
            v = judge.judge_conformance(c, tx, JUDGE_CMD)
            passes += v.get("verdict") == "PASS"
        pass_k = passes == k                      # pass^k: ALL k repeats passed
        rate = passes / k
        failures += not pass_k
        print(f"  pass^{k}={'PASS' if pass_k else 'FAIL'} (pass@1={rate:.2f})\n")
    return failures
```

  Wire `--k` (default 1, so existing single-shot behavior is unchanged) into `main`'s argparse next to `--n` ([`run.py:163`](../../evals/run.py)) and pass it to `run_conformance` at [`run.py:189`](../../evals/run.py). Add a `pass^k` gate target consumed by [ADR-0004](../adr/0004-gain-scorecard-experiment.md): `pass^5 ≥ 0.80` on the Haiku conformance set.

- **`_value_verdict` → handle the differential condition** ([`run.py:109-118`](../../evals/run.py)). The differential is computed across two result directories, not within one win tally, so `_value_verdict` stays as-is for the two within-model conditions and **delegates** the new one to `uplift.py`. Keep `_value_verdict` pure: when `pass_condition == "weak_uplift_exceeds_strong"`, `run_value` records the per-model margin into the result jsonl (already written at [`run.py:98-105`](../../evals/run.py)) and the PASS/FAIL is decided later by `uplift.py` reading both directories. Add a `margin` field to the recorded run so `uplift.py` has a number to difference:

```python
margin = (wins["treatment"] - wins["control"]) / (sum(wins.values()) or 1)
# ...add "margin": margin to the json.dumps payload at run.py:98-105
```

- **Add `run_canary`.** A deterministic-first runner that records a `history.jsonl` row per case per run:

```python
def run_canary(cs, model, history_path) -> int:
    failures = 0
    for c in cs:
        tx = agent.run_capture(AGENT_CMD, c["prompt"], model=model)
        m = agent.metrics(tx)                     # tool_calls, transcript_chars, latency_ms
        det = _run_deterministic_check(c, tx)     # None | 0 | 1
        traj = agent.trajectory_score(c, tx) if c.get("reference_trajectory") else None
        score = judge.judge_scored(c, tx, JUDGE_CMD) if c.get("rubric") else None
        passed = det if det is not None else (score is not None and score >= c.get("pass_threshold", 0.5))
        failures += not passed
        _append_jsonl(history_path, {
            "date": date.today().isoformat(), "id": c["id"], "model": model,
            "pass_at_1": int(bool(passed)), "deterministic": det,
            "trajectory": traj, "score": score,
            "tool_calls": m["tool_calls"], "latency_ms": m.get("latency_ms"),
            "set": c.get("set", "active"),       # active | holdout, for R1 rotation
        })
    return failures
```

  `_run_deterministic_check` runs the case's `deterministic_check` script in the scratch repo and returns its exit-code-derived 0/1. Register `canary` in `main`'s `--track` choices ([`run.py:161`](../../evals/run.py)) and dispatch to `run_canary` in the execution block ([`run.py:187-193`](../../evals/run.py)).

### 3. `evals/uplift.py` — new differential-uplift reporter

A thin, stdlib-only reporter (no agent, no judge) that closes the delta-of-deltas gap and normalizes raw model ids to tier labels (R4):

```python
TIER = {                                   # raw --model string -> tier label
    "claude-opus-4-8": "strong",
    "claude-sonnet-4-6": "mid",
    "claude-haiku-4-5-20251001": "weak",
}
SYNTHETIC = {"<synthetic>"}

def differential(results_dir, case_id, weak="weak", strong="strong", floor=0.20):
    weak_margin  = _latest_margin(results_dir, weak, case_id)    # from run_value's "margin"
    strong_margin = _latest_margin(results_dir, strong, case_id)
    delta = weak_margin - strong_margin
    return {"case": case_id, "weak_margin": weak_margin,
            "strong_margin": strong_margin, "delta": delta,
            "verdict": "PASS" if delta >= floor else "FAIL"}
```

`_latest_margin` resolves a tier label to whichever `results/<raw-model-id>/` directory maps to it via `TIER`, filters `<synthetic>`, and reads the most recent `margin` for the case id. A CLI prints a one-line-per-case table and exits non-zero if any required case is below floor.

### 4. `evals/lib/judge.py` — scored 0-1 rubric mode

Beside `judge_conformance`/`judge_pairwise` and the `FLIP_THRESHOLD` logic ([`judge.py:16`, `:96-119`](../../evals/lib/judge.py)), add a scored grader that returns a float in [0,1]:

```python
_SCORED_TEMPLATE = """Score this transcript against the rubric from 0.0 to 1.0.
RUBRIC:\n{rubric}\nTRANSCRIPT:\n{transcript}
Reply with one JSON object: {{"score": <0.0-1.0>, "reason": "one sentence"}}"""

def judge_scored(case, transcript, judge_cmd) -> float:
    raw = agent.final_text(agent.run_capture(judge_cmd, _SCORED_TEMPLATE.format(
        rubric="\n".join(f"- {r}" for r in case.get("rubric", [])),
        transcript=agent.clip(transcript))))
    parsed = _parse_json_object(raw) or {}
    return max(0.0, min(1.0, float(parsed.get("score", 0.0))))
```

This reuses `_parse_json_object`, `agent.clip`, and `agent.final_text` unchanged.

### 5. `evals/lib/agent.py` — trajectory match + latency

`metrics()` ([`agent.py:74-95`](../../evals/lib/agent.py)) already walks `tool_use` blocks. Two additions, both reusing that parse:

- Capture the ordered tool-name list and `duration_ms`/`num_turns` from the stream-json `result` event (the digest's latency proposal needs `duration_ms` here; it is dropped today). Add `latency_ms` and `tool_sequence` to the returned dict.
- Add a pure-logic `trajectory_score(case, raw)` that compares the captured `tool_sequence` against `case["reference_trajectory"]`:

```python
def trajectory_score(case, raw) -> dict:
    got = metrics(raw)["tool_sequence"]; ref = case["reference_trajectory"]
    in_order = _longest_in_order(got, ref) / max(len(ref), 1)
    precision = len(set(got) & set(ref)) / max(len(got), 1)
    recall    = len(set(got) & set(ref)) / max(len(ref), 1)
    return {"in_order_match": in_order, "precision": precision, "recall": recall}
```

`_longest_in_order` is the length of the longest subsequence of `got` that matches `ref` in order — deterministic, no LLM.

### 6. `evals/judge_calibration/` + a divergence script

- New `evals/judge_calibration/` with ~15 hand-labeled transcripts (`{transcript, human_label}` per file) drawn from real failures and known-good runs.
- A `reference` (gold-answer) field added to 2-3 value/conformance cases where the answer is objectively checkable (e.g. the `ast-grep` call-site list in `ast-grep-structural-precision`), fed into the judge prompt.
- `evals/calibrate_judge.py`: replays the judge over the labeled set and reports `divergence = disagreements / total`, exiting non-zero if `> 0.25`. Offline, no agent runs.

### 7. `evals/selftest.py` — self-tests for every new non-LLM verdict

Add to the existing pure-logic suite ([`selftest.py:44-63`](../../evals/selftest.py)):

- `test_pass_k_reducer` — k repeats with one failure ⇒ `pass^k` FAIL, `pass@1 = (k-1)/k`; all pass ⇒ PASS.
- `test_differential_verdict` — `weak_margin − strong_margin ≥ floor` ⇒ PASS; equal margins ⇒ FAIL (mirrors `test_value_verdict_thresholds`).
- `test_trajectory_score` — exact match ⇒ `in_order_match == 1.0`; reversed ⇒ low; missing-tool ⇒ recall < 1.
- `test_scored_threshold` — score ≥ `pass_threshold` ⇒ pass; below ⇒ fail (stub the judge call, as `test_pairwise_*` stub `_judge_once` at [`selftest.py:30`, `:38`](../../evals/selftest.py)).

### 8. `evals/canary/` cases + scheduler

- `evals/canary/cases/` with 5-8 frozen multi-tool cases reusing the TEST-08 "works together" prompts (e.g. the `Repository.Save` signature-change task from [`plans/05-test-coverage.md`:313-318](../05-test-coverage.md)), each carrying a `deterministic_check` (every Bash `rtk`-prefixed; exact `ast-grep` call-site set; an edit makes a fixture test pass) and a `set: active|holdout` field for R1 rotation.
- `evals/canary/history.jsonl` committed, one row per case per scheduled run.
- A scheduler entry via `mcp__scheduled-tasks__create_scheduled_task` (or a cron line) running `evals/run.py --track canary --model claude-haiku-4-5-20251001 --confirm` daily and appending to `history.jsonl`.

## Why each change (one cited finding + impact per change)

- **Deterministic canary track:** Terminal-Bench grades strict Pass@1 with no judge and SWE-bench Verified grades by running tests, to remove judge variance from the trend ([Terminal-Bench 2.0](https://explainx.ai/blog/terminal-bench-2-0-ai-agent-benchmark-evaluation); [OpenAI evals](https://developers.openai.com/api/docs/guides/evals)). Impact: a zero-judge-token, zero-variance longitudinal signal the noisy real-session proxies can be read against.
- **`weak_uplift_exceeds_strong` + `uplift.py`:** exemplar/scaffold benefit is inversely related to model strength ([arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)). Impact: every uplift claim in [ADR-0006](../adr/0006-weak-model-reasoning-uplift.md) becomes PASS-only when `delta ≥ 0.20`, instead of asserted in TEST-10 prose.
- **`pass^k`:** best-of-k overstates reliability — gpt-4o `pass^8 < 25%` despite ~50% single-trial ([tau-bench, arXiv:2406.12045](https://arxiv.org/abs/2406.12045)). Impact: catches a change that lifts Haiku's mean but makes it erratic, which a mean gate misses.
- **Trajectory grader:** "it's not enough to check outputs; understand the path" ([Vertex agent eval](https://cloud.google.com/blog/products/ai-machine-learning/introducing-agent-evaluation-in-vertex-ai-gen-ai-evaluation-service)). Impact: deterministically surfaces tool-misuse (grep instead of `ast-grep`, skipped `rtk`) a final-answer judge hides.
- **Scored judge mode:** a graded score "produce[s] a smooth score, not a pass/fail stamp" ([OpenAI graders](https://developers.openai.com/api/docs/guides/graders)). Impact: detects small canary moves a binary flips noisily on.
- **Judge calibration:** position bias up to 75%, self-preference −38% to +90% ([CalibraEval, arXiv:2410.15393](https://arxiv.org/pdf/2410.15393); [Self-Preference Bias, arXiv:2410.21819](https://arxiv.org/abs/2410.21819)). Impact: the spot-check A/Bs we spend Opus tokens on become trustworthy; gate divergence ≤ 25%.

## Build order (step by step)

1. **`cases.py`** — add the `canary` track, `CANARY_DIR`, `weak_uplift_exceeds_strong`, and the write-path deterministic-check rule. Lint passes with zero canary cases yet.
2. **`agent.py`** — add `latency_ms`/`tool_sequence` to `metrics()` and `trajectory_score()`. Self-testable without an agent.
3. **`selftest.py`** — add `test_trajectory_score` (no agent needed); run `python evals/selftest.py`.
4. **`run.py`** — add `--k`/`pass^k` to `run_conformance`; add `test_pass_k_reducer` to `selftest.py`. Default `k=1` keeps existing behavior.
5. **`uplift.py`** — write the differential reporter + `TIER` map + `<synthetic>` filter; add `margin` to `run_value`'s recorded payload; add `test_differential_verdict`.
6. **`judge.py`** — add `judge_scored`; add `test_scored_threshold` (stubbed judge).
7. **`run_canary`** — wire deterministic check + trajectory + scored grader into `history.jsonl`; register the `canary` track in `main`.
8. **`evals/canary/cases/`** — author 5-8 cases from TEST-08 prompts with deterministic checks and `set` fields; commit an empty `history.jsonl`.
9. **`judge_calibration/` + `calibrate_judge.py`** — author ~15 labeled transcripts; add `reference` to 2-3 cases.
10. **Scheduler** — register the daily canary run via `create_scheduled_task`/cron.

## Validation commands and targets

```bash
# Pure-logic backbone (no tokens) — must pass before anything LLM-driven.
rtk python evals/selftest.py            # all new verdict/trajectory/pass^k tests green
rtk python evals/lint.py                # canary cases pass schema validation

# Reliability under the weak model.
rtk python evals/run.py --track conformance --k 5 \
  --model claude-haiku-4-5-20251001 --confirm
# TARGET: pass^5 >= 0.80 on shell-rtk-prefix and code-search-uses-ast-grep.

# Differential uplift (after the plan-first scaffold value case exists).
rtk python evals/run.py --track value --filter plan-first \
  --model claude-haiku-4-5-20251001 --confirm
rtk python evals/run.py --track value --filter plan-first \
  --model claude-opus-4-8 --confirm
rtk python evals/uplift.py --case plan-first --floor 0.20
# TARGET: delta = weak_margin - strong_margin >= 0.20, flip_rate < 0.10.

# Deterministic canary determinism + trend.
rtk python evals/run.py --track canary --model claude-haiku-4-5-20251001 --confirm
# TARGET: tokens/tool-calls stable run-to-run on unchanged config;
#         deterministic pass@1 flat-or-up across the week in history.jsonl.

# Judge calibration (offline, no agent).
rtk python evals/calibrate_judge.py
# TARGET: judge-vs-human divergence <= 0.25.
```

Summary targets (source rows for the [ADR-0004](../adr/0004-gain-scorecard-experiment.md) scorecard): weak-minus-strong differential ≥ 0.20; deterministic canary pass@1 flat-or-up across the week; pass^5 ≥ 0.8 on the rtk-prefix and ast-grep conformance cases under Haiku; trajectory `in_order_match ≥ 0.9`; judge-vs-human divergence ≤ 25%.

## Dependencies and sequencing

- **Wave placement:** Wave 1 (the measurement backbone). Lands after Wave-0 telemetry ([ADR-0001](../adr/0001-real-usage-measurement-baseline.md)/[ADR-0002](../adr/0002-quality-latency-proxies.md)) so `agent.metrics()` already exposes `duration_ms`, and **before** the Wave-2 content of [ADR-0005](../adr/0005-model-tiering-routing.md)/[ADR-0006](../adr/0006-weak-model-reasoning-uplift.md), which it makes falsifiable.
- **depends_on:** the `agent.metrics()` latency/`num_turns` addition (shared with ADR-0002); the existing `value` track and `selftest.py` verdict tests; the TEST-08 prompts (read-only). Independent of the Go rewrite (GO-01..17) and of the P0 hook-hardening (BUG-01..23).
- **Feeds:** [ADR-0004](../adr/0004-gain-scorecard-experiment.md) (scorecard rows), [ADR-0005](../adr/0005-model-tiering-routing.md) (canary as the blocking routing gate, R-routing below), [ADR-0006](../adr/0006-weak-model-reasoning-uplift.md) (the differential harness every scaffold is graded by), [ADR-0007](../adr/0007-adoption-flywheel.md) (`harvest.py` output rotates into the canary `holdout` set).

## Risks and mitigations

- **R1 — Canary Goodhart (critique P1-6).** Mitigate with the `active`/`holdout` `set` field, harvest-fed rotation from [ADR-0007](../adr/0007-adoption-flywheel.md), and the hard rule that the canary is never the *sole* acceptance signal — a change must also hold on the joint scorecard.
- **R2 — Eval meta-cost vs Goal 2 (critique P2-9).** Eval-token budget: **deterministic + trajectory graders are the daily primary signal (zero LLM tokens)**; LLM-judge differential A/Bs run **weekly/periodically**, never daily; the canary pins the cheap model (`claude-haiku-4-5-20251001`) for the scheduled run. Cap scored-judge use to canary cases lacking a deterministic check.
- **R3 — Write-path judged-only (critique P2-12).** `validate` enforces that any `write`-tagged canary case carries an apply-and-run-tests `deterministic_check`; the pairwise judge is advisory, the test is dispositive.
- **R4 — `results/<model>/` raw-id mismatch (minor).** `uplift.py`'s `TIER` map normalizes raw ids to tier labels and filters `<synthetic>` before matching case ids.
- **R5 — `pass^k` is real new code (minor).** Its all-pass reducer has a dedicated `test_pass_k_reducer` in `selftest.py`.
- **R6 — cache-hit regression from prefix edits (critique P2-13, cross-cutting).** This plan adds no always-on prefix bytes, but any canary case that edits `AGENTS.md` content must run `telemetry/gate.py` before/after and treat a cache-hit drop below 0.80 as a blocking regression.

## Effort and checklist

**Effort:** M (the differential reporter, canary runner, and scored/trajectory graders are each small; `pass^k` is S-plus because conformance ran once before; calibration set authoring is the main manual cost).

- [ ] `cases.py`: `canary` track + `weak_uplift_exceeds_strong` + write-path rule
- [ ] `agent.py`: `latency_ms` + `tool_sequence` + `trajectory_score`
- [ ] `run.py`: `--k`/`pass^k` in `run_conformance`; `margin` in `run_value`; `run_canary`; `canary` registered in `main`
- [ ] `uplift.py`: differential reporter + `TIER` map + `<synthetic>` filter
- [ ] `judge.py`: `judge_scored` 0-1 mode
- [ ] `selftest.py`: `test_pass_k_reducer`, `test_differential_verdict`, `test_trajectory_score`, `test_scored_threshold`
- [ ] `evals/canary/cases/` (5-8 TEST-08-derived cases) + committed `history.jsonl` + `active`/`holdout` split
- [ ] `evals/judge_calibration/` (~15 labeled transcripts) + `calibrate_judge.py` + `reference` on 2-3 cases
- [ ] scheduler entry (`create_scheduled_task`/cron) for the daily canary run
- [ ] `evals/selftest.py` and `evals/lint.py` green; all targets in "Validation commands and targets" met

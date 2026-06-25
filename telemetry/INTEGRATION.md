# Integrating the hit-rate gate into the evals framework

This is a **spec for coordination**, not applied code. The eval framework under
`evals/` is owned by the value-evals work; this document describes how the
standalone `telemetry/gate.py` could become a first-class `metric` track there,
so whoever owns `evals/` can apply it without guesswork.

## The one hard constraint: metric checks are local-only

The existing CI (`.github/workflows/ci.yml` → `bin/ci-check.sh`) runs on GitHub
Actions and is deliberately **zero-token**: `evals/lint.py`, `evals/selftest.py`,
and a dry-run parse. A cache-hit-rate metric is also zero-token, but it reads
`~/.claude/projects/**` transcripts, which **do not exist on the CI runner**.

So a `metric` track must run **locally** (manual, or a local pre-push hook),
never in GitHub Actions. Do not add it to the CI job. It can live in the same
`run.py` for ergonomics, but its invocation path is local-only.

## Shape of the framework today (for reference)

- Tracks are discovered by directory: `evals/<track>/cases/*.json`
  (`evals/lib/cases.py` → `load(track)`).
- `evals/run.py` routes per track: `run_conformance()` (LLM judge, PASS/FAIL),
  `run_value()` (pairwise A/B with ablation). Exit 1 if any case fails.
- `evals/lib/cases.py:validate(case, track)` returns a list of schema errors.
- `evals/lib/judge.py` holds the judges. All current judging is LLM-based.

There is no precedent for a numeric/threshold case — this adds the first one.

## Proposed `metric` track (Option B)

A metric case asserts a number from local telemetry against a threshold. No LLM.

1. **Cases dir:** `evals/metric/cases/*.json`. Example
   `evals/metric/cases/cache-hit-rate.json`:
   ```json
   {
     "id": "cache-hit-rate",
     "rule": "Prompt-cache reuse must not regress (prompt-caching-playbook)",
     "metric": "weighted_cache_hit_rate",
     "threshold": 0.80,
     "op": ">=",
     "window_sessions": 20,
     "min_tokens": 200000
   }
   ```

2. **Schema** — add a branch to `evals/lib/cases.py:validate()`:
   ```python
   elif track == "metric":
       require("id", str); require("rule", str)
       require("metric", str); require("op", str)
       require("threshold", (int, float))
       # window_sessions / min_tokens optional, with defaults
   ```

3. **Judge** — add `judge_metric(case, value)` to `evals/lib/judge.py`:
   ```python
   _OPS = {">=": lambda v, t: v >= t, "<=": lambda v, t: v <= t,
           ">": lambda v, t: v > t,  "<": lambda v, t: v < t}

   def judge_metric(case, value):
       ok = _OPS[case["op"]](value, case["threshold"])
       return {"verdict": "PASS" if ok else "FAIL",
               "reason": f"{case['metric']}={value:.4f} {case['op']} {case['threshold']}"}
   ```

4. **Metric source** — reuse `telemetry/gate.py:evaluate()` rather than
   reimplementing the aggregation. It already returns
   `weighted_hit_rate`, handles the `min_tokens` skip, and is calibrated. The
   runner computes the value via `telemetry.report.collect()` +
   `gate.evaluate()` and feeds it to `judge_metric`. Honor the `skip` status as
   a non-failure (insufficient data), matching `gate.py`.

5. **Runner** — add `run_metric(cases)` to `evals/run.py` and a `metric` choice
   to the `--track` argparse. Guard it so `--track all` in **CI** does not pull
   in metric cases (no transcripts there); only an explicit local
   `--track metric` runs them.

6. **Coverage lint** — `evals/lint.py` enforces a case per skill. If the metric
   track is meant to cover `prompt-caching-playbook`, decide whether that skill's
   coverage is satisfied by a metric case or should remain a conformance case;
   adjust `lint.py` accordingly so coverage accounting stays correct.

## Until then

`python3 telemetry/gate.py` is the working, standalone equivalent. The eval
integration is an ergonomics/consolidation step, not a prerequisite for using it.

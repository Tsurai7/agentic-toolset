# Impl-04: The `agentic-cfg gain` balanced scorecard and longitudinal experiment

**Status:** Proposed (not started)
**ADR:** [ADR-0004](../adr/0004-gain-scorecard-experiment.md)
**Wave:** 3 (the roll-up; closes the loop after the instruments exist)

This plan is the executable *how* for ADR-0004. It composes the scattered
telemetry/eval instruments into one command, `agentic-cfg gain`, that emits a
committed `SCORECARD.md` the owner reads in under a minute, and a longitudinal
before/after experiment that makes a low-n personal comparison attributable.

## Scope and deliverables

1. **`telemetry/scorecard.py`** (new, stdlib-only) — aggregates the nine
   `synthesis.scorecard` rows from the live instruments into one table + `--json`,
   computes the balanced (correctness-vs-tokens) verdict, and writes
   `SCORECARD.md`.
2. **`telemetry/experiment.py`** (new, stdlib-only) — takes a cutover date, buckets
   reconstructed sessions by task class, and reports per-class + CUPED-adjusted
   deltas with confidence intervals for the continuous KPIs, plus pooled
   rare-event rates with a detectability label.
3. **`bin/agentic-cfg`** (new shell dispatcher) — a thin `case`-dispatch wrapper
   with a `gain` subcommand, designed to fold into Go `agentic gain` (GO-15/GO-16).
4. **`SCORECARD.md`** (new committed artifact) — regenerated wholesale by the
   command; every cell generated, header records the command + cutover + window.
5. **A weekly review cadence** documented in `telemetry/README.md`.
6. **Selftests** in `telemetry/scorecard_selftest.py` for the balanced-rule logic
   and the CUPED math (no transcripts required).

Out of scope (owned elsewhere, referenced read-only): session reconstruction and
unit correction (ADR-0001 / `plans/impl/01`), the quality/latency proxies and OTel
names (ADR-0002 / `plans/impl/02`), the canary + `evals/uplift.py` differential
harness (ADR-0003 / `plans/impl/03`), the routing Opus-share KPI (ADR-0005), and
`telemetry/adoption.py` (ADR-0007). This plan only *reads* their outputs.

## File-by-file changes

### `bin/agentic-cfg` (new)

A POSIX-shell dispatcher mirroring the existing wrapper pattern in
[`bin/ci-check.sh:77-85`](../../bin/ci-check.sh), which already shells from the
repo into `python3 evals/{lint,selftest,run}.py`. It resolves the repo root the
same way [`bin/install.sh:5`](../../bin/install.sh) does
(`AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`) and dispatches:

```sh
#!/usr/bin/env bash
set -euo pipefail
AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cmd="${1:-help}"; shift || true
case "$cmd" in
  gain)  exec python3 "$AGENTIC_ROOT/telemetry/scorecard.py" "$@" ;;
  help|-h|--help) echo "usage: agentic-cfg gain [--last N] [--cutover YYYY-MM-DD] [--json|--write]"; ;;
  *) echo "unknown subcommand: $cmd" >&2; exit 2 ;;
esac
```

`gain` is the only subcommand now; the `case` shape exists so the future Go binary
adds `agentic gain` as one more dispatch arm without a contract change
([`plans/01-go-rewrite.md:181-184,195-197`](../01-go-rewrite.md), GO-15/GO-16).

### `telemetry/scorecard.py` (new)

The aggregator. It imports `collect` from `report.py` the same in-directory way
`gate.py` does ([`telemetry/gate.py:39-41`](../../telemetry/gate.py)), and consumes
the **reconstructed-session** view from ADR-0001 — never raw `**/*.jsonl` files —
because `report.collect()` today takes the N most-recent *files*
([`telemetry/report.py:179-189`](../../telemetry/report.py)) and a fanned-out task
is many files (critique P0-2). Public surface:

```python
ROWS = [
  Row(key="opus_token_share", goal="Goal 2 — Opus consumption / rate-limit headroom",
      source="report.py --by-model (main-thread, sidechain+<synthetic> excluded)",
      target=0.60, direction="<=", kind="continuous", quality_guard=False),
  Row(key="api_equiv_cost_proxy", goal="Goal 2 (SECONDARY — API-equivalent, NOT the bill)",
      source="report.py est_cost_usd (API list price; report.py:35 warns 'not invoices')",
      target=None, direction="info", kind="continuous", secondary=True),
  Row(key="turn_latency_p50_p95", goal="Goal 2 — latency", ... kind="continuous"),
  Row(key="weighted_cache_hit", goal="Goal 2 — cost & first-token latency",
      source="gate.py weighted_hit_rate", target=0.85, direction=">=", kind="continuous"),
  Row(key="tool_error_rate", goal="Goal 1 (+ Goal 2 guardrail)", ... kind="rare", quality_guard=True),
  Row(key="edit_revert_correction_rate", goal="Goal 1", ... kind="rare", quality_guard=True),
  Row(key="adoption_rtk_astgrep", goal="Both — behaviors actually fire",
      source="adoption.py", ... kind="continuous"),
  Row(key="weak_differential_uplift", goal="Goal 1 — helps Haiku > Opus",
      source="evals/uplift.py", target=0.20, direction=">=", kind="continuous", quality_guard=True),
  Row(key="canary_pass1_pass5", goal="Both — longitudinal quality/reliability",
      source="evals/canary/history.jsonl + run.py --k 5", ... kind="continuous", quality_guard=True),
]

def build(window, experiment) -> dict:        # value+status per row, from live sources
def balanced_verdict(rows) -> str:            # ACCEPTED | NOT_ACCEPTED | UNDERPOWERED
def render_md(scorecard) -> str               # the committed SCORECARD.md body
def to_json(scorecard) -> dict
```

The **primary cost row is `opus_token_share`** — main-thread Opus input tokens /
main-thread total input, with `isSidechain` and `model == "<synthetic>"` records
excluded (critique P0-1, minor-notes "`<synthetic>` 53"). The dollar `$est` is the
separate `api_equiv_cost_proxy` row, rendered with the literal label "API-equivalent
resource proxy — NOT the owner's bill (flat Max subscription)". `report.py` already
warns its `$est` is "for relative comparison, not invoices"
([`telemetry/report.py:19-21`](../../telemetry/report.py)); the scorecard carries
that warning into the table so the secondary row is never read as a charge.

`balanced_verdict` is the correctness-vs-tokens gate: the overall verdict is
`NOT_ACCEPTED` if any `quality_guard=True` row regressed versus baseline, **even
when** `opus_token_share` met its target. A cost win that costs quality is red.
Rows whose CI straddles zero (rare events on too small a window) render
`UNDERPOWERED` (gray), and the overall verdict is `UNDERPOWERED` rather than a
false green when a guard row is undecidable.

Each scorecard cell carries `(value, baseline, target, status, source, goal)`. A
row whose source script is unavailable renders gray "not yet measurable", never
green — so a missing instrument cannot inflate the verdict.

### `telemetry/experiment.py` (new)

The longitudinal layer. Public surface:

```python
TASK_CLASSES = ("single_file_fix", "multi_file_refactor", "codebase_qa", "pr_creation")

def classify(session) -> str:
    # dominant tool mix (session.tools Counter, report.py:84-85),
    # git_branch (report.py:130), cwd (report.py:129) → one TASK_CLASS.

def split(sessions, cutover_date) -> (pre, post)       # by session first_ts (report.py:131-135)

def cuped_delta(pre_vals, post_vals, covariate) -> Delta:
    # theta = cov(post, covariate) / var(covariate); adjusted = post - theta*(covariate - mean(covariate))
    # return (raw_delta, cuped_delta, ci_low, ci_high)  — covariate = this class's pre-period mean

def rare_event_delta(pre_rate, post_rate, n_pre, n_post) -> Delta:
    # Wald/Wilson interval on the rate difference; NO CUPED; flag detectable=False
    # when the interval straddles 0 → "needs weeks", surfaced to the scorecard as UNDERPOWERED.

def report(sessions, cutover_date) -> dict             # per-class + CUPED-adjusted continuous, pooled rare
```

`classify` reuses the task-class clustering ADR-0005 already defines for the
routing telemetry (dominant tool mix / git branch / cwd), so the experiment and the
routing KPI bucket sessions identically. `cuped_delta` uses each class's recorded
pre-period mean as the covariate, exactly as the digest specifies
(`/tmp/research_digest.json`, lines 51-58).

The hard separation (critique P2-11): **continuous** metrics (tokens, latency,
Opus-share, `$est`) go through `cuped_delta`; **rare-event** rates (reverts,
corrections, tool errors) go through `rare_event_delta` with **no CUPED** and an
honest detectability flag. `experiment.py` labels which KPIs are not detectable in
a multi-day window and need weeks, and the scorecard renders those gray. This is
why ADR-0004 makes CUPED a *hard dependency* of the bucketed cost/turns rows (P0-3),
not an optional "after."

### `SCORECARD.md` (new, generated)

Written by `scorecard.py --write` (the `agentic-cfg gain --write` path). Header
records the generating command, the cutover date, and the session window so the
artifact is reproducible. Body is the nine-row table —
`metric | goal | value | baseline | target | status | source` — followed by the
one-line balanced verdict (`ACCEPTED` / `NOT ACCEPTED` / `UNDERPOWERED`) and the
keep/iterate decision. Regenerating on another day changes only value/target/status
cells, so `git diff` is a sub-minute read.

### `telemetry/scorecard_selftest.py` (new)

Stdlib selftest, no transcripts, mirroring [`evals/selftest.py`](../../evals/selftest.py).
Asserts: (a) `balanced_verdict` returns `NOT_ACCEPTED` for a window where
`opus_token_share` meets target but a `quality_guard` row regressed; (b)
`cuped_delta` reduces the CI width versus the raw delta on a synthetic series with a
correlated covariate; (c) `rare_event_delta` flags `detectable=False` when the
interval straddles zero. Wired into `bin/ci-check.sh` next to the existing
`evals/selftest.py` line ([`bin/ci-check.sh:81`](../../bin/ci-check.sh)).

### `telemetry/README.md` (edit)

Add a short "Weekly review (`agentic-cfg gain`)" section: the exact command, the
keep / iterate / revert decision rule, and the cadence ("daily glance at the Opus
share and cache gate; weekly full scorecard review"), matching the per-row
`cadence` column of `synthesis.scorecard`.

## Why each change (one cited finding + impact per change)

- **One `agentic-cfg gain` command + `SCORECARD.md`** — the digest's single-KPI
  scorecard proposal: "Composes the scattered instruments into the goal-aligned
  dashboard the plans never build ... read one artifact in under a minute to decide
  keep/iterate" (`/tmp/research_digest.json`, lines 65-72). Impact: turns five
  separate script invocations into one sub-minute review.
- **Balanced verdict in `scorecard.py`** — CursorBench scores on a
  correctness-vs-token trade-off, not one axis
  ([CursorBench](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)).
  Impact: a Goal-2 token win that regresses a Goal-1 quality proxy renders red and
  is not accepted — the decision rule from ADR-0004 is enforced, not assumed.
- **Primary cost row = main-thread Opus token-share; `$est` secondary** —
  `report.py` itself labels `$est` "for relative comparison, not invoices"
  ([`telemetry/report.py:19-21,35`](../../telemetry/report.py)), and the owner is
  on a flat Max subscription governed by rate limits, not per-token billing.
  Impact: the scorecard tracks rate-limit headroom (the real constraint), not a
  fictional bill.
- **`experiment.py` CUPED + task-class buckets** — CUPED cuts required sample size
  ~30-50% ([Optimizely](https://www.optimizely.com/optimization-glossary/what-is-cuped);
  [arXiv:2510.03468](https://arxiv.org/abs/2510.03468)), and task-mix normalization
  stops a hard week reading as a regression (`/tmp/research_digest.json`, lines
  51-58). Impact: a real >=15% change is detectable in days, within-class, with CIs.
- **Rare-event separation + detectability labels** — CUPED does little for low-rate
  binary events (critique P2-11); with ~450 text-bearing turns the quality proxies
  are underpowered over days. Impact: underpowered rows render gray with a "needs
  weeks" annotation, so the owner does not over-read noise as signal.
- **Reconstructed-session input only** — subagent transcripts are separate files and
  `--last N` mis-counts a fanned-out task (critique P0-2); the real mix is Opus
  5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 with 28% sidechain (P0-1).
  Impact: every per-session row is computed on the right unit over the right
  population, or it does not render.
- **Shell dispatcher folding into Go** — the Go rewrite already plans
  `agentic ci-check` as a thin wrapper over the Python evals
  ([`plans/01-go-rewrite.md:195-197`](../01-go-rewrite.md), GO-15/GO-16). Impact:
  `agentic gain` is a one-line dispatch addition later; no rewrite of the scorecard.

## Build order (step by step)

1. **`bin/agentic-cfg` dispatcher** with the `gain` arm shelling to a stub
   `scorecard.py` (`--help` only). Verify `agentic-cfg gain --help` runs.
2. **`telemetry/scorecard.py` skeleton**: `ROWS`, `build`, `to_json`, reading the
   reconstructed-session view from ADR-0001 and the existing `gate.py`
   `weighted_hit_rate`. Land `--json` first (machine-checkable), then `render_md`.
3. **`balanced_verdict`** + `telemetry/scorecard_selftest.py` for the
   correctness-vs-tokens rule. Gate on the selftest before wiring real sources.
4. **`telemetry/experiment.py`**: `classify`, `split`, `cuped_delta`,
   `rare_event_delta`, `report`; extend `scorecard_selftest.py` with the CUPED
   CI-narrowing and rare-event detectability assertions.
5. **Wire live sources** into `scorecard.py build`: `report.py --by-model`
   (Opus-share, latency, `$est`), `gate.py` (cache), `adoption.py` (ADR-0007),
   `evals/uplift.py` (ADR-0003), `evals/canary/history.jsonl` (ADR-0003). Rows whose
   source is absent render gray.
6. **`agentic-cfg gain --write`** emits `SCORECARD.md`; commit the first generated
   copy.
7. **`telemetry/README.md`** weekly-review section; add `scorecard_selftest.py` to
   `bin/ci-check.sh`.

## Validation commands and targets

```sh
# (1) sub-minute diff: regenerate on two different days, diff must be a few cells
bin/agentic-cfg gain --write && git --no-pager diff --stat SCORECARD.md

# (2) every row populates from live transcripts; zero hand-typed numbers
bin/agentic-cfg gain --json | python3 -c "import json,sys; \
  rows=json.load(sys.stdin)['rows']; \
  assert all(r['source'] for r in rows); print(len(rows),'rows sourced')"

# (3) balanced rule enforced (selftest, no transcripts)
python3 telemetry/scorecard_selftest.py

# (4) experiment attribution: per-class + CUPED-adjusted deltas with CIs
python3 telemetry/experiment.py --cutover 2026-06-26 --json | \
  python3 -c "import json,sys; d=json.load(sys.stdin); \
  print(sorted(d['classes'])); assert 'cuped' in d['continuous']['opus_token_share']"

# (5) honest cost framing: secondary row is labeled, never green
bin/agentic-cfg gain --json | python3 -c "import json,sys; \
  r=[x for x in json.load(sys.stdin)['rows'] if x['key']=='api_equiv_cost_proxy'][0]; \
  assert r['secondary'] and 'NOT the' in r['label']"
```

Targets (from `synthesis.scorecard` verification, `/tmp/research_digest.json`
line 72, and ADR-0004 Validation):

- **(1)** the day-over-day `SCORECARD.md` diff is readable in under a minute (only
  value/target/status cells move).
- **(2)** all nine scorecard rows populate from live reconstructed transcripts;
  unavailable sources render gray, never green.
- **(3)** a cost win + a quality regression yields the `NOT_ACCEPTED` verdict.
- **(4)** a >=15% change in a continuous KPI is detectable within the developer's
  real variance, reported within task class; rare-event rows that are underpowered
  render gray with a "needs weeks" label.
- **(5)** `opus_token_share` is the primary cost row; `$est` is the labeled
  secondary "API-equivalent, not the bill."

## Dependencies and sequencing

**Wave 3** — the roll-up, after every instrument it aggregates exists
(`/tmp/research_digest.json`, `sequencing`, Wave 3: "finally telemetry/scorecard.py
to aggregate all 6-10 KPIs into one weekly-reviewed SCORECARD.md").

`depends_on`:

- **ADR-0001 (Wave 0)** — *hard* dependency: session reconstruction + corrected
  units + the captured baseline. `scorecard.py` and `experiment.py` consume the
  reconstructed-session view and refuse to run on raw `**/*.jsonl` (critique
  P0-1/P0-2). Without it the cost-share and per-session rows are on the wrong unit.
- **ADR-0002** — the quality proxies (tool-error, edit-revert, user-correction,
  latency) and the OTel names the scorecard rows read.
- **ADR-0003** — `evals/uplift.py` differential uplift and the canary
  `history.jsonl` rows; the canary is also the *primary* quality guard the scorecard
  defers to over the noisy real-session proxies (critique P1-5).
- **ADR-0005** — the main-thread, sidechain-excluded Opus-share KPI and the
  task-class clustering `experiment.classify` reuses.
- **ADR-0007** — `telemetry/adoption.py` for the adoption row.

Nothing depends on this plan; it is the leaf. No dependency on the Go rewrite —
`bin/agentic-cfg` is shell now and folds into `agentic gain` at GO-15/GO-16.

## Risks and mitigations

- **Wrong unit / population (P0-1, P0-2):** consume only the reconstructed,
  sidechain-excluded, `<synthetic>`-filtered view from ADR-0001/0005; refuse to
  render a row whose source was not reconstructed.
- **Undefined "resolved" (P0-3):** drop "resolved"; report cost/turns per task
  class with CIs from `experiment.py`; "cost per resolved task" is a labeled
  lower-confidence derived row only.
- **CUPED oversold on rare events (P2-11):** `experiment.py` routes rare-event
  rates through `rare_event_delta` (no CUPED) with detectability flags; the
  scorecard renders underpowered guard rows gray.
- **Overclaimed power (P2-11):** every rare-event row carries a CI and a
  "needs N sessions / weeks" annotation when its CI straddles zero.
- **Scorecard Goodhart:** the deterministic canary (ADR-0003) is the primary
  routing quality guard, separate from the real-session proxies; a change is never
  accepted on a green table alone if the canary or differential-uplift rows regress.
- **Artifact drift:** `--write` overwrites `SCORECARD.md` wholesale; the header
  records command + cutover + window for reproducibility.

## Effort and checklist

**Effort:** M (two stdlib modules + a shell dispatcher + a generated artifact and a
selftest; the CUPED/CI math is the only non-trivial logic). Aligns with the digest's
`effort: "M"` for the scorecard and experiment proposals.

- [ ] `bin/agentic-cfg` dispatcher with `gain` arm (folds into Go GO-15/GO-16)
- [ ] `telemetry/scorecard.py`: `ROWS`, `build`, `balanced_verdict`, `render_md`, `to_json`, `--json/--write`
- [ ] Primary cost row = main-thread Opus token-share; `$est` secondary, labeled "not the bill"
- [ ] `telemetry/experiment.py`: `classify`, `split`, `cuped_delta`, `rare_event_delta`, `report`
- [ ] Continuous vs rare-event separation with detectability labels (P2-11)
- [ ] Consume reconstructed-session view from ADR-0001 only (P0-1, P0-2)
- [ ] `telemetry/scorecard_selftest.py`: balanced-rule + CUPED CI-narrowing + rare-event flag
- [ ] `SCORECARD.md` generated and committed with a reproducible header
- [ ] `telemetry/README.md` weekly keep/iterate review cadence
- [ ] `scorecard_selftest.py` wired into `bin/ci-check.sh`
- [ ] Validation commands (1)-(5) pass against live transcripts

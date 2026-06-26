# W3 — Overhead KPI & gate (make ≤1.5× measurable and enforced)

> Parent: [../06-overhead-and-uplift.md](../06-overhead-and-uplift.md). Extends ADR-0001
> (`report.py`), ADR-0003 (eval backbone), ADR-0004 (`scorecard.py`/`experiment.py`),
> ADR-0007 on branch `722d6e2`. **Sequence this FIRST** — the others are validated by it.

## Goal

Turn "≤1.5× overhead" from an aspiration into a committed, gated number. The ADR program
measures Opus token-*share* and cache-hit, but **never the ON-vs-OFF overhead multiplier**
the owner cares about (ADR digest §7). W3 adds exactly that instrument.

## Why it must come first

W1 and W2 are projections until measured. The 2026-06-26 decomposition already showed the
naive `total_input` ratio (3.93×) is misleading (95% `cache_read`; repriced 1.25×;
cost 2.04×). Without a committed metric that reports the *right* numbers, every later claim
is unfalsifiable.

## Changes (concrete)

1. **Reusable A/B runner.** Promote
   [`evals/experiments/haiku_overhead_decomp.py`](../../evals/experiments/haiku_overhead_decomp.py)
   into `evals/overhead.py`: given a task-pair (easy + hard) and a model, run both arms
   (prompt-isolation by default; config-dir when `ANTHROPIC_API_KEY` is present — the
   higher-confidence mode per `evals/lib/render_config.py`) and emit per-arm:
   `total_input`, `repriced_input` (`input` + `cache_creation`), `output`, `cost_usd`,
   `turns`, `tool_calls`, `prefix_turn1_ctx`, plus the **ratios** ON/OFF for each.

2. **Extend `agent.metrics()`** (`evals/lib/agent.py`) to also surface, from stream-json:
   - `repriced_input_tokens` (= `input_tokens` + `cache_creation_tokens`);
   - `prefix_turn1_ctx` (first assistant message's `input + cache_creation + cache_read`);
   - `cost_usd`, `duration_ms`, `num_turns` from the `result` event.
   (The cumulative usage fields already land here from P2.)

3. **Committed canary task-pair** under `evals/canary/cases/` (ADR-0003 `canary` track):
   - `overhead-lookup-easy` — a trivial single-fact lookup; deterministic correctness
     check; records the easy-regime ratio.
   - `overhead-structural-hard` — a structural task where a bare agent flails;
     deterministic correctness check; records the hard-regime ratio.
   Both carry the expected answer so correctness is auto-scored, not judged.

4. **Scorecard rows (ADR-0004).** Add two rows to `telemetry/scorecard.py` `ROWS`:
   - `overhead_ratio_easy` — target `≤ 1.5`, `quality_guard=True` (regression blocks the
     overall verdict even if other targets pass).
   - `overhead_ratio_hard` — target `≤ 1.0` (guard: the toolset must keep paying off
     where it matters).
   Every cell generated from `evals/overhead.py` output (zero hand-typed, per ADR-0004).

5. **Gate (ADR-0001/0005 pattern).** `telemetry/gate.py --max-overhead-ratio 1.5`
   (easy regime) and `--max-hard-overhead-ratio 1.0`; non-zero exit on breach. Wire into
   `bin/ci-check.sh` behind a flag (the A/B costs LLM calls, so default to the
   deterministic scorecard read in CI and run the live A/B on demand / scheduled).

6. **Pure-logic selftests** (`evals/selftest.py`, zero-token): `test_overhead_ratio_verdict`
   (boundary inclusive at 1.5), `test_repriced_split`, `test_prefix_turn1_extraction`
   against a synthetic stream-json fixture (extend the existing
   `test_metrics_parses_token_usage`).

## Validation

- `evals/overhead.py` reproduces the 2026-06-26 numbers on the same task-pair (±noise),
  proving the instrument is faithful.
- Scorecard renders the two overhead rows with live values; `gate.py` exits non-zero when
  fed a synthetic >1.5 easy ratio and zero at ≤1.5.
- Selftests green in CI with no LLM calls.

## Projected gain

No token gain itself — this is the *enabler*: it makes W1/W2's gains claimable and guards
against regression. Its only cost is the LLM A/B run (already bounded and owner-approved
for the P2 sample); the deterministic scorecard/gate path is zero-LLM.

## Risks

- **n=1 noise.** A single A/B is directional. Mitigate: support `--k` repetitions and
  report median (cheap on Haiku); pool the canary over scheduled runs (ADR-0003 `pass^k`).
- **Prompt-isolation leakage.** OFF still loads the config and is merely told to ignore it
  (medium confidence). Document confidence on every verdict (ADR-0001 pattern); prefer
  config-dir isolation when an API key is available.

## Decisions for the owner

- The exact easy/hard canary tasks (propose: reuse the 2026-06-26 pair as the seed).
- Whether to grant an `ANTHROPIC_API_KEY` for high-confidence config-dir isolation, or
  stay on prompt-isolation (cheaper, medium confidence).
- Re-run cadence: on-demand only, or scheduled (ADR-0003 canary, pinned cheap model).

# telemetry — token & cache measurement (Phase 0)

Turns "the stack saves tokens" from a claim into a measured number. Reads the
JSONL transcripts Claude Code writes under `~/.claude/projects/**/*.jsonl` and
reports token volume, cache hit rate, estimated cost, the main-thread vs
subagent split, and tool-call distribution.

Read-only on the transcripts. Stdlib only — no dependencies, no network.

## Built-in readout: `agentic gain`

The fastest way to see what this config is buying you is the built-in command in
the `agentic` binary — no Python, no flags to remember:

```bash
agentic gain                       # last 20 sessions
agentic gain --last 50 --project agentic-cfg
agentic gain --json                # machine-readable
agentic gain --by-model            # per-model token share — is the cheap tier carrying the bulk?
agentic gain --adoption            # enforcement coverage: shell-guard wrap/deny/fail-open shares
agentic gain --gate                # regression gate: exit 1 if hit rate < 80% (CI-friendly)
```

```
agentic-cfg gain — session token economy over 20 session(s)
  input (fresh)      : 205k
  cache read         : 239.0M
  cache write        : 6.9M
  output             : 1.5M
  cache hit rate     : 97.1%   (cache_read / total input) — healthy (≥ 80% floor)
  subagent share     : 23.7%   (context isolated off the main thread)
  input bill (actual): $278.83  (input + cache — what you actually paid)
  cache avoided      : $1549.31  (85% — vs re-sending the same context uncached)
  est. total cost    : $331.93  (incl. output; approximate — verify rates)
  note: prompt caching is a Claude platform feature; agentic-cfg's lever is cache
        hygiene (a warm, byte-stable prefix), not the avoided figure itself.
```

It mirrors `report.py`'s parsing (and agrees with it on the hit rate), but leads
with the **gain**: the token-weighted cache-hit rate and the input-token cost the
cache is avoiding — a write-heavy session that never reuses its cache correctly
shows a *negative* saving. Use `report.py` below for the richer per-session table,
tool breakdown, and cost detail. Implementation: `internal/gain/` (Go,
unit-tested), wired in `cmd/agentic/main.go`.

`--adoption` complements — it does not replace — the cache metrics above: it
measures whether the *enforcement layer* is actually covering the traffic
(shell-guard wrap/deny/fail-open shares, deny events observed in transcripts,
and ast-grep/GitNexus/native-tool call counts), rather than the token
economy of the traffic that does get wrapped.

## Usage (`report.py`)

```bash
python3 telemetry/report.py                # last 10 sessions
python3 telemetry/report.py --last 30
python3 telemetry/report.py --project agentic-cfg
python3 telemetry/report.py --by-tool      # tool-call breakdown
python3 telemetry/report.py --json         # machine-readable
```

## What the columns mean

- `in` — fresh (uncached) input tokens. Lower is better; these are the most
  expensive input tokens.
- `cache_rd` — input tokens served from the prompt cache (cheap).
- `hit%` — `cache_read / (input + cache_read + cache_write)`. The single most
  important lever for token cost; high is good. Short sessions show low hit
  rates because the static prefix never gets reused — that is the Phase 1 target.
- `sub%` — share of input tokens spent on subagent (sidechain) turns. Work
  delegated to subagents keeps the main thread's context small.
- `$est` — approximate cost from the `PRICING` table in `report.py`. Edit those
  rates to match current Anthropic pricing; treat the figure as relative, not a
  bill.

## Notes

- One `.jsonl` file = one session row. A subagent's sidechain transcript is a
  separate file, so it shows up as its own row with `sub%` at 100%.
- Cost uses the per-message `model` and the 1h/5m cache-write breakdown when the
  transcript records it, falling back to 5m pricing for older records.

## Regression gate (Phase 3)

`gate.py` turns the metric into a pass/fail check — a cheap, zero-LLM guard
against a change that wrecks cache reuse.

```bash
python3 telemetry/gate.py                  # fail if weighted hit rate < 80%
python3 telemetry/gate.py --min-hit-rate 0.85 --last 30
python3 telemetry/gate.py --json
```

It uses the **token-weighted** hit rate (`sum(cache_read) / sum(total_input)`)
over the last N sessions, not a per-session average, so cold-start noise from
short sessions doesn't trip it. Exit codes: `0` pass or insufficient data
(skipped), `1` regression, `2` bad usage. The `--min-tokens` guard skips rather
than fails when the window is too small to judge.

The default `0.80` floor is calibrated from the observed range (86.7%–95.1%
across project windows) with margin; a real cache-busting regression lands far
below it. This gate is **local-only** — it reads `~/.claude` transcripts, which
do not exist in GitHub CI. See [INTEGRATION.md](INTEGRATION.md) for folding it
into the `evals/` framework as a `metric` track.

## Why this is Phase 0

Every other token-economy change (trimming always-loaded tool schemas, fixing
cache hygiene, adding a subagent-orchestration discipline) needs a before/after
number to justify it. This script is that measuring stick.

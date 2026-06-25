# telemetry — token & cache measurement (Phase 0)

Turns "the stack saves tokens" from a claim into a measured number. Reads the
JSONL transcripts Claude Code writes under `~/.claude/projects/**/*.jsonl` and
reports token volume, cache hit rate, estimated cost, the main-thread vs
subagent split, and tool-call distribution.

Read-only on the transcripts. Stdlib only — no dependencies, no network.

## Usage

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

## Why this is Phase 0

Every other token-economy change (trimming always-loaded tool schemas, fixing
cache hygiene, adding a subagent-orchestration discipline) needs a before/after
number to justify it. This script is that measuring stick.

# Benchmarks-impact wave index (2026-07-02)

Goal (user request): make `evals/BENCHMARKS.md` an **honest, clear impact dashboard** —
the effect of agentic-cfg as a whole AND of each constituent tool (rtk/shell-guard,
lean-ctx, gitnexus, ast-grep) on **haiku / sonnet / opus**, with at least: task speed,
tokens used, tool calls. Honesty is the top requirement: measured numbers with n and
spread, hypotheses labeled, unmeasured cells said out loud.

Worktree: `agentic-cfg-bench` on `feat/benchmarks-impact` (off master) — the main
checkout is occupied by a parallel wave (`feat/audit-fixes-2026-07`).

## Currency audit findings (task: "are the current tests/benchmarks up to date?")

1. **All June matrix data is doubly confounded.** The `plans/data/*.json` runs
   (06-26…06-30) ran their ON arm against the live `~/.claude`, which at the time had
   (a) the user's `codebase-memory-mcp` hooks driving most tool calls (removed
   2026-07-02), and (b) a **dead gitnexus server** (broken since 06-24, fixed 07-02,
   PRs #14/#15). Those numbers describe a config that no longer exists — historical
   record only.
2. **The ON arm is ambient, not isolated.** `overhead.py`/`swe_bench.py` run the
   configured arm against the real `~/.claude` (`render_config.py:37,169`); with
   parallel sessions actively installing things, ambient state drifts mid-run. Fix in
   this wave: an isolated full-config render (arms never touch the live machine).
3. **Duration is captured but not reported.** `agent.metrics()` returns `duration_ms`
   (`agent.py:176-178`); neither runner medians or prints it. The user's "speed"
   column requires surfacing it.
4. **BENCHMARKS.md is stale**: two value-track rows, both under the pre-2026-07-01
   biased-control caveat, one for a retired skill; no matrix, no per-tool, no
   real-adoption view; `report.py` renders the value track only.
5. **Fresh, usable evidence exists elsewhere**: gitnexus A/B (n=1, small repo:
   3/3 correct both arms, 63.4k vs 82.3k tokens, 138s vs 225s —
   `plans/gitnexus-fix/DESIGN.md`) and 50-session real-adoption telemetry
   (`agentic gain --adoption`; lean-ctx ~12 ctx_* calls vs 644 native Reads,
   gitnexus 1 call pre-fix). Both belong in the dashboard, correctly labeled.

## Execution

| Step | Plan | Owner |
|------|------|-------|
| 1 | [01-harness-arms.md](01-harness-arms.md) — isolated full render + `--arms` axis + duration | `implementer` (sonnet) in this worktree |
| 2 | [02-run-matrix.md](02-run-matrix.md) — the right-sized run protocol | orchestrator (background runs) |
| 3 | [03-benchmarks-rewrite.md](03-benchmarks-rewrite.md) — the honest dashboard | orchestrator authors; `verifier` fact-checks |

## The matrix (right-sized; ~63 API runs)

Arms (each an isolated `CLAUDE_CONFIG_DIR`, never the live `~/.claude`):

| Arm | Meaning |
|-----|---------|
| `bare` | no config at all (existing `render_bare_control`) — the control |
| `full` | today's complete render: prefix + hooks + skills + agents + lean-ctx & gitnexus MCP |
| `no-leanctx` | full minus lean-ctx (MCP + redirect hook + allow entries) |
| `no-gitnexus` | full minus gitnexus MCP |
| `no-shellguard` | full minus the `^Bash$` shell-guard group (no rtk rewrite, no grep deny) |

Cells, n=3 each:
- **Headline** `bare`+`full` × {haiku, sonnet, opus} × {easy, hard} = 36 runs.
- **Per-tool** ablations, each measured in the regime where the tool plausibly acts:
  `no-leanctx`, `no-shellguard` × 3 models × {easy}; `no-gitnexus` × 3 models ×
  {hard} = 27 runs. The other regime per tool is reported as **unmeasured**.
- ast-grep gets no matrix arm: its effect is already isolated by the value-track
  case (`ast-grep-structural-precision`) — re-run under the bare control instead.

Metrics per cell: median `duration_ms`, `total_input_tokens`, `repriced_input_tokens`
(billed), `output_tokens`, `tool_calls`, `num_turns`, `cost_usd`, correctness, plus
per-rep min/max spread and errored-rep count.

## Global acceptance

1. `python3 evals/swe_bench.py --selftest` passes (extended for arms/duration), zero
   API tokens spent by tests/lint.
2. `bash bin/ci-check.sh`, `go test ./... -count=1`, `python3 evals/lint.py`,
   `python3 evals/selftest.py` all green in this worktree.
3. Matrix JSONL lands under `plans/data/` with a dated name; every BENCHMARKS.md
   number traces to a JSONL record or a named external doc; no unmeasured claim
   stated as fact.
4. The live `~/.claude` is never mutated by runs (arms are isolated; assert via
   mtime check in the run protocol).

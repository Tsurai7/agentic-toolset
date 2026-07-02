# Plan 03 — BENCHMARKS.md: the honest impact dashboard

Part of [`00-INDEX.md`](00-INDEX.md). Authored by the orchestrator from plan 02's
data; fact-checked by the `verifier` role before commit.

**File scope:** `evals/BENCHMARKS.md` (+ `evals/report.py` ONLY if the value-table
regeneration would clobber the new sections — verify the notes-preservation
mechanism covers them; if it does, no code change).

## Target structure

1. **Header** — what this file is, eval-set version, which sections are
   machine-generated (value table, by `report.py`) vs hand-maintained-from-data
   (impact matrix; each row cites its JSONL), and the honesty rules (no number
   without n and source; unmeasured cells written as "unmeasured").
2. **Headline: agentic-cfg ON vs OFF** — table rows = model × task-tier, columns:
   `Duration (s, median)` | `Billed input tokens` | `Total input` | `Output` |
   `Tool calls` | `Turns` | `Cost $` | `Correct` | `n (effective/attempted)` —
   one row-pair (bare/full) per cell + a delta line. Source: impact-matrix JSONL.
3. **Per-tool impact** — one subsection per tool (shell-guard/rtk, lean-ctx,
   gitnexus, ast-grep): the ablation delta (full vs full-minus-tool) per model in
   its measured regime; the OTHER regime explicitly "unmeasured (not run — see
   INDEX rationale)". ast-grep cites the value-track row + its mechanism
   (deny-nudge) instead of an ablation arm. gitnexus additionally cites the n=1
   A/B from `plans/gitnexus-fix/DESIGN.md` with its caveats.
4. **Real-session adoption (the honesty counterweight)** — controlled benchmarks
   ≠ real usage: the `gain --adoption` numbers (lean-ctx/gitnexus call counts vs
   native, fail-open share), dated, with the gitnexus removal-trigger note.
5. **Value-track table** — the existing machine-generated section, refreshed by
   the plan-02 re-run; keep `report.py` ownership.
6. **Deprecated data** — one paragraph moving the June numbers to historical
   status (dead-gitnexus + cbm confounds), pointing at `plans/data/*2026-06*`.
7. **Method + caveats** — isolated arms (incl. the `--mcp-config` fidelity note),
   n=3 medians with spread, single-repo synthetic tasks, model IDs pinned, date.

## Acceptance

1. Every number in the file greps back to a JSONL record, a named doc, or a
   dated command output; zero unattributed numbers (verifier checks a sample of
   ≥10 numbers end-to-end).
2. Columns requested by the user present: speed, tokens, tool calls — plus turns,
   cost, correctness, n.
3. The two stale caveat notes are superseded correctly (old value rows either
   re-run or explicitly retired), and `python3 evals/report.py` regenerated on top
   does NOT destroy the new sections (run it; diff before/after).
4. `bash bin/ci-check.sh` green; PR from `feat/benchmarks-impact` with the wave.

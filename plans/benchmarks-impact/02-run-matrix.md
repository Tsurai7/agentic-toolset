# Plan 02 — Run protocol (orchestrator)

Part of [`00-INDEX.md`](00-INDEX.md). Runs happen from the bench worktree after
plan 01 verifies green. Estimated ~63 API runs ≈ 1.5–3 h wall with modest
parallelism; cost is real (rough order: tens of dollars) — record actuals.

1. Preflight (zero-token): `--selftest` green; `render_full_variant` smoke —
   render each arm once, `ls` the dirs, `python3 -m json.tool` the mcp configs;
   snapshot `stat -f %m ~/.claude/settings.json ~/.claude.json` (must be unchanged
   after all runs — arms are isolated).
2. Stage A (headline, 36 runs): `--arms bare,full --models haiku,sonnet,opus`
   `--tasks easy,hard --reps 3 --out plans/data/impact-matrix-2026-07-02.jsonl`
   (background; incremental JSONL survives interrupts).
3. Checkpoint: sanity-read stage A (correctness rates, errored reps, spread). If a
   cell shows >1 errored rep, re-run that cell before proceeding.
4. Stage B (ablations, 27 runs): `--arms no-leanctx,no-shellguard --tasks easy` and
   `--arms no-gitnexus --tasks hard`, same models/reps/out file.
5. Value-track re-run under the bare control (ast-grep case):
   `python3 evals/run.py --track value --case ast-grep-structural-precision
   --model claude-opus-4-8` (+ haiku, sonnet if budget allows) — refreshes the
   stale pre-isolation row.
6. Adoption snapshot (zero-token): `bin/agentic gain --last 50 --adoption --json`
   from the MAIN checkout (live telemetry, not the worktree) → save to
   `plans/data/adoption-2026-07-02.json`.
7. Post-run: mtime assert from step 1; total cost tally from the JSONL `cost_usd`
   sums; hand the data to plan 03.

Honesty rails: never average across models or tiers; report per-cell medians with
min/max; errored reps are excluded from medians but counted in the record; any cell
with n_effective < 3 gets flagged low-n in the dashboard.

# W5 — Minimal-tier profile (the environmental ≤1.5× lever)

> Parent: [../06-overhead-and-uplift.md](../06-overhead-and-uplift.md). Opened after the
> live measurement falsified W1's prompt-only approach (see "Evidence" below). Relates to
> ADR-0006's model-tier render fork on branch `docs/adr-measure-uplift-program`.

## Why this exists — W1 was measured and did not work

W1 added a "right-size the tooling" triage gate to the always-on prefix on the hypothesis
that a prompt instruction would stop a weak model from over-engaging trivial tasks. The
live before/after on Haiku (PR #8 comments, `evals/overhead.py --confirm`, n=1 per cell,
prompt-isolation) falsified it:

| | easy total_input | easy cost | easy turns ON/OFF | hard total_input | verdict |
|--|---:|---:|---:|---:|--|
| before (pre-W1) | 5.33× | 2.42× | 16 / 4 | 0.79× | FAIL |
| after (W1 triage gate + W2 de-dup) | 4.11× | 2.42× | 20 / 6 | 1.83× | FAIL |

The gate did not move Haiku off over-tooling (16→20 turns ON, still ~3–4× the OFF arm).
A CLAUDE.md instruction cannot override hooks that fire regardless of the prompt.

## Diagnosis (already evidenced)

The over-tooling is driven by the **custom tool environment, not the prompt**:

- The ON arm routes Read/Grep through the `lean-ctx hook redirect` PreToolUse hook
  (`providers/claude/settings.hooks.json`) plus the MCP layer, which induces a multi-step
  orientation dance on a task that needs one grep (16–20 turns).
- The OFF arm — instructed to use only built-in tools (no lean-ctx/rtk/ast-grep/MCP) —
  runs the same tasks in 4–6 turns at **~1× total_input**.

So the OFF arm is effectively the target "minimal" profile, and it already sits near 1×.
The direction is proven; what is unproven is the *minimal safe cut* and whether the custom
layer helps weak models at all (see Open question).

## Goal

A **weak-tier / minimal profile**: render the config without the turn-inducing custom
layer for weak models or cheap/short sessions, so the ON path behaves like the OFF path
(≤1.5×) on trivial work, while strong-tier sessions keep the full layer. The lever is the
**install/render**, not the prompt.

## Methodology — measure FIRST (the W1 lesson)

Do not build the profile on another untested hypothesis. Use the W3 instrument
(`evals/overhead.py`) on config-based variants to pinpoint the culprit and the smallest
cut that works:

1. **Ablation (gated — see Blocker):** measure, as config variants of the ON arm:
   - full ON (baseline),
   - ON minus the `lean-ctx hook redirect` PreToolUse group (keep rtk + shell-guard + MCP),
   - ON minus MCP (keep all hooks),
   - minimal (drop the redirect group + MCP; keep shell-guard's ast-grep deny + rtk).
   Pick the smallest cut that brings the easy regime ≤1.5× without losing the hard-task
   win. This tells us exactly what to remove (vs W1, which removed nothing real).
2. **Implement** the profile: an install flag (`AGENTIC_TIER=weak`, or `--profile minimal`)
   that renders `settings.hooks.json` without the chosen group(s) and skips the heavy MCP
   registration. Default stays the full "strong" tier; reuse the existing managed-merge so
   user hooks survive. Add a render/golden test.
3. **Validate** with `evals/overhead.py --confirm` against the minimal config as the ON
   arm: require easy ≤1.5×, hard ≤1.0×, and no correctness regression. Ship only if it
   passes (the W3 gate is now the contract).

## Blocker

The ablation and the config-based validation must edit `~/.claude/settings.json` to remove
the lean-ctx redirect hook. That is **unsafe while the concurrent session relies on it**,
and config-dir isolation needs `ANTHROPIC_API_KEY` (absent). Unblock by one of:

- a safe window where no other session is using `~/.claude` (then swap-measure-restore, as
  done for the prefix in PR #8), or
- an `ANTHROPIC_API_KEY` for clean config-dir isolation (`evals/lib/render_config.py`), or
- a fixture-`$HOME` harness with an env key (extends `internal/installtest`).

Until then, the implementation (step 2) can be built and unit/golden-tested deterministically;
only the live ≤1.5× validation (steps 1, 3) is gated.

## Open question (needs n≥3, not n=1)

Does the full custom layer help weak models on *hard* tasks, or is minimal≈vanilla simply
better for them? The hard-task ON/OFF was 0.79× then 1.83× across two runs — inconclusive.
If the layer does not help weak models even on hard tasks, the minimal profile for the weak
tier is strictly better and the question becomes whether agentic-cfg's custom tooling is
worth its cost for any weak-model use at all. Resolve with a judged, n≥3 hard-task suite
(ADR-0003 differential uplift) before committing to keep the layer for the weak tier.

## Decisions for the owner

- Profile mechanism: an `AGENTIC_TIER`/`--profile` flag on the existing installer, or a
  separate install target? (Recommend the flag — minimal new surface.)
- What stays in "minimal": drop only the lean-ctx redirect + MCP (keep shell-guard safety),
  or go fully vanilla? (The ablation decides.)
- Default tier (recommend strong, weak opt-in).

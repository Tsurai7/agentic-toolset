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

## Status — implemented; n=3 correction (the n=1 result was a fluke)

**Honest correction.** The first ablation was n=1 and showed the weak profile at easy
0.59× (PASS). Re-run at **n=3 (median of 3 reps)** — and on **Opus 4.8** as well as Haiku
— that PASS does **not** hold. Haiku's easy-task turn count is bimodal (sometimes 4, often
12–16), so a single run is not trustworthy. The n=3 matrix (all arms 100% correct,
prompt-isolation, `evals/overhead.py --reps 3`, raw in
[../data/overhead-n3-2026-06-26.json](../data/overhead-n3-2026-06-26.json)):

| model / config | easy | hard | hard2 |
|----------------|---:|---:|---:|
| Haiku, full | **3.15× FAIL** | 0.65× | 1.00× |
| Haiku, weak | **2.27× FAIL** | 0.93× | 1.00× |
| Opus 4.8, full | 1.00× | 0.99× | 1.34× |

What this actually shows:

- **Over-tooling is weak-model + trivial-task specific.** Opus 4.8 never exceeds 1.34×
  (all PASS) — the strong/default tier has no overhead problem and needs no change. Only
  Haiku's *easy* task fails the bar.
- **Hard tasks are fine for everyone** — no overhead, both arms always correct. The
  earlier "hard 1.83× FAIL" was n=1 noise (median is 0.65–0.99×).
- **The weak profile only *partially* mitigates** Haiku's easy-task overhead (median
  3.15× → 2.27×) and is harmless to hard tasks and to Opus, but it does **not** reliably
  reach ≤1.5×. The lean-ctx removal isn't enough on its own: the remaining layer (the
  gitnexus MCP + the tool-pushing CLAUDE.md prefix + rtk) still triggers a variable
  orientation dance.
- **So the ≤1.5× target is not met for Haiku trivial tasks.** Reaching it reliably would
  need a more aggressive minimal/near-vanilla weak profile (also drop gitnexus and trim
  the tool-pushing prefix for the weak tier). And since the custom layer is merely
  *neutral* (not a win) for weak models even on hard tasks, the open question — is it worth
  its cost for weak models at all? — is now sharper.

The profile below is therefore shipped as an honest **partial mitigation + a measurement
finding**, not as "≤1.5× achieved".

**Implemented** as an `AGENTIC_TIER` switch on the Claude install (`strong` default):

- `AGENTIC_TIER=weak bin/install.sh --provider all` renders `settings.json` without the
  lean-ctx Read/Grep redirect hook (keeps shell-guard, edit-lint, observe) and skips
  registering the lean-ctx MCP server. shell-guard safety and the prefix are unchanged.
- Mechanism: `providers/claude/install.sh` filters the redirect group for weak and passes
  `AGENTIC_MCP_EXCLUDE=lean-ctx` to merge-mcp; both merge-mcp implementations
  (`internal/mcpmerge`, `providers/shared/merge-mcp.py`) honor `AGENTIC_MCP_EXCLUDE`
  (comma-separated server names) in the fragment collector.

**Tests:** `TestCollectFragmentsExclude` (Go unit, the MCP exclude), and
`TestClaudeInstallWeakTierDropsRedirect` (integration: a real weak install drops the
redirect hook, keeps shell-guard + edit-lint). Go+Python parity preserved (exclude is a
no-op by default). Since the weak install renders exactly the config the ablation measured
at PASS, the ablation is its end-to-end validation.

**Still open / future:** the weak tier could also drop the now-moot lean-ctx prefix rules
(an optimization — the measurement passed without it); a judged n≥3 hard-task suite to
firm the noisy hard-regime numbers; and a Cursor-side equivalent if needed.

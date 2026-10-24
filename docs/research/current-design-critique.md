# Current-design critique — keep / fix / drop

> An adversarial, evidence-first audit of agentic-cfg's *current* methods: which to keep, fix,
> or drop. Every verdict is grounded in a repo file or the repo's own measured data
> ([`plans/06`](../../plans/06-overhead-and-uplift.md), raw
> `plans/data/overhead-n3-2026-06-26.json`). Part of the research set: see
> [token-and-performance-improvements.md](token-and-performance-improvements.md) and the
> [roadmap](improvement-roadmap.md).
>
> **Framing.** The n=3 data is *damning for the weak/easy regime and exonerating for the
> strong/hard regime*. The decisive structural fact: **the toolset's value never appeared as a
> correctness uplift** — both ON and OFF arms were correct on all three tasks at all tiers; the
> only measured "value" was *fewer turns on hard tasks*. So on current evidence the custom layer
> is a **pure-efficiency play for hard tasks and a pure-tax for weak models on easy tasks.**
> Whether it provides *correctness* uplift anywhere is **unmeasured** — the sharpest open
> question in the repo, and the reason the roadmap leads with building a correctness suite.

## Verdict table

| # | Method | Verdict | Grounded in |
|---|--------|---------|-------------|
| 1 | Always-on **tool-precedence prose** (`AGENTS.md` §Tool precedence + Global defaults, 5,623 B = ~half the 11,120 B always-on source) | **FIX (weak tier): replace with a 3-line stub** | Diagnosed root cause of weak-model over-tooling (W1); but W1's *prompt* fix was falsified — prose can't override hooks. It costs bytes and induces literal-ladder behaviour weak models follow off a cliff. |
| 2 | **`lean-ctx` Read/Grep redirect hook** (`settings.hooks.json:9-12`) | **FIX → conditional; DROP on weak tier** | `plans/06` W5: the ON arm routes Read/Grep through `lean-ctx`, net-*adding* turns on trivial tasks; the OFF arm at ~1×. The single biggest measured turn-inducer. |
| 3 | **gitnexus MCP** always-loaded tool schema (`integrations/gitnexus`, *not* excluded by the weak tier — `install.sh` only drops lean-ctx) | **FIX: also exclude on the weak tier; KEEP on strong** | Always-on tool surface adds prefix + orientation pull; Go/.NET-only, so dead weight for other stacks. Untested in isolation — exclude-and-measure. |
| 4 | **Per-task model-tier routing** in `model-orchestration` ("execute cheap = Haiku") | **FIX: reframe** | The "execute cheap" tier is exactly where the config breaks (Haiku). Reframe around what *is* in-session-actionable: **subagent fan-out with model overrides** (Claude Code supports per-subagent model) + cross-session cost planning — not an implied in-prompt model switch. |
| 5 | **Pure-nudge principles** (`honesty`, `karpathy-guidelines`, `coding-principles`, `communication` — ~5.2 KB always-on) | **FIX: de-dup + demote; mechanize the one that matters** | The data says weak models don't follow prose. Keep a lean core; mechanize verification (Stop-hook). De-dup the documented overlaps (verify-before-done stated multiple times; karpathy/coding-principles overlap). |
| 6 | **Measurement rigor** (n=1 default / n=3 max, ratio-of-medians, substring correctness, prompt-isolation) | **FIX: more reps, functional grading, persist per-rep** | The n=1 weak-easy 0.59× fluke (retracted to 2.27× at n=3) *is* the proof that n=3 is below the agentic noise floor. Substring checks (`"4" in ans`) over- and under-pass. |
| 7 | **`shell-guard` / `edit-lint` hooks** | **KEEP** | The two genuinely *mechanical* levers — enforced, not nudges. The model for where quality work should go. |
| 8 | **Prefix byte budget** (`bin/prefix-budget.sh`) and the **measurement-first culture** | **KEEP** | Correct cache hygiene + the discipline that let the repo falsify W1. Its real superpower. |

## The four things to actually change (and why each is safe to test)

**Drop the turn-inducers from the weak-tier render — all of them, not just lean-ctx.** The repo
already has the plumbing: `install.sh` filters the redirect group and passes
`AGENTIC_MCP_EXCLUDE`. Extending the weak tier to also exclude gitnexus MCP and to render the
tool-precedence section as a 3-line stub is a small, reversible install-time change. *Hypothesis
(to measure, not assert):* this closes more of the 2.27× → ≤1.5× gap on weak/easy than tool-
stripping alone did, with **zero** impact on Opus (already 1.0×). *Risk:* a too-vanilla weak
profile could give back some hard-task turn-efficiency — which is precisely why it must be
measured per cell, not shipped on a projection. **The repo's own docs present "near-vanilla
closes the gap" as a path, not a result; this doc does the same.**

**Build the correctness suite the repo is missing.** Every current task is solved by both arms,
so *no current eval can show a correctness uplift* — yet the whole question of whether the custom
layer is worth keeping for weak models is a correctness question. Add tasks where **bare Haiku
actually fails and the toolset can help** (the [SWE benchmark](swe-benchmark-design.md) ladder's
`medium`/`very_hard` edit tasks are built for exactly this — functional `go test` grading, not
substring matching). Until this exists, every quality lever (Stop-gate, plan-gate, self-critique,
schema hand-offs) is unprovable under the repo's own PLAYBOOK. *Lead with this.*

**Harden the instrument: persist per-rep distributions, raise n, grade functionally.**
`overhead.py` already builds `on_runs`/`off_runs` per rep — serialize them (median + min/max/IQR)
instead of discarding after taking the median (~15 lines). Raise the default reps toward the
noise floor. Replace substring checks with the benchmark's `("state", go test)` functional
checks. This prevents another retracted-fluke episode and makes verdicts auditable. *Risk:* it
may reveal current "FAIL" verdicts are themselves noisy — which is information, not a setback.

**Reframe `model-orchestration` to what's actionable.** Keep the strong content (subagent fan-
out, context isolation, plan-strong/execute-cheap, the effort ladder), but stop implying an
in-prompt per-task model switch the weak tier can't perform. *(Caveat from the verifier: do
**not** state as fact that per-sub-task model down-routing is impossible in one Claude Code
session — Claude Code supports per-subagent model overrides; the honest framing is that the skill
should lean on that real mechanism and on cross-session planning, not on an aspirational mid-turn
switch.)*

## What the data does NOT license you to say

- That the custom layer is worthless for weak models. The hard-task efficiency (0.65×) is real;
  the **correctness** question is *unmeasured*, not answered.
- That any proposed gate/effort/critique change *will* improve correctness or *will* hit ≤1.5×.
  No current eval can show it; these are hypotheses for the benchmark.
- That prefix de-duplication is a meaningful cost win on a fixed task (it is ~95% `cache_read`).
  It is cache hygiene; pursue it as such.

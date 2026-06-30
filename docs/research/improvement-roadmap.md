# Improvement roadmap — prioritized, each item a testable hypothesis

> The ordered plan to make agentic-cfg cut more tokens and lift model performance, built from
> [the research review](token-and-performance-improvements.md) and the
> [keep/fix/drop critique](current-design-critique.md). Ordering is by **gain per token of
> effort**, and — following the repo's own hard-won lesson (it shipped, then falsified, W1) —
> **the instrument comes before the changes it judges.** Every row names the
> [SWE-benchmark](swe-benchmark-design.md) cell that decides it. Nothing here is asserted to
> work; each is a hypothesis to confirm or kill.

## Priority order

| # | Change | Hypothesis (falsifiable) | Decides it | Effort | Risk |
|---|--------|--------------------------|-----------|--------|------|
| **0** | **Build the correctness suite** — edit tasks where bare-weak *fails* (the `medium`/`very_hard` `go test` tiers) | A toolset effect on *correctness* exists and is measurable (today every arm is 100% correct, so nothing is provable) | swe_bench `medium`,`very_hard` × Haiku | M | Authoring tasks that flatter a lever — guard with PLAYBOOK's synthetic-case warning |
| **1** | **Harden `overhead.py`**: persist per-rep values (median+min/max), raise default reps, functional grading | Haiku's easy ratio has an IQR wide enough that n=3 can't gate a ship decision | re-run existing cells, report distribution | S | May show current FAILs are noisy → needs larger n (more tokens) |
| **2** | **Near-vanilla weak tier**: also exclude gitnexus MCP + stub the tool-precedence prose (not just lean-ctx) | Closes more of the 2.27×→≤1.5× gap on weak/easy than tool-stripping alone, **zero** Opus impact | swe_bench `trivial`,`easy` × Haiku vs Opus | S | Too vanilla → loses some hard-task turn-efficiency (measure `hard`,`very_hard`) |
| **3** | **Conditional Read/Grep redirect**: fire only on large/structural reads (proxy: file size / match count / glob breadth) or strong tier | Removes the trivial-task turn-inducer (12–20 turns → ~4) while preserving the hard-task structural win | swe_bench `trivial` (turns↓) + `hard` (turns held) | M | A hook can't see task "size" — proxy signals may misfire |
| **4** | **Per-tier reasoning-effort defaults** in `install.sh` (`AGENTIC_TIER` already plumbed) | Low effort on weak/trivial moves Haiku toward ≤1.5× where tool-stripping stalled; high effort lifts hard-task correctness | swe_bench all tiers × Haiku, Sonnet | S | Low effort under-thinks a misclassified hard task — pair with the heaviness heuristic |
| **5** | **Context editing** (tool-result clearing) in the runner, + a long multi-turn regime | On a session > ~30k tokens of tool results, clearing cuts `total_input` materially, no correctness loss | a new long-session benchmark cell | M | Needs an SDK/API-controlled runner; stock `claude -p` may not expose it |
| **6** | **Stop-hook verification gate** — block "done/tests pass" with no verifying command in the transcript | Reduces false-completion on Haiku/Sonnet without over-firing on pure-reasoning answers | suite #0 correctness × Haiku, Sonnet | M | Over-fires on legitimately-no-command tasks — gate on whether an edit/test was expected |
| **7** | **Enforced plan-gate** on first heavy-task edit (file-count heuristic) | Fewer backtracks/wrong turns and tighter in-scope diffs on multi-file tasks vs ungated | swe_bench `very_hard` × Haiku, Sonnet | M | Friction on borderline tasks — fire only above a file-count threshold |
| **8** | **Schema-enforced subagent hand-offs** (vs opt-in `answer-shapes`) where the runner owns the call | Format-driven re-ask turns → ~0; beats `answer-shapes` on weak-executor reliability | an orchestrator→subagent hand-off micro-eval | M | Schema rigidity on freeform sub-tasks — apply only to machine-consumed hand-offs |
| **9** | **Conditional weak-tier self-critique** (W4 step 3, designed, unbuilt) — one bounded, hard-task-gated pass | Lifts weak+hard correctness without regressing the easy band | suite #0 `very_hard` × Haiku (two-band value case) | M | The self-critique paradox (hurts high-base tasks) — hard-task trigger only |
| **10** | **Cache hygiene**: 1h TTL for spaced eval runs + byte-stable post-compaction prefix (extend `PreCompact` hook) | Holds cache hit ≥85% across spaced requests; cuts repeated turn-1 `cache_creation` | telemetry hit-rate before/after | S | 1h TTL costs ~2× on write — net loss on truly one-shot runs |

## Sequencing rationale

**Instrument first (0–1).** The repo's defining win was building the gate *before* the change,
which let it falsify a plausible fix. Re-apply that: a correctness suite (where bare-weak fails)
and a hardened, distribution-reporting `overhead.py` must exist before anything in 2–9 is
"shipped," or the repo risks another retracted finding.

**Environmental cuts next (2–4), because the data points there.** The over-tooling is
environment-driven and weak-tier-specific; the cheapest large wins are *removing* the turn-
inducers from the weak render and setting effort defaults — not adding anything. These are
small, reversible install-time changes the plumbing already supports.

**Then the API-level and mechanized-quality levers (5–9),** which need either an SDK runner
(context editing, schema outputs) or new hooks (Stop-gate, plan-gate, self-critique). Each is
isolated to a regime where it can't regress the others, and each is held behind its benchmark
cell. Performance levers (6–9) are explicitly *unproven* until suite #0 exists — that is why
suite #0 is item 0.

**Cache hygiene (10) last** — genuinely useful but low-yield relative to turns; do it once the
high-leverage levers are settled.

## The acceptance rule (unchanged from the repo's own bar)

A change ships only if, on the same benchmark matrix as its baseline:

1. the trivial/easy overhead moves toward **≤1.5×** (cost and `total_input`),
2. the hard-regime ratio stays **≤1.0×**, and
3. **no cell regresses correctness** (and, for an uplift lever, it clears the *differential*
   floor `weak_margin − strong_margin ≥ 0.20`, not a raw weak-model margin).

Anything that doesn't is cosmetic or harmful — which is exactly what W1 was, and exactly what
this whole apparatus exists to catch before it ships.

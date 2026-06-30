# Making agentic-cfg the best token-economy + performance layer for Claude Code

> A principal-engineer research review: 2026 state-of-the-art techniques for cutting token
> usage and improving model performance in Claude Code, mapped onto what agentic-cfg already
> does, with each recommendation framed as a **falsifiable hypothesis** for the
> [SWE benchmark](swe-benchmark-design.md). Companion docs:
> [current-design critique](current-design-critique.md) (keep/fix/drop) and the
> [improvement roadmap](improvement-roadmap.md) (prioritized).
>
> **Method & honesty.** Compiled June 2026 from a multi-agent research pass (web SOTA + a
> file-level audit of this repo + the repo's own measured data), then put through an
> adversarial verifier. Mechanisms and the headline Anthropic figures held up; the verifier's
> corrections (release-state, citation scope) are folded in as explicit caveats. **Numbers
> from a single vendor example are labelled as such — they are not typical savings.** No
> proposal here is asserted to *work*; that is what the benchmark is for.

## The one finding everything else hangs on

agentic-cfg already did the hardest and most valuable thing: it **built a measurement
instrument** ([`evals/overhead.py`](../../evals/overhead.py), the ON-vs-OFF ratio gate) and
used it to **falsify its own plausible fix**. Its own n=3 data
([`plans/06-overhead-and-uplift.md`](../../plans/06-overhead-and-uplift.md), all arms 100%
correct) is the load-bearing fact:

| model / config | trivial-easy | hard | hard2 |
|---|---:|---:|---:|
| Haiku, full | **3.15× (FAIL ≤1.5×)** | 0.65× | 1.00× |
| Haiku, weak-tier | **2.27× (FAIL)** | 0.93× | 1.00× |
| Opus 4.8, full | 1.00× | 0.99× | 1.34× |

Three things follow, and they reorder the whole improvement program:

1. **The toolset over-tools *weak models* on *trivial tasks*** — and *only* there. Opus never
   exceeds 1.34×; every hard task is ≤1.0× for everyone. The defect is **regime-specific**, so
   any fix must be evaluated per (model-tier × task-difficulty) cell, never on an average.
2. **The cost driver is turns, not prefix bytes.** Turn-1 always-on context is **1.00×** across
   arms (28,290 vs 28,327 tokens); the honestly-repriced input overhead is **1.25×**, not
   3.93×. The 3–4× headline is `turns × per-turn re-read` + output tokens (2.70×) — *induced
   behaviour*, dominated by ~95% `cache_read` that is priced ~0.1× (and flat-rate-unbilled on
   Max). **Trimming the ~11.1 KB prefix is cache hygiene, not the cost lever.**
3. **The over-tooling is driven by the environment, not the prompt.** The prompt-based triage
   gate (W1) moved nothing — "a CLAUDE.md instruction cannot override hooks that fire
   regardless of the prompt." The driver is the `lean-ctx` Read/Grep redirect hook + the
   always-loaded MCP + the tool-pushing prose.

So the high-leverage work is **environmental and per-turn** (gate/remove the turn-inducing tool
layer for the weak tier; adopt API-level context management) — *not* more prose, and not prose
trimming pursued as if it were the cost lever.

---

## Part A — Token reduction: state of the art vs. what the repo uses

### A.1 What the repo does today (assessment)

| Lever | Verdict | Why |
|---|---|---|
| Prefix **byte budget** + stability ([`bin/prefix-budget.sh`](../../bin/prefix-budget.sh), FAILs CI > 11,300 B) | **Keep** | Correct cache hygiene — stops silent prefix growth that inflates `cache_creation` every session. The right guard. |
| Always-on ~11.1 KB prefix **as the primary cost lever** | **Questionable** | It is identical ON vs OFF and ~95% `cache_read`; repriced overhead is 1.25×. Pursuing prose trimming as the headline token win is mis-prioritized. |
| `lean-ctx` Read/Grep **redirect hook** | **Fix/Drop (weak tier)** | On trivial weak-model tasks it *induces* the orientation dance it was meant to prevent — it adds turns, and turns are the cost. The single biggest measured contributor to 3.15×. |
| `AGENTIC_TIER=weak` profile | **Mixed** | Right *direction* (environmental), honestly reported as partial (3.15→2.27×, still FAIL). Stops short: keeps gitnexus MCP + tool-pushing prose. |
| `rtk` / `lean-ctx` shell+read compression | **Mixed** | Real on noisy output, but [`evals/BENCHMARKS.md`](../../evals/BENCHMARKS.md) stamps `rtk-economical-shell-output` **UNRELIABLE** on Opus (0/3 treatment wins). Keep, but don't over-claim. |
| Sub-agent context isolation (guidance) | **Keep** | Matches Anthropic's context-engineering guidance (workers return distilled summaries). It is *advice*, not wiring — see Part B. |
| Anthropic **context editing / tool-result clearing** | **Missing** | Not used anywhere in `providers/`/`integrations/`. Targets the exact failure mode (turns × tool-result re-read). |
| Anthropic **memory tool** | **Missing** | `lean-ctx` offers a memory-shaped surface (`ctx_knowledge`/`ctx_session`); the Anthropic-native memory tool is absent. |
| **Grammar-constrained structured outputs** | **Missing** | `answer-shapes` is an opt-in *prose* skeleton a weak model can ignore; schema enforcement is a hard guarantee where the runner owns the call. |

### A.2 The unused levers (SOTA, with verified caveats)

**Context editing — automatic tool-result clearing** *(largest unused lever for long agentic
sessions).* Anthropic's context-management API (beta header `context-management-2025-06-27`)
clears the oldest tool results once context crosses a trigger (defaults: trigger 100k tokens,
keep the last 3 tool uses, `clear_at_least`, a placeholder replaces cleared content). Anthropic's
own token-count **example** shows `original_input_tokens` 70,000 → `input_tokens` 25,000 — **a
64% reduction in that single illustrative example, not a guaranteed/typical figure.** It is not
settable in stock Claude Code today, but **any SDK/API-controlled runner can set it** — including
`evals/overhead.py` (which spawns `claude -p`) and a future agentic-cfg runner. This is exactly
the multi-turn, tool-result-accumulating case the repo benchmarks.
*Hypothesis (testable):* on a session that accumulates >30k tokens of tool results, enabling
tool-result clearing cuts `total_input_tokens` materially with no correctness regression.

**Memory tool** *(composes with context editing).* A file-backed, model-managed memory that
persists across the context window; **generally available** (the earlier "gated behind a beta
header" framing was wrong). It lets an agent write durable findings that survive clearing/
compaction. For long agentic SWE tasks this is where clearing-without-memory loses information.
Lower priority than clearing itself; they are designed to be used together. *(Do not state as a
fact that Claude is "warned to save before tool results are cleared" — that specific threshold
mechanism is not documented.)*

**Grammar-constrained structured outputs.** A 2025 Anthropic capability that constrains
generation to a supplied JSON schema, turning a *probabilistic* output format into a *hard
guarantee* and eliminating parse-failure re-asks. *(Treat exact beta-state and per-model support
as fast-moving — verify at the docs before pinning versions.)* Where agentic-cfg owns the API
call — e.g. an orchestrator delegating a well-specified extraction/review to a cheap subagent —
a schema is strictly better than the `answer-shapes` prose contract, which a weak model can
ignore. *Hypothesis:* a schema'd subagent hand-off drives format-driven re-ask turns to ~0,
beating `answer-shapes` on weak-executor reliability.

**Just-in-time retrieval, kept but made conditional.** Anthropic's context-engineering guidance
("the smallest possible set of high-signal tokens"; just-in-time loading; context rot) endorses
exactly `lean-ctx`'s philosophy. The fix is not to abandon JIT but to make the **redirect
conditional** (large/structural reads, or the strong tier only) instead of firing on *every*
`Read`/`Grep` — which the repo's data shows is the weak-model turn-inducer.

**Prompt-cache TTL & compaction-as-stable-prefix.** Standard prompt caching cuts repeated-prefix
cost substantially (Anthropic's published "up to ~90% cost / ~85% latency" is the launch-era
*best-case* on long prompts — not a guarantee). A 1-hour cache TTL helps *spaced* workloads
(it costs ~2× on write, so it only nets out after several reads — a loss for truly one-shot
runs). *(Do not attach the "41–80% cost / 13–31% TTFT" figures from the cited arXiv to "1h TTL"
specifically — those are general system-prompt caching results.)* The repo's `PreCompact` hook
currently only emits telemetry; it could additionally enforce a **byte-stable post-compaction
prefix** so the cache re-warms in one turn instead of paying full reprocessing each summary.

---

## Part B — Model performance: mechanical levers vs. nudges

The repo has an unusually mature *measurement* spine and **two genuinely mechanical levers**,
but most of its *quality* story is prose the data shows weak models ignore.

**What's mechanical (keep):**
- **`shell-guard` PreToolUse hook** — wraps shell with `rtk`, denies code-targeted `grep` and
  points at `ast-grep`, delegates to `lean-ctx`. A real, enforced behaviour, not a nudge.
- **`edit-lint` PostToolUse hook** — parse-checks `.py`/`.go`/`.js` after Edit/Write (fail-open)
  and injects a fix-it note. Mechanizes "don't ship code that doesn't parse."

**Measured case — mechanizing a discovery gate beat softening its prose (live, loop 29).** The
benchmark's weak-tier over-tooling turned out to be driven not by agentic-cfg but by an aggressive
*discovery-gate* hook in the live environment (a "use the graph MCP FIRST; index_repository if
needed" PreToolUse block on the first read of every session). On a 1–2 file task it forced a full
graph index + Cypher to answer what a direct read solves — ~12 wasted tool calls. Two fixes were
tried and measured on the same task:
- **Softening the prose** (the SessionStart reminder → "right-size; read small things directly")
  shifted behaviour only *probabilistically*: 1 of 4 Haiku runs skipped the graph, 3 of 4 still
  indexed. A live re-proof of W1 — prose moves a weak model but does not enforce.
- **Mechanizing it** (make the gate *skip the block when the working tree is < ~12 source files*)
  was decisive: **4 of 4 runs used zero graph calls, zero indexing, all correct**, while the gate
  still fires on real repos (verified on this 26-file checkout). 12 cbm calls → 0.

The transferable pattern: **any "MCP-first / discovery-gate" hook should be scoped by working-tree
size** (a `find | head -N` count is enough), so it never forces heavy structural tooling onto a
trivial task. This is the same mechanical-over-prose lesson, now with a fresh before/after number
behind it — and the strongest available evidence for the Stop-/plan-gate proposals below.

**What's a nudge (the gap):** `karpathy-guidelines`, `honesty`, `coding-principles`,
`verification-before-completion`, `model-orchestration`, `answer-shapes` are all prose — in the
always-on prefix or an on-demand skill. The repo *already proved* (W1 falsified) that prompt
nudges don't change weak-model behaviour. The highest-value performance work is to **mechanize
the few that matter**, as hooks, gated to where they help:

- **Stop-hook verification gate** — mechanize `verification-before-completion`: a `Stop` hook
  that blocks a "done / tests pass" claim with no verifying command output in the transcript.
  Today the `Stop` matcher only runs `lean-ctx hook observe`. Targets the top agentic failure
  mode (confident false "it works"). *Hypothesis — not a claim:* reduces false-completion on
  Haiku/Sonnet; **no existing eval demonstrates this yet** (all current arms are 100% correct —
  see Part C on the missing correctness suite).
- **Enforced plan-gate on first heavy-task edit** — a PreToolUse hook on the first `Edit` of a
  multi-file task that requires a stated plan (files + change + per-step check). Turns the
  karpathy "goal-driven execution" principle into a gate. Gate on a file-count/heaviness
  heuristic to avoid friction on small tasks.
- **Per-tier reasoning-effort defaults** — the `model-orchestration` skill documents the
  effort knob, but the **installer sets no effort default**. Extending the `AGENTIC_TIER`
  branch ([`install.sh`](../../providers/claude/install.sh)) to set low effort for the weak/
  trivial regime and high for hard/strong is a small, directly-measurable change — a *plausible*
  route toward the still-unmet ≤1.5× weak-easy bar (where tool-stripping alone stalled at
  2.27×). **Not asserted to reach it.**
- **Schema-enforced subagent hand-offs** (see Part A) and **conditional, hard-task-gated,
  weak-tier-only self-critique** (already designed as W4 step 3, unbuilt) — both bounded,
  both isolated to where they can't regress the easy band, both to be proven on the
  correctness suite before shipping.

> **Verifier caveats honored:** none of the Stop-gate / plan-gate / self-critique / effort
> proposals is stated to produce correctness gains — there is no eval in the repo that could
> show it, because every current task is solved by both arms. Building that eval (Part C) is the
> prerequisite. The "0.20 uplift floor" from ADR-0003/0006 is a **differential** floor
> (`weak_margin − strong_margin ≥ 0.20`), not a raw weak-model uplift threshold. No per-hook
> latency budget is claimed (Anthropic publishes none).

---

## Where this goes next

- The **keep/fix/drop verdicts** on every current method, grounded in the n=3 data:
  [current-design-critique.md](current-design-critique.md).
- The **prioritized, testable roadmap** (what to do, in what order, with the hypothesis and the
  benchmark cell that decides it): [improvement-roadmap.md](improvement-roadmap.md).
- The **instrument** that turns every hypothesis above into a pass/fail:
  [swe-benchmark-design.md](swe-benchmark-design.md) / [`evals/swe_bench.py`](../../evals/swe_bench.py).

The throughline: this repo's superpower is that it *measures and falsifies*. The improvement is
not a pile of new prose — it is **moving the few high-value levers from prose into enforced
mechanism, attacking turns and tool-result accumulation rather than prefix bytes, and proving
each one on a correctness benchmark the repo does not yet have.**

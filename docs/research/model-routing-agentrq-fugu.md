# External review — AgentRQ, Sakana Fugu, and the Fugusashi router

> Method: the repo's standing loop — **idea → measurer → measure → change → re-measure → commit** —
> with a gstack `office-hours` premise challenge in front of it. Four externally-suggested
> sources were studied in depth (one research agent each), scored against what agentic-cfg
> actually is, and filtered to a single change that this repo's own acceptance rule can judge.
> Every "could adopt" claim is checked against the repo's measured data, not vibes.

## TL;DR

All four sources are **INSPIRE-ONLY** — none ships a component a *configuration* repo (no model
serving, no training, no persistent server) can lift directly. The recurring SOTA idea across
three of them is **allocate compute by task difficulty / route by role**. Filtered through this
repo's own benchmark — which has measured **zero cross-tier correctness divergence** (Haiku 4.5
solves the deliberately-nasty `expert` probe 5/5) — the literal "add a model router" idea fails
its premise challenge. The actionable residue is the **reasoning-effort dial** (`claude -p
--effort`), which is roadmap item 4, needs no new dependency, and targets where the measured
waste actually is (over-thinking easy tasks, not picking the wrong model). That is the one
change taken into the measure→change loop below.

## The four sources, digested

### 1. Fugusashi router — `huggingface.co/eulogik/fugusashi-router` (MIT)

An "open-source alternative to Sakana's Fugu router." The entire artifact is a **385-float vector**
(`cmaes_weights.json`, 384 embedding weights + 1 bias) applied on top of `all-MiniLM-L6-v2`
(~22M-param sentence embedder, CPU-runnable). It has no neural network of its own — it is a tiny
linear head. Input: a prompt → MiniLM embedding → linear score → **a model name** from a fixed pool
of five OpenRouter models (reasoning / general / light / code / ultra-fast roles). Trained on
**20 preference samples** with CMA-ES (30 generations, population 16; `best_fitness ≈ 0.24`).

Claims (model card only): 85% in-distribution / 70% cold-start accuracy; ~4 ms routing latency
("25× faster than LLM-based routing"). No held-out benchmark.

**Verified defect (load-bearing):** the model card's own usage snippet computes `embedding @
weights[:384] + bias`, which with a flat 385-vector yields a **scalar**, then calls `np.argmax`
over five names — argmax of a scalar is always 0, so the documented code always returns the first
model. A real five-way linear router needs a 5×385 matrix; only a single 385-vector is published.
The reference implementation is mathematically inconsistent.

**Verdict: INSPIRE-ONLY.** The *recipe* — embed the task with a small encoder, apply a tiny learned
head, emit a tier — is a clean template for mechanizing a routing decision. The *weights* are
worthless here (20 samples, OpenRouter-model taxonomy with no Anthropic-tier mapping, broken
reference code), and adopting them would bolt a Python + sentence-transformers + torch stack onto a
Go/markdown/shell repo.

### 2. Sakana Fugu — `sakana.ai/fugu/` (proprietary API)

A family of **orchestrator models** ("A Multi-Agent System, Delivered as One Model") behind one
OpenAI-compatible endpoint. Fugu is *not* a merged model that answers directly — per the technical
report (arXiv 2606.21228, Jun 2026) the Fugu models are "language models trained to understand user
queries and dynamically devise **agentic scaffolds**," coordinating a pool of external frontier
LLMs. Two public research papers underpin it:

- **TRINITY** (arXiv 2512.04695): a compact coordinator (**~0.6B SLM + ~10K-param head**) runs up to
  five turns; at each turn it selects an LLM *and a role* — the head emits `L+3` logits = **L model
  choices + 3 role logits {Thinker, Worker, Verifier}** — conditioned on the full running transcript,
  sampled from a softmax policy optimized by separable CMA-ES. Pool of seven models. 86.2% on
  LiveCodeBench.
- **Conductor** (arXiv 2512.04388, ICLR 2026): a 7B RL-trained coordinator that learns natural-language
  agent-to-agent coordination topologies.

Product benchmarks (marketing page, **vendor-reported**, vs Opus 4.8): SWE-Bench Pro 59.0 / **73.7**
vs 69.2; TerminalBench 2.1 80.2 / 82.1 vs 74.6; LiveCodeBench 92.9 / 93.2 vs 87.8; GPQA-D 95.5 /
95.5 vs 92.0. The technical-report abstract claims only "state-of-the-art," not these numbers, and
the production router is **proprietary and undisclosed by design**. API only; no weights; $20/$100/$200
per month or $5-in/$30-out per 1M tokens PAYG; not available in the EU/EEA.

**Verdict: INSPIRE-ONLY.** Fugu is a serving/training product the repo cannot host. Its transferable
abstraction is the **role taxonomy (Thinker / Worker / Verifier) routed per-turn on transcript
state** — a sharper, citable framing of the `model-orchestration` skill's existing "plan strong,
execute cheap, verify, escalate" policy. The 0.6B/7B coordinators, the CMA-ES/RL training, and the
heterogeneous cross-vendor pool are all un-hostable here.

### 3. AgentRQ — `github.com/agentrq/agentrq` (Apache-2.0)

A self-hostable **human-in-the-loop realtime task manager for AI agents**, exposed over MCP
(Go/Fiber backend + Vue 3 UI, ~799 stars). Agents pull assigned tasks, update status, request
permissions, and chat with a human operator in real time. Mechanically it is a task-queue + MCP-server
+ SSE event-bus: a stateless supervisor MCP plus lazily-created per-workspace MCP servers (structural
isolation), task dequeue via `getTask()`, a **permission gate** (`auto-allow` / `allow` /
`allow_always` → persisted `AutoAllowedTools`), an in-memory EventBus (SSE) and internal PubSub, and
event-chaining that injects a deterministic completion instruction into the agent.

**Verdict: INSPIRE-ONLY.** Everything is welded to a stateful multi-agent server (per-workspace MCP
servers, SSE/PubSub, OAuth2/JWT, Postgres, cron) that a config repo should not grow. The one
durably-useful pattern — **approval-driven allowlist promotion** (`allow_always` learns a persisted
permission allowlist) — reinforces this repo's hook-over-prose thesis but is already substantially
covered by the `fewer-permission-prompts` skill, which mines session transcripts for common approvals
and writes a `settings.json` allowlist.

### 4. AgentRQ blog — `agentrq.com/blog/` (hosted SaaS)

The product's content marketing: a hosted oversight/notification plane so a human can supervise
unattended agents from a phone. Real proprietary mechanisms are MCP-transport plumbing — **notification
channels** (`notifications/claude/channel` over stdio, Claude Code v2.1.80+), supervisor/worker task
routing (to *workspaces*, not model tiers — explicitly no model routing), and open-source ACP/Codex
gateways. No product performance benchmarks exist (only a "60 seconds to connect" claim); the
"closed-loop" 113%/127%/143% improvement figures are explicitly rhetorical compounding arithmetic, and
every real benchmark number in the blog belongs to third-party model/hardware news (DeepSeek-V4,
TurboQuant, M5 Max, MolmoWeb).

**Verdict: INSPIRE-ONLY.** The only infra-free idea is an **autonomy-tiering rubric** — which actions
to auto-approve versus human-gate — which could ADAPT into a small skill/hook nudge. Every concrete
AgentRQ mechanism presupposes a hosted MCP/notification service the repo deliberately does not run.

## Office-hours synthesis

**Premise challenge — "build a model router like Fugu / fugusashi."** It fails on three independent
grounds, each fatal on its own:

1. **The execution model forbids it.** Claude Code runs **one model per session**; no PreToolUse or
   SessionStart hook can swap the running model mid-session. A router is actionable only at session
   launch (`--model`) or per delegated subagent — and the `model-orchestration` skill already covers
   the subagent case in prose.
2. **The repo's own data says there is nothing to learn.** Across the full live matrix every arm was
   100% correct, and the `expert` rung built specifically to break bare Haiku went **5/5**. With no
   measured task where a cheap tier fails and a strong tier succeeds, the optimal learned policy is
   "always cheapest" — a tier-router has essentially no signal to add for this workload.
3. **Cost/benefit is upside-down.** A MiniLM-embed router adds a Python + torch dependency to a
   Go/markdown/shell repo to mechanize a decision the data says is usually trivial.

**Q2 — the real status quo.** The competitor is not "no routing"; it is the existing
`model-orchestration` skill, which already encodes plan-strong / execute-cheap / verify / escalate —
i.e. Fugu's Thinker/Worker/Verifier roles — as a prose decision policy. The genuine gap versus the
SOTA sources is not *model* selection (the data closed that) but that the repo **never exploits the
reasoning-effort dial**, which is exactly where the measured waste lives: weak models over-thinking
easy tasks.

**Q4 — the narrowest wedge.** `claude -p` exposes `--effort <level>`. So the actionable core of
"allocate compute by difficulty" (the one idea common to Fugu and fugusashi) reduces, for this repo,
to a measurable question: **does lower effort cut tokens on easy tasks without losing correctness,
and does higher effort earn its cost anywhere?** That is roadmap item 4, needs no dependency, and is
judgeable by the existing benchmark with a one-flag change.

## The change under test

Instrument first: `evals/swe_bench.py` gained an `--effort` axis (threads `--effort` into the
`claude -p` launch argv; covered by the zero-token selftest). The measurer compares the **bare (OFF)
arm** of Haiku across effort levels, isolating the reasoning-effort effect from the config effect.

## Measured result

Haiku, bare (OFF) and configured (ON) arms, reps=3, `claude -p --effort low` vs `high`
([raw data](../../plans/data/swe-bench-effort-2026-06-30.jsonl)):

| tier | effort | OFF: correct / turns / total-in / cost | ON: correct / turns / total-in / cost |
|------|--------|----------------------------------------|----------------------------------------|
| trivial | low  | 100% / 2 / 60.6k / $0.0534 | 100% / 2 / 60.5k / $0.0530 |
| trivial | high | 100% / 2 / 60.6k / $0.0537 | 100% / 2 / 60.5k / $0.0532 |
| easy    | low  | 100% / 6 / 159.9k / $0.0705 | 100% / 10 / 296.8k / $0.0903 |
| easy    | high | 100% / 5 / 94.1k / $0.0626 | 100% / 12 / 380.0k / $0.1045 |

**The effort dial is not a measurable lever for Haiku on these tiers — a null result.**

1. **Correctness: untouched.** 100% across all eight arm×effort combinations. Effort moves it nowhere
   (consistent with the repo's standing finding that Haiku 4.5 does not fail these tasks unaided).
2. **`trivial`: an exact no-op.** Low and high are identical to the dollar (2 turns, ~60.5k, ~$0.053).
   Haiku spends no reasoning budget here regardless of the dial.
3. **`easy`: noise, not signal.** The two arms **disagree on the sign** of the effort effect — on the
   bare arm high effort looked *cheaper* (−41% total-input, −17% turns), on the configured arm high
   looked *costlier* (+28% total-input, +20% turns). When the same comparison flips direction between
   arms on a tier already known to swing wildly (this repo measured `easy` ratios move 2.62×→1.31×
   across reps), the effect is indistinguishable from run-to-run variance at n=3.

**Mechanistic reading.** Haiku's cost on `easy` is dominated by **tool turns** (the configured arm runs
10–12 turns vs the bare arm's 5–6), not by reasoning tokens — so a *reasoning*-effort knob has almost
nothing to bite on. This is the same lesson the session's cbm-gate result taught from the other side:
the lever that measurably moved Haiku was difficulty-aware **tool-gating** (12 graph calls → 0), not
effort and not model choice.

## What this does and does not license

**Ships (this commit):**

- **The instrument** — the `--effort` axis on `evals/swe_bench.py` (selftest-covered). It is reusable:
  any future effort question (a harder tier, a stronger model, a reasoning-bound task) can now be
  measured, not asserted.
- **The knowledge** — this review, and a roadmap update marking item 4 (per-tier effort defaults)
  **tested and null for Haiku × {trivial, easy}**.
- **One adopted idea** — Fugu/TRINITY's **Thinker / Worker / Verifier** role taxonomy, folded into the
  `model-orchestration` skill as the name for its existing plan→execute→verify pattern, plus the
  measured effort caveat correcting the skill's prior "effort is often a cheaper lever" claim for the
  tool-bound weak-model case.

**Does NOT license:**

- **A per-tier reasoning-effort default** (roadmap item 4) — the data shows it would be cosmetic on
  these tiers (no correctness, no consistent cost effect). The acceptance rule blocks it. It stays open
  only for a *reasoning-bound* regime, which this experiment did not cover.
- **A model router** (fugusashi / Fugu style) — killed by the premise challenge above: one model per
  session, zero measured cross-tier correctness divergence to learn from, and a heavy dependency for a
  decision the data says is trivial.
- **Any AgentRQ mechanism** — all require a hosted multi-agent server the repo deliberately does not run.

**Caveat on this experiment.** n=3, single task instance per cell, Haiku only, `trivial`+`easy` only.
The `easy` effort deltas are explicitly not trustworthy (the arms' sign disagreement is the evidence).
The clean, repeatable finding is the `trivial` no-op and the universal 100% correctness; the `easy`
numbers are reported with their noise, not as a ratio to bank.

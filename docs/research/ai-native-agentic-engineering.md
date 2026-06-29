# How AI-native companies do model orchestration & token efficiency

A reviewed, cited snapshot of how the leading agentic-coding shops — **Anthropic, OpenAI,
Google, and Cursor** — actually divide work across model tiers and keep the token bill down,
plus the vendor-neutral patterns they converge on. It exists to ground this repo's
[`model-orchestration`](../../core/skills/model-orchestration/SKILL.md) skill in evidence
rather than vibes.

> **Freshness & confidence.** Compiled June 2026 from primary sources (vendor engineering
> blogs and docs), then fact-checked by a separate adversarial pass; claims that couldn't be
> confirmed were dropped or hedged. The product/model landscape moves fast — **exact model
> names, prices, and limits drift monthly**, so this doc routes by *tier* and marks specific
> figures as "up to" where the source did. Verify numbers at the linked source before
> quoting them.

## The big picture — what everyone agrees on

Despite different products, the four companies have converged on the same playbook:

1. **Start simple; escalate only when measured.** Begin with one well-prompted model; add
   workflows, multi-agent orchestration, or a bigger model only when evals show the simple
   thing falls short. Stated almost identically by Anthropic ("add complexity only when
   simpler solutions fall short") and OpenAI ("maximize a single agent first").
2. **Tier the model to the task.** A strong model plans, decomposes, and reviews; cheaper/
   faster models execute well-specified sub-tasks; you escalate on failure. Every vendor
   ships an explicit cheap tier (Haiku / mini-nano / Flash-Lite / Composer) for exactly this.
3. **One effort knob, not just model-switching.** Each now exposes a *reasoning-effort* /
   *thinking-level* dial so a single model can serve cheap and deep workloads — often a finer
   lever than swapping models.
4. **Context engineering is the token game.** Curate the smallest high-signal context;
   isolate verbose work in sub-agents that return summaries; cache the stable prefix;
   retrieve instead of stuffing. Token usage is the dominant cost *and* quality variable.
5. **Multi-agent is powerful but expensive** — reserve it for high-value, parallelizable work.

The rest of this doc is the evidence behind each.

## Anthropic

**Tiering & orchestration.** Anthropic's *Building effective agents* essay is the canonical
taxonomy: it separates **workflows** ("LLMs and tools orchestrated through predefined code
paths") from **agents** ("LLMs dynamically direct their own processes and tool usage"), and
codifies five reusable patterns — **prompt chaining, routing, parallelization
(sectioning/voting), orchestrator-workers, and evaluator-optimizer**. Its routing example
*is* model-tiering: send easy/common inputs to a small cheap model and hard/unusual inputs to
a more capable one.

The flagship demonstration is Anthropic's own multi-agent **Research** system: a lead agent
plans and spawns **3–5 parallel sub-agents** that act as intelligent filters and return
condensed findings. Anthropic reports the lead-plus-subagents configuration "outperformed
single-agent Claude Opus 4 by **90.2%** on our internal research eval" — but also that
"agents typically use about **4×** more tokens than chat interactions, and multi-agent
systems use about **15×** more tokens than chats," with **token usage alone explaining ~80%**
of performance variance. The lesson the orchestration skill borrows: *orchestrate only when
the task value justifies a 15× token bill.*

The cheap tier is explicit. On the Haiku release: "Sonnet … can break down a complex problem
into multi-step plans, then orchestrate a team of multiple **Haiku**s to complete subtasks in
parallel." Docs list "sub-agent tasks" as a primary Haiku use case. (The current top tier has
moved beyond Opus 4.8 in the live model picker; route by tier — *frontier / balanced / cheap*
— and let `/model` pick the concrete name.)

**Token efficiency.** Three named levers:
- **Prompt caching** — "reducing costs by **up to 90%** and latency by **up to 85%** for long
  prompts"; cache reads bill at ~10% of base input.
- **Context engineering** — "find the smallest possible set of high-signal tokens," motivated
  by *context rot* (accuracy degrades as the window fills against a finite attention budget).
  For long horizons: **compaction**, **structured note-taking/memory**, and **sub-agent
  isolation**.
- **Effort tuning** — "tuning effort is often a better lever than switching models."

**Productized.** Claude Code **subagents** implement orchestrator-workers locally: each runs
in its own context window with a custom prompt, restricted tools, and a **configurable
model** (the built-in `Explore` runs on a cheap fast tier; `Plan` inherits the main model);
forked subagents reuse the parent's prompt cache. The Claude Agent SDK exposes the same loop
for building these in code.

Sources: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) ·
[Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (2025-06) ·
[Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (2025-09) ·
[Prompt caching](https://www.anthropic.com/news/prompt-caching) ·
[Claude Code subagents](https://code.claude.com/docs/en/sub-agents) ·
[Choosing a model](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model)

## OpenAI

**Tiering & orchestration.** OpenAI fields a frontier coding/reasoning model plus
progressively cheaper variants and **mini/nano** tiers explicitly "for tasks where speed and
cost matter most like classification, data extraction, ranking, and **sub-agents**." Its
official model-selection method is **optimize-down**: "Optimize for accuracy first … then
maintain accuracy with the cheapest, fastest model possible." A single **`reasoning.effort`**
control (values are model-dependent; recent models add `none` and `xhigh`) tunes thinking,
and "**higher reasoning effort isn't automatically better**" — high effort on weakly-specified
tasks causes overthinking. A separate `text.verbosity` knob trims output length independently.

The **Agents SDK** offers two orchestration shapes — a code-owned **Manager** (agents-as-
tools, the manager keeps the reply) and decentralized **Handoffs** (control transfers to a
specialist via `transfer_to_<agent>` tools) — with the standing advice to "**start with one
agent**." **Guardrails** run input/output checks with tripwires, designed to use a cheap fast
model to halt bad requests *before* the expensive agent runs.

**Codex** is the agentic-coding product across a local CLI, a parallel **cloud** environment,
and an IDE extension; the guidance is to "treat Codex like a teammate with explicit context
and a clear definition of 'done'" — plan/verify in the tight local loop, delegate long
implementations to background cloud tasks.

**Token efficiency.** **Automatic prompt caching** gives "**up to 90%** cheaper cached input
tokens" with no cache-write fee (place static content first, variable content last, ≥1024-
token prefixes). The **Responses API** can persist reasoning across turns (chain via
`previous_response_id`) so chain-of-thought isn't re-billed and cache utilization improves.
Reasoning tokens are billed as (hidden) output tokens and discarded between turns by default.

Sources: [Models](https://developers.openai.com/api/docs/models) ·
[Model selection](https://developers.openai.com/api/docs/guides/model-selection) ·
[Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model) ·
[A practical guide to building agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) ·
[Agents SDK handoffs](https://openai.github.io/openai-agents-python/handoffs/) ·
[Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)

## Google

**Tiering & orchestration.** Google tiers the **Gemini** family into **Pro** (deep reasoning/
agentic coding), **Flash** (fast, frontier-class), and **Flash-Lite** (budget high-volume),
with the cheap-vs-deep split visible in pricing (Flash-Lite output is several-fold cheaper
than Pro). A unified **thinking-level** control (low/medium/high; numeric `thinking_budget`
still supported) trades reasoning depth for cost, since thinking tokens bill as output.
Google markets Flash as delivering "Pro-grade reasoning with Flash-level latency, efficiency
and cost" — using materially fewer tokens than the prior Pro on everyday tasks.

Uniquely, Google ships a **managed cost router**: the **Vertex AI Model Optimizer** is "a
single meta-endpoint that auto-selects the best Gemini model per request" via a quality-vs-
cost preference (`PRIORITIZE_QUALITY` / `BALANCED` / `PRIORITIZE_COST`) — routing in the
platform instead of app code.

**Agentic coding** consolidated in 2026: **Gemini CLI** (open-source) is being folded into
the Go-based **Antigravity CLI**; **Antigravity** is an agent-first platform centered on
parallel multi-agent orchestration; **Jules** is an async coding agent that runs in an
isolated cloud VM, plans before acting, and returns reviewable GitHub PRs; the Gemini API
added **Managed Agents** ("a single API call … spins up an agent that reasons, uses tools and
executes code in an isolated Linux environment"). The open-source **Agent Development Kit
(ADK)** provides sequential/parallel/loop/hierarchical (coordinator-dispatcher) orchestration
and is model-agnostic — assign cheap models to workers, a stronger one to the coordinator.

**Token efficiency.** The **1M-token context window** plus **context caching** is the
strategy: **implicit caching** is automatic (no storage fee) and **explicit caching** manages
reusable cache objects (hourly storage fee). Cached-input discounts are large (on the order of
75% on the 2.5 generation, higher on newer ones). The signature move: **load a whole repo
once and cache it**, so every subsequent agent turn reads context at the cached rate.

Sources: [Gemini caching](https://ai.google.dev/gemini-api/docs/caching) ·
[Vertex AI Model Optimizer](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/vertex-ai-model-optimizer) ·
[Antigravity](https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/) ·
[Jules](https://blog.google/innovation-and-ai/models-and-research/google-labs/jules/) ·
[ADK](https://adk.dev/) ·
[I/O 2026 highlights](https://blog.google/innovation-and-ai/technology/developers-tools/google-io-2026-developer-highlights/)

## Cursor (Anysphere)

**Tiering & orchestration.** Cursor's 2025–26 shift is notable: alongside orchestrating
third-party frontier models, it **trained its own** model family, **Composer** — a
mixture-of-experts model trained with reinforcement learning *inside the real Cursor agent
harness* (semantic search, grep, edit, terminal). Cursor reports (vendor self-report)
Composer generates **~4× faster** than similarly intelligent models, finishing most agent
turns under 30s. Orchestration centers on an **"Auto"** router that "balance[s] intelligence,
cost efficiency, and reliability" for everyday tasks — billed from a cheaper included-usage
pool than named frontier models, a deliberate strong-vs-cheap tradeoff. **Plan Mode**
separates planning from execution: the agent researches, asks clarifying questions, and
produces an editable plan you approve before any code is written. **Cursor 2.0** added a
multi-agent interface to run many agents in parallel (git worktrees or remote VMs), including
racing several models on one problem (best-of-N).

**Token / context efficiency.**
- **Codebase indexing** — chunk code, embed it, store obfuscated vectors remotely, **re-embed
  only changed files** (Merkle-tree change detection); retrieve relevant chunks at query time
  instead of dumping the repo.
- **Scoped context** — `@`-mentions (`@Files`, `@Docs`, `@Branch`, …) and a **rules** system
  (`.cursor/rules`, user/team rules, `AGENTS.md`) with four application modes inject only
  relevant instructions; docs advise rules kept "under 500 lines … added only when the agent
  repeats a mistake."
- **Fast-apply / speculative edits** — a planner/applier split: the strong model emits a
  compact edit instruction; a cheaper fine-tuned model rewrites the file via deterministic
  speculative decoding at ~1000 tokens/sec.
- **Background/cloud agents** run in isolated remote VMs on their own branch, billed
  separately — offloading long work from the interactive session.

Sources: [Cursor 2.0](https://cursor.com/blog/2-0) ·
[Composer](https://cursor.com/blog/composer) ·
[Models](https://cursor.com/docs/models) ·
[Codebase indexing](https://cursor.com/docs/context/codebase-indexing) ·
[Rules](https://cursor.com/docs/context/rules) ·
[Plan Mode](https://cursor.com/docs/agent/planning) ·
[Fast apply](https://cursor.com/blog/instant-apply)

## The vendor-neutral pattern catalog

Convergent across Anthropic's essay, OpenAI's agents guide, LangGraph/LangChain, and the
[12-factor-agents](https://github.com/humanlayer/12-factor-agents) community:

### Orchestration patterns
| Pattern | What | When |
|---|---|---|
| **Router (model-tiering)** | Classify each task/step and dispatch to the cheapest model that can handle it; treat routing as a *per-step* decision | Mixed traffic with distinct difficulty bands |
| **Orchestrator-workers** | A strong lead decomposes an open-ended task and spawns workers (often cheaper), then synthesizes | Open-ended tasks whose sub-tasks you can't predict |
| **Evaluator-optimizer** | Generator LLM + evaluator LLM loop until criteria pass; evaluator can be cheaper | Clear eval criteria + iterative refinement pays |
| **LLM-as-judge** | A model with a fixed rubric scores/accepts outputs and gates escalation | Automated quality gate; deciding stop/retry/escalate |
| **Escalate-on-failure** | Run on a cheap tier first; on a failed verifier/test/schema check, retry one tier up | Capture cheap-execution savings, preserve strong-model success rate |

The community consensus (incl. practitioner reports and Simon Willison, who moved from
skeptic to "sold on multi-agent … where task value justifies cost") is blunt: **a single
agent with the right tools and context matches or beats multi-agent on most tasks**, and
multi-agent adds large latency/cost overhead. Orchestrate when the task **fans out into
independent, well-specified pieces** — not by default.

### Token-economy techniques
| Technique | Benefit |
|---|---|
| **Prompt caching** of static prefixes | Up to ~90% input-cost / ~85% latency reduction on cached prefixes; compounds across agent loops |
| **Context compaction / summarization** | Bounds token growth over long horizons; avoids "lost in the middle" degradation |
| **Sub-agent context isolation** | Verbose work stays out of the main window; system processes more total info than one window holds |
| **Structured outputs (schema-constrained)** | Kills reparse/repair round-trips; makes routing/escalation machine-checkable |
| **Retrieval over context-stuffing** | Targeted context per turn → lower input cost *and* higher relevance/accuracy |
| **Effort/thinking-level tuning** | Cheaper than model-switching for the same model; cut reasoning tokens on easy work |
| **Write less code (YAGNI / minimalism)** | The cheapest tokens are never generated — the [`ponytail`](../../catalog/plugins.yaml) lever |

## What this means for `agentic-cfg`

The skill and this repo apply the above at config altitude, not as a runtime service:

- **Route by tier** — the [`model-orchestration`](../../core/skills/model-orchestration/SKILL.md)
  skill encodes strong-plan / cheap-execute / escalate-on-failure, by *task shape* so it
  survives model renames.
- **Cache the prefix** — [`prompt-caching-playbook`](../../core/skills/prompt-caching-playbook/SKILL.md)
  and the [byte-budgeted always-on layer](../../bin/prefix-budget.sh) keep the stable prefix
  small and cacheable.
- **Isolate + structure hand-offs** — subagents for verbose work; [`answer-shapes`](../../core/skills/answer-shapes/SKILL.md)
  for parseable plan→execute hand-offs.
- **Write less** — `ponytail` catalogued as the minimalism lever.

## See also

- Practitioner habits drawn from these sources: [AI for software engineering](../guides/ai-for-software-engineering.md).
- The scope rationale (office-hours session): [model-orchestration-office-hours.md](../design/model-orchestration-office-hours.md).

---
name: model-orchestration
description: Route each sub-task to the cheapest model tier that can do it well, and delegate execution to subagents. Apply when planning a multi-step or token-expensive task, choosing between strong/mid/cheap models (Opus/Sonnet/Haiku), deciding whether to spawn subagents, or when the user mentions cost, tokens, latency, or orchestration. Plan and decide with a strong model; execute well-specified sub-tasks with a cheap one; escalate on failure. Skip for a single trivial step — orchestration has overhead.
---

# Model orchestration

Match **model tier to task weight**, the same way the tool-precedence gate matches tool
weight to task weight. A strong model earns its cost on judgement — planning, decomposition,
ambiguous design, review. A cheap model is faster and far cheaper on well-specified
mechanical work — applying an agreed edit, renaming, boilerplate, search. Spending a
frontier model on a one-line rename is waste; spending a cheap model on an architecture call
is a bug. Route deliberately.

This is a **decision policy**, not a framework. It costs nothing until it fires.

## Tiers (route by shape, not by brand)

Think in three tiers so the policy survives model renames. Today's mapping:

| Tier | Role | Claude | Use for |
|------|------|--------|---------|
| **Strong** | Plan / decide / review | Opus | Decomposition, ambiguous or high-blast-radius design, final review, hard debugging, judging another model's output |
| **Mid** | General execution | Sonnet | Most day-to-day coding, multi-file edits with a clear spec, focused debugging |
| **Cheap** | Bulk / mechanical | Haiku | Well-specified single-file edits, renames, boilerplate, formatting, extraction, search, summarizing a file, draft commit messages |

Other providers tier the same way (GPT-5 / mini / nano; Gemini Pro / Flash / Flash-Lite).
Route by the task's *shape*; let the harness or `/model` pick the concrete model.

## Effort before model-switch

Switching tier is not the only knob. Modern models expose a **reasoning-effort / thinking-level**
dial (Claude effort low→max; GPT-5 `reasoning.effort`; Gemini thinking level), and tuning it is
often a finer, cheaper lever than changing model:

- **Lower** effort (or `none`) for easy, well-specified, latency-sensitive work — it cuts billed
  reasoning tokens without dropping a tier.
- **Higher** effort only for genuinely hard reasoning; more is *not* automatically better — on a
  weakly-specified task high effort causes overthinking and wasted tokens.

So the ladder is **right effort → right tier → orchestration**: reach for the next lever only
when the cheaper one is exhausted.

## The default pattern: plan strong, execute cheap, escalate on failure

1. **Plan with the strong tier.** Decompose the task into sub-tasks each small enough to
   hand off with an unambiguous spec: the file(s), the exact change, and a verifiable
   success check. A vague hand-off ("make it work") forces the executor to re-plan and
   burns the savings — a precise one (a written diff intent + the command that proves it)
   lets a cheap model finish independently. Pair this with `answer-shapes` so hand-offs are
   parseable.
2. **Execute with the cheapest capable tier.** Delegate each well-specified sub-task to a
   subagent (the `Agent`/Task tool, or a cheaper `/model`). Subagents also **isolate
   context** — the executor's intermediate reads never enter the planner's window, which is
   itself a large token saving on long tasks.
3. **Verify, then escalate only on failure.** Check the result (`verification-before-completion`).
   If a cheap tier fails the check twice, escalate that sub-task one tier up — do not loop a
   weak model on a problem above its weight. Escalation is the exception, not the plan.

## When NOT to orchestrate

Orchestration has real overhead — a planning round, hand-off tokens, subagent spin-up.
A single capable model in one context often wins. **Stay single-model when:**

- The whole task is one or two steps, or fits comfortably in one context.
- The work is exploratory/ambiguous throughout (no stable spec to hand off) — keep it with
  the strong tier rather than thrashing a cheap one.
- Splitting would duplicate context across agents that all need the same large file set.
- **The task value can't justify the overhead.** A single agent can use ~4× the tokens of a
  chat and a multi-agent run ~15× — reserve fan-out for high-value, parallelizable tasks, not
  routine edits (figures: [research doc](../../../docs/research/ai-native-agentic-engineering.md)).

Rule of thumb: orchestrate when the task **fans out into independent, well-specified
pieces**. If you can't write the sub-task spec in two sentences, it isn't ready to delegate.

## Token economy (independent of tiering)

These cut the bill whatever model you are on — apply them first; they often remove the need
to orchestrate at all:

- **Cache the stable prefix.** Keep instructions/system/context order stable so the prompt
  cache hits. See `prompt-caching-playbook`.
- **Isolate context in subagents.** Hand a subagent only what its sub-task needs; return a
  short structured result, not the transcript.
- **Retrieve, don't stuff.** Pull the relevant code via the structural/search tools
  (`gitnexus-navigation`, `ast-grep`) instead of pasting whole files into context.
- **Structured hand-offs.** `answer-shapes` skeletons make a cheap model's output complete
  and an orchestrator's parsing trivial — fewer correction round-trips.
- **Write less code.** The cheapest tokens are the ones never generated. The `ponytail`
  plugin (catalogued in `catalog/plugins.yaml`) enforces a do-less decision ladder before
  implementing — measured materially less generated code.

## Composes with

| Pair with | For |
|-----------|-----|
| `answer-shapes` | Parseable plan → execute hand-offs |
| `prompt-caching-playbook` | Keeping the cache warm across the orchestration |
| `verification-before-completion` | The gate that decides escalate-or-done |
| `gitnexus-navigation` / `ast-grep` | Retrieval over context-stuffing |

## Anti-patterns

- Spawning subagents for a task that fits in one context (overhead > savings).
- Delegating an under-specified sub-task, then paying to re-plan it.
- Looping a cheap model on a problem above its tier instead of escalating once.
- Using a frontier model for bulk mechanical edits a cheap tier would nail.
- Splitting a task so finely that every subagent re-reads the same large files.

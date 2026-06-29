# Office-hours design session — model orchestration & token economy

> Method: the [gstack `office-hours`](https://github.com/DietrichGebert/gstack) skill — six
> forcing questions that pressure-test an idea before any code is written. This is a
> **pure-engineering/infra** change, so per the skill's smart-routing table we run **Q2
> (status quo)** and **Q4 (narrowest wedge)**, plus a premise challenge. Captured here so
> the scope decision is auditable, not vibes.

## The ask

> "Cardinal performance boost for the models (Haiku, Opus, Sonnet) — more work, fewer
> tokens. Use orchestration: a smarter model for decisions and planning, a cheaper model
> for simple implementation."

A good instinct. The job of this session is to turn it into the *narrowest* thing that
actually moves the needle in **this** repo — not a framework nobody asked for.

## Premise challenge

The request says "make the models faster/cheaper." But this repo does not run models. It
is a **configuration source of truth** — it authors skills, principles, instructions, and
MCP wiring, then renders them into `~/.cursor/*` and `~/.claude/*`. So the lever here is
**not** a runtime orchestrator (a service that calls Opus then hands off to Haiku); it is
the **decision layer** the agent reads: *when to plan with a strong model, when to delegate
a well-specified subtask to a cheaper one, and when to escalate.*

Reframed premise we will actually build against:

> Give any agent driving this config a cheap-to-load, evidence-based **routing policy**:
> match model tier to task weight, delegate execution via subagents, and keep the
> token bill down — without inflating the always-on prefix the repo has worked to shrink.

## Q2 — Status quo (the real competitor)

The status quo is not "no token discipline." This repo already fights the token bill on
several fronts, and the orchestration idea competes with *those*, not with nothing:

| Existing lever | Where | What it already does |
|---|---|---|
| Right-size-the-tooling triage gate | `core/instructions/AGENTS.md` (W1) | Suppresses heavy tooling for trivial lookups |
| Prefix economy + byte-budget guard | `bin/prefix-budget.sh` (W2) | Caps the always-on layer at 11,300 bytes |
| Token-cheap weak-model uplift | `answer-shapes` skill + `edit-lint` hook (W4) | Makes a weak model's output complete/parseable |
| `AGENTIC_TIER=weak` install profile | `providers/*` (W5) | Environmental lever for minimal-tier models |
| Prompt-cache discipline | `prompt-caching-playbook` skill | Maximizes cache-hit rate to cut cost |

**What is genuinely missing:** an explicit **model-tier routing policy**. Today the config
tells the agent *which tool* to reach for, but never *which model* should own a sub-task,
nor *how to delegate execution to a cheaper tier*. That is the gap — and it is the part of
the user's ask that nothing here covers yet.

Verdict: the wedge is real. It is additive to the existing levers, not a duplicate.

## Q4 — Narrowest wedge (ship this week, not a platform)

The temptation is to build a "model orchestration framework." Resist it. The narrowest
version that delivers the value:

1. **One on-demand skill** — `core/skills/model-orchestration/SKILL.md` — carrying the
   routing table (task-shape → model tier) and the plan-strong / execute-cheap delegation
   pattern via subagents. On-demand = **zero always-on token cost** (loads only when it
   fires, like `answer-shapes`).
2. **A one-line pointer** in `AGENTS.md` so the agent knows the skill exists — kept under
   the prefix budget (only ~300 bytes of headroom; an always-on *principle* would blow it
   and *work against* the token goal, so we deliberately do **not** add one).
3. **Catalog `ponytail`** (code-minimalism plugin, measured ~54% less code / ~20% cheaper)
   in `catalog/plugins.yaml` — a free, drop-in token win that reinforces the same thesis.
4. **The docs the user asked for**: a cited review of how Cursor / Anthropic / Google /
   OpenAI actually do this, and two practitioner guides (AI for software engineering; AI in
   daily life).

Explicitly **out of scope** (architecture attachment, not value): a runtime router binary,
a model-cost telemetry pipeline, per-provider auto-switching code. The repo's model is
"author here, render to providers" — a runtime orchestrator does not fit and nobody asked
for it.

## Bonus push — value with zero user effort

The cheapest win requires the user to do *nothing*: cataloging `ponytail` and shipping the
skill means the next agent session inherits the policy automatically through the normal
install render. No new workflow to learn.

## The "fewer tokens" honesty check

A routing *skill* costs tokens only when it fires. The one risk is the AGENTS.md pointer,
which is always-on. So the binding success criterion is mechanical:

- **`bin/prefix-budget.sh` must still pass** after the AGENTS.md edit (≤ 11,300 bytes).

If we cannot add the pointer within budget, we trim or drop it rather than raise the cap —
raising the always-on cost to advertise a token-saving skill would be self-defeating.

## Success criteria

1. `model-orchestration` skill exists, on-demand, with a concrete routing table and a
   delegation pattern — covered by ≥1 eval case (CI coverage gate).
2. `bin/prefix-budget.sh` still passes (always-on layer did not grow past budget).
3. `bin/ci-check.sh` green (shell, JSON, YAML, frontmatter, evals lint/selftest, budget).
4. `bin/install.sh --dry-run` renders cleanly; `bin/doctor.sh` healthy.
5. `ponytail` catalogued (not vendored).
6. Research doc + two guides land under `docs/`, cited and dated.

## Future-fit note (Q6, optional, answered briefly)

Does this get *more* useful as models change? Yes: as the tier spread widens (frontier
planners vs. near-free executors) the value of an explicit routing policy grows, and the
skill is the natural home to keep the heuristics current. It does not bet on any one
vendor's model names — it routes by **task shape**, which is durable.

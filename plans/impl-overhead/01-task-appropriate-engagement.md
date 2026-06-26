# W1 — Task-appropriate engagement (stop over-tooling easy tasks)

> Parent: [../06-overhead-and-uplift.md](../06-overhead-and-uplift.md). Relates to ADR-0005
> (routing/effort/single-threaded) on branch `722d6e2`.

## Goal

Make the always-on guidance **right-size tool weight to task weight**. This is the
single biggest lever on the easy-task overhead and is nearly free in tokens.

## Evidence (why this is #1)

On the easy lookup task the toolset drove Haiku to **12 turns / 10 tool calls** to reach
the same answer a bare agent reached in **4 / 3** — `total_input` 3.93×, cost 2.04×, same
correct answer ([../data/haiku-overhead-2026-06-26.json](../data/haiku-overhead-2026-06-26.json)).
The cause is structural: the always-on **Tool precedence** table in
[`core/instructions/AGENTS.md`](../../core/instructions/AGENTS.md) (rendered into
`~/.claude/CLAUDE.md`) reads as an unconditional ladder — "1st choice GitNexus, 2nd
`ctx_semantic_search`…" — for *every* action regardless of task size. A weak model takes
that literally and orients/semantic-searches/structurally-navigates a one-line grep.

## Root cause

The precedence rules answer "which tool for this *class of action*" but never "does this
task warrant the heavy path at all". There is no triage gate and no stop condition.

## Changes (concrete)

1. **Add a triage gate above the precedence table** in `core/instructions/AGENTS.md`
   (`## Tool precedence` section). One compact block, e.g.:

   > **Right-size the tooling.** Match tool weight to task weight. For a single-fact
   > lookup (one symbol, one file, a literal string, "does X exist") use the **one
   > lightest tool** that answers it and stop — do not orient, semantic-search, or build
   > a graph first. Escalate to GitNexus / lean-ctx orientation / semantic search only
   > for genuinely multi-step, structural, or high-blast-radius work (3+ coupled files,
   > "who calls / impact", ambiguous scope). When in doubt, start light; escalate only if
   > the light tool is insufficient.

2. **Reframe the precedence table caption** from a prescriptive ladder to a conditional:
   "*When you need this class of action*, prefer in this order" — so the table stops
   reading as "always run the 1st choice".

3. **Add an explicit stop condition** to the precedence rules: "Once you can answer,
   answer. Do not run additional tools to confirm what you already know."

4. **Byte-neutral authoring (ties to [W2](02-prefix-economy.md)).** Fund the new block by
   trimming the now-redundant precedence prose (the per-row "Rules:" bullets restate the
   table). Net change to the always-on prefix must be **≤ 0 bytes** — verified by the W2
   byte budget. The point is to *redirect* the existing guidance, not add to it.

5. **(Optional, defer) routing skill.** If ADR-0005's `core/skills/model-routing/SKILL.md`
   is adopted, the heavy/triage detail moves there (loaded on demand) and AGENTS.md keeps
   only the one-line gate — strictly better for the prefix. Sequence after W2.

## Validation (success criteria)

Built on the [W3](03-overhead-kpi-and-gate.md) instrument:

- **Easy regime:** re-run the easy-task A/B; require `total_input(ON)/total_input(OFF) ≤ 1.5`
  and `tool_calls(ON) ≤ tool_calls(OFF) + 1`, with the answer still correct.
- **Hard regime (no-regression guard):** re-run the hard-task A/B; require
  `total_input(ON)/total_input(OFF) ≤ 1.0` still holds (today 0.72×) — the triage rule
  must not make the toolset *under*-engage where the heavy path is warranted.
- **Conformance case:** new `evals/conformance/cases/triage-light-tool-for-lookup.json`
  — a trivial lookup prompt; pass = the trajectory uses a light/direct tool and does not
  open with `ctx_overview`/semantic-search/gitnexus. (Trajectory check per ADR-0003.)
- **Adoption (ADR-0007):** the existing skills (rtk/ast-grep/etc.) still fire on the
  tasks that warrant them — triage must not suppress correct heavy-path usage.

## Projected gain

Easy task: `total_input` 3.93× → ~1.1–1.4×; cost 2.04× → ~1.1–1.3× (turns 12 → ~4).
Projection from the n=1 decomposition; re-measure under W3 before claiming.

## Risks

- **Under-engagement.** Too-aggressive triage could make Haiku skip structural tools on
  genuinely hard tasks (regressing the 0.72× hard-task win). Mitigated by the hard-regime
  guard above and by phrasing the gate as "start light, escalate if insufficient".
- **Weak-model literalism cuts both ways.** The same literalism that over-tools today
  could over-correct to never-tool. The conformance + adoption cases bracket both
  failure modes.

## Decisions for the owner

- Adopt the one-line gate in AGENTS.md now, or wait and fold it into the ADR-0005 routing
  skill? (Recommended: ship the gate now — it is the highest-leverage, lowest-token
  change; move detail to the skill later.)

# ADR-0000: Record architecture decisions as ADRs with linked implementation plans

- **Status:** Accepted
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** process, documentation
- **Supersedes:** —
- **Superseded by:** —
- **Related:** the prior planning corpus [`plans/00-master-plan.md`](../00-master-plan.md) … [`plans/05-test-coverage.md`](../05-test-coverage.md)

## Context and problem statement

This repository already holds a high-quality planning corpus: six narrative
documents (`plans/00`–`plans/05`) that review the repo against its north-star
goals and reconcile a P0–P3 roadmap. That corpus is strong as a *review*, but it
embeds its architectural decisions inside prose. The six load-bearing decisions
are listed only as a flat "decisions needed" table (`plans/00-master-plan.md` §7,
`D1`–`D6`) with a one-line recommendation each. They lack three things a
decision record needs to be durable and reviewable:

1. **The alternatives that were rejected, and *why*** — a reader cannot tell what
   was considered and discarded, so the decision cannot be safely revisited later.
2. **Explicit decision drivers** tied to the owner's goals, so a future change can
   be checked against the same yardstick.
3. **External evidence** — citations to the practice of leading teams
   (Anthropic, OpenAI, Cursor, Google, Cognition) justifying *why this way and not
   another*, rather than asserted judgement.

The owner has asked that new planning work be (a) structured as Architecture
Decision Records in the style used at large engineering organisations, (b) each
linked to a detailed implementation plan that explains **what** will be done,
**why**, and **how**, and (c) backed by facts, articles, and links. This ADR
establishes that format so every subsequent record follows it.

## Decision drivers

- **Reviewability** — each decision must be individually addressable, diffable in
  version control, and revisitable in isolation (supersede, don't rewrite).
- **Justification over assertion** — every non-obvious choice cites a primary
  source explaining the trade-off, per the repo's own honesty principle
  ("state *how* you know something").
- **Separation of decision from execution** — *what/why* (the ADR) is stable and
  audited; *how* (the implementation plan) changes as code lands. Conflating them
  makes both rot.
- **Low ceremony** — the format must be lightweight enough that the owner
  actually writes one per decision, not a 20-page design doc per change.

## Considered options

1. **Keep narrative plan documents** (status quo): decisions stay embedded in
   review prose.
2. **Heavyweight design docs only** (Google-style design doc per change): one long
   document per feature, no separate decision log.
3. **Lightweight ADRs (MADR-style) + linked implementation plans** (chosen): one
   short record per decision under `plans/adr/`, each linking to a `plans/impl/`
   document that carries the executable detail.

## Decision outcome

**Chosen: Option 3 — lightweight ADRs plus linked implementation plans.**

Every architectural decision in the uplift program is recorded as a numbered ADR
in [`plans/adr/`](.) using the template below (a pragmatic blend of Michael
Nygard's original five-section form and MADR 4.0's decision-driver + options
structure). Each ADR links to one implementation plan in `plans/impl/` that holds
the step-by-step *how* — file paths, code shape, verification commands, and target
numbers — so the ADR stays a stable *what/why* record while the implementation
plan absorbs churn.

This mirrors how large engineering organisations separate the two concerns:
Google's engineering culture pairs a durable design doc with lighter decision
records ([Software Engineering at Google, ch. "Documentation"](https://abseil.io/resources/swe-book/html/ch10.html));
ThoughtWorks moved "Lightweight Architecture Decision Records" to *Adopt* on its
Technology Radar precisely because heavyweight docs go stale while one-decision
records stay current
([ThoughtWorks Technology Radar](https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records));
and AWS publishes the same ADR process as prescriptive guidance
([AWS Prescriptive Guidance: ADR process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)).

### Consequences

- **Good:** decisions become greppable and diffable; a future reader sees the
  rejected alternatives; superseding is explicit (`Superseded by ADR-NNNN`) so the
  history is never lost; citations make each choice auditable.
- **Cost:** a small per-decision authoring overhead, and a discipline to keep the
  ADR's *what/why* in sync with the implementation plan's *how*.
- **Risk & mitigation:** ADRs can drift from reality if code lands without
  updating them. Mitigation: the linked implementation plan carries a "Status"
  line and the ADR is only marked `Accepted` once its validation criterion
  (a named eval case, telemetry metric, or canary target) is defined.

## The template (every ADR in this directory follows it)

```markdown
# ADR-NNNN: <imperative title — the decision, not the topic>

- Status: Proposed | Accepted | Superseded by ADR-XXXX
- Date: YYYY-MM-DD
- Deciders: <who>
- Tags: <measurement | cost | weak-model | process>
- Related: ADR-XXXX, plans/impl/NN-<slug>.md, plans/0Y-*.md

## Context and problem statement
## Decision drivers
## Considered options
## Decision outcome           (chosen option + justification tied to drivers + evidence)
### Consequences              (good / cost / risk + mitigation)
## Pros and cons of the options
## Validation — how we confirm it worked   (named eval case / telemetry metric / canary, WITH a target number)
## References                 ([Author, Title](url) — what each source supports)
```

The **Validation** section is mandatory and non-negotiable: a decision in this
repo is not "done" until it states the falsifiable check that proves it, in this
repo's own harness (`evals/`, `telemetry/`, or a new canary). This is the repo's
existing discipline — "a skill is worth only as much as it provably changes agent
behaviour for the better" ([`evals/PLAYBOOK.md`](../../evals/PLAYBOOK.md)) — applied
to architecture decisions.

## Index

The decision log and reading order live in [`plans/adr/README.md`](README.md).

## References

- Michael Nygard, *Documenting Architecture Decisions* (2011) — the original ADR
  form (Context / Decision / Status / Consequences): <https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>
- *MADR — Markdown Any Decision Records*, v4.0 — the decision-driver + considered-
  options template this repo adopts: <https://adr.github.io/madr/>
- *adr.github.io* — the ADR community hub and tooling: <https://adr.github.io/>
- Joel Parker Henderson, *architecture-decision-record* — a large catalogue of ADR
  templates and examples: <https://github.com/joelparkerhenderson/architecture-decision-record>
- ThoughtWorks Technology Radar — *Lightweight Architecture Decision Records*
  (Adopt): <https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records>
- AWS Prescriptive Guidance — *ADR process*: <https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html>
- *Software Engineering at Google*, ch. 10 "Documentation" — design docs as the
  durable record of a decision: <https://abseil.io/resources/swe-book/html/ch10.html>

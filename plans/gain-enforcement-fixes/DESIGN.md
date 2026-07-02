# Office-hours session — adopt office-hours itself, and scope the gain/enforcement fix wave

> Method: the office-hours forcing questions, applied first to the meta-question the
> operator asked ("should we adopt office-hours into this repo?") and then to scope the
> fix wave for the 2026-07-02 audit findings
> ([docs/design/gain-and-enforcement-audit-office-hours.md](../../docs/design/gain-and-enforcement-audit-office-hours.md)).

## Part 1 — should office-hours be adopted into the repo?

### The ask

> "Сделай детальный анализ — стоит ли внедрять office hours сюда."

### Premise challenge

"Внедрять" implies the method isn't here yet. It half is: `plans/IMPROVEMENT-LOOP.md`
**mandates** an "office-hours vet (status quo / narrowest wedge / risk)" for every loop
iteration, and at least four shipped documents used it (two archived design sessions, the
orchestration-agents DESIGN, the 2026-07-02 audit). What is *not* here is the method
itself: every document cites the gstack `office-hours` skill as the source, and that
upstream is **gone — `github.com/DietrichGebert/gstack` returns 404** (checked
2026-07-02). The archives demonstrate only a fragment of the method (premise challenge,
Q2 status quo, Q4 narrowest wedge); the full question set exists nowhere we can reach.

So the real question is not "adopt a new practice" but: **the improvement loop already
depends on a method whose definition this repo does not own — codify it or keep
reconstructing it from fragments?**

### Q2 — status quo (the real competitor)

- **Discovery**: a session asked to "vet this idea" finds office-hours only if it greps
  the archives. There is no trigger — unlike every other repeated practice here, which is
  either a skill (auto-injected description) or an always-on rule.
- **Consistency**: each vet reinvents the questions. The archived sessions show drift
  already (one ran "Q2+Q4+premise", the loop log names "status quo / wedge / risk" —
  which is it?).
- **Alternatives considered**:
  - *Catalog the upstream plugin* — impossible, upstream 404s. This also removes the
    "don't duplicate marketplace plugins" objection: there is no plugin to duplicate.
  - *A docs/ page* — owns the text but has no trigger; the vet step stays convention-only.
  - *An always-on principle* — pays tokens every turn for a sometimes-used method and the
    prefix budget has only 300 bytes of headroom (8754/9054 measured) — directly against
    the repo's token-economy north star.
  - *Status quo* — free today, but the method decays as archives age and upstream stays
    dead.

### Q3 — evidence of value

The vet step is the repo's stated defense against its own biggest failure mode
(over-engineering config nobody asked for — see the model-orchestration session, which
exists only because an office-hours vet cut a "framework" down to one skill). Every loop
iteration consumes it. Cost of the skill: one description line in the injected skills
list (~40–60 tokens/session), ~1 page of body loaded only when it fires, one eval case
(mandatory — `evals/lint.py` fails CI on skills without evals).

### Q4 — narrowest wedge

One on-demand skill, `core/skills/office-hours/SKILL.md`, carrying the canonical
question set (reconstructed from our own archived sessions, with an honest provenance
note that upstream is no longer public), the smart-routing table, and the capture
convention (`docs/design/<topic>-office-hours.md`, archived when shipped). One
conformance eval. **No AGENTS.md line** — the skill description is the trigger, so the
always-on prefix stays byte-identical (zero cost against the 300-byte headroom).

Explicitly out of scope: a vet-enforcing hook (unenforceable mechanically), rewriting the
archived sessions to match the canonical set (they're provenance, not templates).

### Verdict

**Adopt — as the narrowest form (one skill + one eval), shipped as plan 05 of this
wave.** The deciding facts: the loop already mandates the method, the upstream definition
is unreachable, and the repo's own precedent (model-orchestration) chose exactly this
shape for exactly these reasons.

## Part 2 — scoping the fix wave (audit findings → plans)

The audit found six actionable defects/gaps. Office-hours scoping applied to each:

| Finding | Decision | Plan |
|---|---|---|
| `rtk grep`/wrapped commands bypass the ast-grep deny (exploited in transcripts) | Fix — reorder the deny before the already-wrapped exit, both implementations | [01](01-shell-guard-order.md) |
| Multiline/heredoc grep-on-code also bypasses the deny | **Keep fail-open.** Denying on content inside heredocs risks false positives (quoted code, embedded patterns); the wedge is the demonstrated exploit, not full coverage. Documented limitation. | — |
| `rtk`-wrap breaks bare `=`-words (`echo ===`) | Fix — extend the existing leading-`VAR=` guard to any `=`-leading token | [02](02-rtk-equals-word-guard.md) |
| Enforcement coverage invisible (34% fail-open, ctx/gitnexus adoption ~0) — audit needed a hand-written script | Fix — `agentic gain --adoption`, reusing the hook's own classifier (single source of truth) | [03](03-gain-adoption-view.md) |
| Pricing tables predate Claude 5; opus row is 3× stale ($15/$75 vs current $5/$25); unknown models silently billed as opus | Fix — refresh both tables, flag unknown models in by-model output, erratum in the audit doc | [04](04-pricing-claude5.md) |
| GitNexus: 1 call / 50 sessions but per-call hook overhead | **Defer.** The operator wants GitNexus *used*, not removed; making models reach for it is a prompt/skill-design investigation with its own eval loop, not a mechanical fix. Logged as follow-up in the INDEX. | — |
| Heredoc share (31% of Bash traffic uncompressed) | **Measure, don't legislate.** Plan 03 makes the number visible; changing model behavior is a separate experiment. | — |

Risk gates for the whole wave: `go test ./...`, `bin/ci-check.sh` (including the
shell-guard fallback self-test, extended in plans 01–02), `python3 evals/lint.py`,
`bash bin/prefix-budget.sh` — all must stay green.

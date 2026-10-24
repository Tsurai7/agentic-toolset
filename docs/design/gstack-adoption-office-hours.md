# Office-hours session — what else to take from local gstack

> Method: `core/skills/office-hours` (all six questions — this is an "adopt X?"
> decision). Context: the gstack upstream turned out to exist locally at
> `/Users/tsurai/Documents/GitHub/gstack` (the GitHub URL 404s; the checkout is
> current, v2.0.0 office-hours skill, ~60 skills total).

## Q1 — Premise challenge

The ask: "может оттуда ещё можно что-то забрать и внедрить". The implicit premise is
that adoption means copying skills over. It can't: gstack skills are **not standalone
markdown** — each carries a ~180-line preamble that executes gstack binaries
(`gstack-config`, `gstack-telemetry-log`, `gstack-brain-sync`, gbrain), writes state
under `~/.gstack/`, and assumes the gstack routing/AUQ protocol. A vendored copy either
breaks (missing binaries) or drags the whole runtime in. Reframed question: **which
gstack *methods* are worth distilling into lean local skills (the office-hours pattern),
and is the whole toolkit worth cataloging as an optional plugin?**

## Q2 — Status quo (the real competitor)

Most of the gstack catalog is already covered here or by Claude Code built-ins:

| gstack | Covered by |
|---|---|
| `/review`, `/qa`, `/cso` | `/code-review`, `/security-review`, `/verify`, `verification-before-completion` |
| `/ship`, `/land-and-deploy` | `create-pr`, `git-safety`, `no-mistakes` pipeline |
| `/spec`, `/autoplan`, `/plan-*-review` | the plan-then-delegate workflow (linked plans with hard AC + verifier agents) |
| `/learn`, `/context-save`/`restore` | Claude Code auto-memory + transcripts |
| `/retro` (telemetry-driven) | `agentic gain` / `--adoption` + `plans/IMPROVEMENT-LOOP.md` |
| `/careful`, `/freeze`, `/guard` | Claude Code permission system + `git-safety`; shell-guard for mechanical rules |
| `/diagram`, `/make-pdf` | Anthropic `pdf`/`docx` skills; mermaid via the communication rule |
| design/browser/iOS suites | out of domain for this repo |

Genuinely **not** covered: a systematic debugging protocol. `/investigate`'s core
discipline — "Iron Law: no fixes without investigation; trace data flow, test
hypotheses, **stop after 3 failed fixes and reassess**" — has no equivalent in
`core/`. The Karpathy guidelines say *what* a bug fix needs (a reproducing test) but not
*how to investigate*, and nothing enforces the stop-after-N-failures discipline.

## Q3 — Evidence of value

The 2026-07-02 audit measured the failure mode this method targets: deny-loops (a model
re-issuing the same denied grep) and 19/50 denies answered by blind retries. The
stop-and-reassess rule is exactly the missing discipline, and debugging is daily work in
every repo this config is installed into.

## Q4 — Narrowest wedge

1. **Provenance fix** to `core/skills/office-hours/SKILL.md` (ships in this wave): the
   upstream exists locally; name its canonical six (demand reality, status quo,
   desperate specificity, narrowest wedge, observation & surprise, future-fit) and state
   that our six are a deliberate adaptation — upstream's own routing sends
   "pure engineering/infra" to Q2+Q4 only, so we replaced the four product-stage
   questions with repo-relevant ones (premise, evidence, risk, cost-of-keeping).
2. **One distilled skill**: `core/skills/systematic-debugging/SKILL.md` — the
   `/investigate` method without the runtime: investigation-before-fix, hypothesis log,
   data-flow tracing, the 3-failed-fixes stop rule, and an honest provenance note. Plus
   one conformance eval (lint requires it). Zero always-on prefix cost.
3. **One catalog entry**: document gstack in `catalog/plugins.yaml` as a locally
   available, **not enabled** toolkit, with the reason (per-invocation preamble cost,
   overlap with built-ins) — so the decision is recorded and reversible.

Out of scope: vendoring any gstack skill verbatim; enabling gstack wholesale; borrowing
the AskUserQuestion decision-brief format (adds ceremony; communication rules already
cover it — revisit only with evidence of bad decision briefs).

## Q5 — Risk & verification

All additions are on-demand files: no hook, no prefix change. Gates: `evals/lint.py`
(new skill must carry an eval), `bin/prefix-budget.sh` byte-identical,
`bin/ci-check.sh`. Risk of skill-list bloat (one more description per session) is the
Q6 trade.

## Q6 — Cost of keeping

~50 tokens/session for the new skill description + one eval to maintain. Removal
criterion: if `/investigate`-style discipline shows no firing in transcripts after a few
weeks of real debugging work (checkable via the same transcript analytics as the audit),
drop the skill.

## Verdict

**Take three things, nothing else**: the provenance fix, a distilled
`systematic-debugging` skill (+eval), and a documented-but-disabled catalog entry for
gstack. Everything else in the catalog is either already covered (Q2 table) or coupled
to a runtime whose per-invocation token cost contradicts this repo's north star.
Shipped as plan 06 of `plans/gain-enforcement-fixes/`.

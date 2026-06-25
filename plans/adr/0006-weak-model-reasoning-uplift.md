# ADR-0006: Ship weak-model reasoning-uplift scaffolds the config measures but never causes

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** weak-model, cost-tiering
- **Related:** [ADR-0003 — Falsifiable eval backbone](0003-eval-backbone-canary.md), [ADR-0005 — Model-tiering & routing](0005-model-tiering-routing.md), [ADR-0002 — Quality & latency proxies](0002-quality-latency-proxies.md), [ADR-0001 — Real-usage baseline](0001-real-usage-measurement-baseline.md); implementation plan [`plans/impl/06-weak-model-reasoning-uplift.md`](../impl/06-weak-model-reasoning-uplift.md); prior corpus items MAT-07 (byte-stable render), MAT-08 (minimal-context profile), MAT-10 (weak-agent regression gate), TEST-10 (Haiku-uplift suite), BUG-01..23 (P0 hook hardening)

## Context and problem statement

The owner has two goals: cardinally raise the intelligence of the weak models
(Sonnet 4.6, especially Haiku 4.5) when they are driven by this config, and
cardinally reduce the consumption and latency of the heavy model (Opus 4.8). The
program judges every change against a single balanced scorecard that weights both
goals roughly equally.

The repository is in a contradictory state with respect to Goal 1. The evaluation
harness can *measure* reasoning quality — [ADR-0003](0003-eval-backbone-canary.md)
adds a differential-uplift harness and the [TEST-10] Haiku-uplift suite, and
[`evals/PLAYBOOK.md`](../../evals/PLAYBOOK.md) demands that every skill "provably
changes agent behaviour for the better." But the config contains almost no
content that would *cause* the uplift those instruments are built to detect. The
research synthesis names this exactly: the plan-first scaffold is "the literal
'reasoning-uplift CONTENT the repo measures but does not CAUSE'"
([research digest](/tmp/research_digest.json), workstream "Weak-model reasoning
uplift"). The reasoning guidance that does exist is abstract prose — for example
[`core/principles/karpathy-guidelines.md:51`](../../core/principles/karpathy-guidelines.md)
says only "state a brief plan with a verifiable check per step," which a weak
model reads but cannot reliably execute, because weak models imitate concrete
exemplars far better than they follow abstract instructions
([Zhou et al., Least-to-Most Prompting, arXiv:2205.10625](https://arxiv.org/abs/2205.10625)).

This matters because the weak models are not a hypothetical: the owner's real
205-session corpus already contains Opus 5421 / Haiku 1335 / Sonnet 219 assistant
records ([research digest](/tmp/research_digest.json), critique P0-1), so Haiku is
already doing a large fraction of the work — mostly background and sub-task work —
with none of the scaffolding that would make it reliable. Lifting Haiku and Sonnet
directly serves Goal 1, and it serves Goal 2 second-hand: a weak model that
finishes a routed sub-task correctly the first time avoids the correction
round-trips and Opus escalations that consume the heavy model's rate-limit
headroom.

The naive way to add this content — write full scaffolds into the always-on
`AGENTS.md` prefix for every model — is the trap. Anthropic's own guidance is that
a bloated instruction file causes *strong* models to ignore instructions
([Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)),
and few-shot exemplars that lift weak models can *lower* strong-model accuracy
([Agarwal et al., Many-Shot In-Context Learning, arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)).
So unconditional scaffolds would tax Opus's prefix (hurting Goal 2) to help Haiku
(Goal 1) — the conflict the balanced scorecard forbids resolving in one
direction. The decision below is therefore not only *what reasoning content to
add*, but *how to render it so it ships without taxing the heavy model*.

## Decision drivers

- **Goal 1 (primary here): cardinally raise weak-model task success.** The
  scaffolds must measurably lift Haiku and Sonnet on multi-step coding work, not
  merely exist as documentation.
- **Goal 2 (must not regress): keep Opus lean and fast.** Added content must not
  bloat the heavy-tier prefix, must not depress the already-maxed 96.3% weighted
  cache hit rate ([research digest](/tmp/research_digest.json), baseline facts),
  and must not trigger the strong-model exemplar penalty.
- **Balanced rule.** A scaffold is accepted only if it helps the weak tier *more*
  than the strong tier — the differential, not the level. Equal help to both
  models is a Goal-2 regression dressed up as a Goal-1 win, because it spends Opus
  prefix tokens for no Opus benefit.
- **Falsifiability over assertion.** Every uplift claim is proven by
  [ADR-0003](0003-eval-backbone-canary.md)'s differential harness with a concrete
  target, never asserted in prose — the repo's standing honesty principle.
- **Conditional, not blanket.** Some scaffolds (self-critique) *help* a weak model
  and *hurt* a strong one at the same task; they must be triggered by task
  difficulty, not applied everywhere.

## Considered options

1. **Status quo — abstract prose only.** Keep
   [`karpathy-guidelines.md:51`](../../core/principles/karpathy-guidelines.md) and
   `verification-before-completion` as the only reasoning guidance; rely on the
   model to operationalize them. (Rejected.)
2. **Full scaffolds, unconditional, for all models.** Write the plan-first,
   self-critique, and answer-shape scaffolds with exemplars into the always-on
   `AGENTS.md` prefix, applied to every model on every task. (Rejected.)
3. **Model-aware, differentially-proven scaffolds (chosen).** Add executable
   scaffold skills (plan-first decomposition, bounded conditional self-critique,
   structured answer-shapes) plus a deterministic edit-time lint hook; render them
   through a model-tier dimension so the weak tier gets the full scaffold with
   exemplars and the strong tier gets a one-line pointer; and accept each one only
   when [ADR-0003](0003-eval-backbone-canary.md)'s harness shows the weak-model win
   margin exceeds the strong-model margin by at least 0.20.
4. **Fine-tune / prompt-cache a bespoke weak-model system prompt out of band.**
   Maintain a separate Haiku-only prompt outside the config render. (Rejected —
   duplicates the render, fragments the source of truth, and is out of scope for a
   portable text config.)

## Decision outcome

**Chosen: Option 3 — model-aware, differentially-proven reasoning scaffolds.**

We add four reasoning-uplift levers as repo content, each rendered through a new
model-tier dimension and each gated by the differential-uplift proof:

1. **A plan-first / decomposition scaffold skill**
   ([`core/skills/plan-first/SKILL.md`](../../core/skills/plan-first/SKILL.md), new):
   a fillable template that restates the goal in one line, enumerates ordered
   sub-steps each with an explicit verifiable check, names the riskiest step,
   acts, then ticks each check. It carries two concrete few-shot exemplars (a
   bug-fix and a refactor) and promotes the abstract prose at
   [`karpathy-guidelines.md:51`](../../core/principles/karpathy-guidelines.md) into
   executable form. This is the single highest-leverage lever: least-to-most
   decomposition took text-davinci-002 from **6% to 76%** on SCAN, versus only
   **16%** for chain-of-thought
   ([Zhou et al., arXiv:2205.10625](https://arxiv.org/abs/2205.10625)), a far
   weaker uplift than plain CoT
   ([Wei et al., arXiv:2201.11903](https://arxiv.org/abs/2201.11903)); and Cursor
   calls planning "the most impactful change you can make"
   ([Cursor agent best practices](https://cursor.com/blog/agent-best-practices)).

2. **A bounded, conditionally-triggered self-critique scaffold**
   ([`core/skills/self-critique/SKILL.md`](../../core/skills/self-critique/SKILL.md),
   new, distinct from external-evidence `verification-before-completion`): a
   pre-completion checklist that restates the request, lists each explicit
   requirement, points at the output line satisfying it, and names one thing that
   could be wrong — capped at one reflect iteration. Reflexion reached **91%
   pass@1 on HumanEval versus GPT-4's 80%** with no weight updates
   ([Shinn et al., arXiv:2303.11366](https://arxiv.org/abs/2303.11366)). But the
   **self-critique paradox is load-bearing**: a critique loop is a "miracle worker"
   below roughly **35%** base accuracy and "devastating" above roughly **75%**
   ([Snorkel, The Self-Critique Paradox](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/)),
   so it must be triggered only on hard/uncertain tasks, never blanket.

3. **Structured-output answer-shape schemas**
   ([`core/skills/answer-shapes/SKILL.md`](../../core/skills/answer-shapes/SKILL.md),
   new): a small set of fillable, opt-in output skeletons (bug-fix → root cause /
   fix / verification / risk; code-review; investigation), plus an instruction to
   emit a step's output against an explicit schema when it feeds another step.
   Constrained output gives outsized gains to small models: strict-JSON on GSM8K
   lifts a **1B model from 15.2% to 39.0%** and a **1.5B model from 49.4% to 73.9%**,
   and a constrained 7B beat an unconstrained 70B on logical parsing
   ([Geng et al., JSONSchemaBench, arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)).
   A parseable worker result is also exactly what lets an Opus orchestrator consume
   a Haiku worker's output without a re-ask — the cost-tiering handoff of
   [ADR-0005](0005-model-tiering-routing.md).

4. **An edit-time syntax/lint guardrail hook on Edit/Write**
   ([`providers/claude/hooks/edit-lint.sh`](../../providers/claude/hooks/edit-lint.sh),
   new, sibling to
   [`providers/claude/hooks/shell-guard.sh`](../../providers/claude/hooks/shell-guard.sh)):
   a fast per-language parse/lint check (`python -m py_compile`, `tsc --noEmit`, or
   `ast-grep --lang` as a parse check) that returns the error to the agent so it
   retries before a malformed edit lands. SWE-agent's largest single ACI ablation:
   removing linting drops resolve rate by **15.0% relative**, and **51.7%** of
   trajectories hit at least one failed-lint edit, with recovery odds falling as
   failed edits accumulate
   ([Yang et al., SWE-agent, NeurIPS 2024, arXiv:2405.15793](https://arxiv.org/abs/2405.15793)).
   Weak models produce more malformed edits than Opus, so a deterministic
   write-time gate disproportionately lifts them.

These four ship through the **model-aware render dimension**: the install render
gains a model-tier fork (weak-tier = full scaffold + exemplars; strong-tier =
one-line pointer), keyed off the active model where detectable or an explicit
`AGENTIC_TIER` environment variable, extending the [MAT-07] byte-stable render and
the [MAT-08] minimal-context profile. This is what makes the two goals
co-satisfiable rather than in tension: the bytes that lift Haiku never reach
Opus's prefix, and the exemplars that could trigger the strong-model penalty are
gated to the weak tier
([Anthropic effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents);
[Agarwal et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)).

**Why this option over the alternatives.** Option 1 leaves the measured gap
permanently open — the harness keeps reporting "no uplift" because nothing causes
it. Option 2 buys Goal 1 by sacrificing Goal 2: it bloats the Opus prefix,
threatens the 96.3% cache hit rate that is already essentially maxed, and triggers
the documented strong-model exemplar penalty, so it fails the balanced rule by
construction. Option 3 is the only one that adds the proven uplift content while
structurally protecting the heavy model, and binds every claim to a falsifiable
differential, so a scaffold that does not actually help the weak tier more than
the strong tier is rejected automatically rather than shipped on faith.

### Consequences

**Good.**

- The repo finally *causes* the weak-model uplift it already measures: plan-first
  decomposition, conditional self-critique, structured output, and a write-time
  lint gate are the four levers with the strongest published weak-model effect
  sizes.
- The model-aware render keeps Opus's always-on prefix lean and cache-stable, so
  Goal 1 content does not become a Goal 2 tax.
- Every scaffold is falsifiable through [ADR-0003](0003-eval-backbone-canary.md):
  the differential gate means content that helps both models equally — and thus
  wastes Opus prefix — cannot ship.

**Cost.**

- Authoring and maintaining four scaffolds plus their conformance and value cases
  (per `AGENTS.md` lines 54-56, every content change ships both).
- The render gains a tier dimension, adding a second golden to maintain (one per
  tier) on top of the [MAT-07] byte-stability golden.
- The edit-lint hook adds per-edit latency; it must stay within a small budget
  (mirroring the shell-guard hook's sub-50ms target,
  [ADR-0002](0002-quality-latency-proxies.md)) or it taxes both tiers.

**Risks and mitigations** (the assigned critique points, folded in as named
risks).

- **Risk R1 — the self-critique paradox has no runtime base-accuracy gate**
  (critique P1-7). The trigger is a heuristic on "non-trivial tasks," but the model
  cannot *know* at runtime whether a task sits in the harmful >75%-accuracy zone,
  so blanket or mis-triggered critique can regress easy tasks and burn
  tokens/latency
  ([Snorkel, Self-Critique Paradox](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/)).
  *Mitigation:* the self-critique value case measures the differential **with
  critique versus without, at two difficulty bands**, and **FAILS if critique
  regresses the easy band** — the paradox is defended against empirically, not just
  documented. The conformance case measures trigger precision (should-trigger /
  should-not-trigger), but on its own it only proves the trigger fires on the
  right tasks, not that firing *helped*; the two-band value case closes that gap.

- **Risk R2 — scaffolds add prefix bytes that tax Opus and the cache**
  (critique P2-13). Three of the four levers add instruction content; unconditional
  rendering would depress the already-maxed cache hit rate and bloat the heavy
  prefix before any mitigation exists. *Mitigation:* the **model-aware render** is
  the structural fix — weak-tier full scaffold versus strong-tier one-line pointer,
  keyed off the active model or `AGENTIC_TIER` — so the bytes never reach Opus.
  Few-shot exemplars, which help weak models and can *hurt* strong ones
  ([Agarwal et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1)), are
  gated to the weak tier specifically. Concretely, run
  [`telemetry/gate.py`](../../telemetry/gate.py) before and after each prefix edit
  and treat a weighted-cache-hit drop as a blocking regression (the gate already
  exists; this makes it explicit for prefix-byte changes).

- **Risk R3 — equal uplift on both models masquerades as a win** (the differential
  proof). A scaffold that lifts Haiku and Opus equally is indistinguishable, on a
  within-model A/B, from one that closes the weak-strong gap — but it spends Opus
  prefix for no Opus benefit. *Mitigation:* every uplift value case **passes only
  if the weak-model win margin exceeds the strong-model margin by ≥ 0.20**, via
  [ADR-0003](0003-eval-backbone-canary.md)'s uplift harness over normalized tier
  labels (the harness must normalize real model ids `claude-haiku-4-5-20251001` and
  `claude-opus-4-8` to tier labels, per the critique's correctness note).

- **Risk R4 — the edit-lint hook lands on un-hardened hook plumbing.** The new
  Edit/Write hook reuses the JSON-envelope parsing pioneered by
  [`shell-guard.sh`](../../providers/claude/hooks/shell-guard.sh); shipping it
  before the [BUG-01..23] P0 hook-hardening lands would inherit the same envelope
  bugs. *Mitigation:* sequence the edit-lint hook **after** BUG-01..23 so it reuses
  the corrected envelope handling, and fail **open** (allow the edit) on any parser
  ambiguity or unsupported language, exactly as shell-guard does, so the gate never
  blocks legitimate work.

## Pros and cons of the options

**Option 1 — status quo, abstract prose only.**

- Good: zero authoring cost; no prefix-byte or cache risk.
- Bad: the measured uplift gap stays open permanently; weak models cannot
  operationalize abstract instructions
  ([Zhou et al., arXiv:2205.10625](https://arxiv.org/abs/2205.10625)); fails Goal 1.

**Option 2 — full scaffolds, unconditional, all models.**

- Good: simplest to implement; one render, one golden.
- Bad: bloats the Opus prefix and risks the maxed cache hit rate (fails Goal 2);
  triggers the strong-model exemplar penalty
  ([Agarwal et al., arXiv:2501.10868](https://arxiv.org/html/2501.10868v1));
  blanket self-critique regresses easy tasks
  ([Snorkel](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/));
  fails the balanced rule by construction.

**Option 3 — model-aware, differentially-proven scaffolds (chosen).**

- Good: adds the highest-effect-size weak-model content; keeps Opus lean via the
  tier render; every claim falsifiable through the differential harness; the
  self-critique paradox is defended by a two-band value case.
- Bad: most engineering effort (four scaffolds, a hook, a render dimension, two
  goldens); the differential gate can reject a scaffold that *feels* helpful but
  does not beat the strong-model margin.

**Option 4 — out-of-band bespoke weak-model prompt.**

- Good: total control over the Haiku prompt.
- Bad: fragments the source of truth, duplicates the render, not portable as text
  config; out of scope.

## Validation — how we confirm it worked

This decision is not "done" until the following named checks pass, in this repo's
own harness, against these target numbers.

- **Differential value cases (per scaffold), via [ADR-0003]'s uplift harness.**
  Each of `plan-first`, `self-critique`, and `answer-shapes` ships a value case run
  under Haiku and Opus. Each passes only if it is `treatment_preferred` on Haiku
  with `flip_rate < 0.10` **and** the Haiku win margin exceeds the Opus win margin
  by **≥ 0.20** (the `weak_uplift_exceeds_strong` verdict from
  [ADR-0003](0003-eval-backbone-canary.md)). This is the differential proof for
  Risk R3.

- **The 10-task multi-step canary** (the in-repo canary suite of
  [ADR-0003](0003-eval-backbone-canary.md)/[ADR-0004](0004-gain-scorecard-experiment.md)).
  With the plan-first scaffold active, **Haiku task-success rises by ≥ 15
  percentage points while Opus rises by < 5 points**. The canary's deterministic
  checks (apply-and-run-tests where possible) are the primary quality guard, so
  this is judge-free where it can be.

- **Self-critique two-band value case** (Risk R1, critique P1-7). A prompt with a
  buried second constraint weak models commonly drop ("do X and ALSO ensure Y")
  graded on both constraints, run under Haiku treatment versus control at an EASY
  band and a HARD band, where a prompt's band is assigned by the control arm's
  measured base pass-rate on that prompt for that model (EASY when control already
  passes > 75% of the time, HARD when it passes < 35% — the two zones the Snorkel
  paradox identifies). The case **PASSES only if** Haiku's satisfies-both rate
  gain exceeds the same delta on Opus (differential) **AND critique does not
  regress the EASY band**. A companion conformance case measures trigger precision
  (should-trigger / should-not-trigger).

- **Edit-lint hook telemetry** ([ADR-0002](0002-quality-latency-proxies.md)'s
  proxies over real transcripts). After the hook lands, the **edit-error /
  edit-revert rate on Haiku and Sonnet sessions drops by ≥ 30%**, measured over a
  20-session window (the same window the cache gate uses). A conformance case
  confirms the agent receives and acts on a lint error on a prompt that tempts a
  malformed edit.

- **Render byte-stability and cache neutrality** (Risk R2, critique P2-13).
  Extending the [MAT-07] golden: the strong-tier rendered CLAUDE.md is
  byte-smaller than the weak-tier render and stable across runs, and
  [`telemetry/gate.py`](../../telemetry/gate.py) shows no weighted-cache-hit
  regression (stay ≥ 0.85; gate fails below 0.80) before-versus-after each prefix
  edit.

## References

- [Zhou et al., *Least-to-Most Prompting Enables Complex Reasoning in Large Language Models*, arXiv:2205.10625](https://arxiv.org/abs/2205.10625) — the 6%→76% SCAN result (vs 16% for CoT) that justifies plan-first decomposition as the headline weak-model lever.
- [Wei et al., *Chain-of-Thought Prompting*, arXiv:2201.11903](https://arxiv.org/abs/2201.11903) — the CoT baseline that least-to-most outperforms on weak models.
- [Cursor, *Agent best practices*](https://cursor.com/blog/agent-best-practices) — vendor corroboration that planning is "the most impactful change you can make."
- [Anthropic, *Building effective agents*](https://www.anthropic.com/research/building-effective-agents) — supports decomposition/orchestrator-worker patterns the plan-first scaffold encodes.
- [Shinn et al., *Reflexion*, arXiv:2303.11366](https://arxiv.org/abs/2303.11366) — 91% vs 80% pass@1 on HumanEval, the upside case for the self-critique loop.
- [Snorkel, *The Self-Critique Paradox*](https://snorkel.ai/blog/the-self-critique-paradox-why-ai-verification-fails-where-its-needed-most/) — the <35% helps / >75% hurts evidence that forces conditional triggering and the two-band value case (Risk R1).
- [Geng et al., *JSONSchemaBench*, arXiv:2501.10868](https://arxiv.org/html/2501.10868v1) — strict-JSON small-model gains (1B 15.2%→39.0%; 1.5B 49.4%→73.9%; constrained 7B beats unconstrained 70B) for answer-shapes, and the many-shot exemplar penalty on strong models that motivates weak-tier gating (Risk R2/R3).
- [Yang et al., *SWE-agent*, NeurIPS 2024, arXiv:2405.15793](https://arxiv.org/abs/2405.15793) — removing linting drops resolve rate 15.0% relative; 51.7% of trajectories hit a failed-lint edit — the basis for the edit-time lint hook.
- [Anthropic, *Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — bloated instruction files cause strong models to ignore instructions, motivating the model-aware render (Risk R2).
- [Anthropic, *Claude prompting best practices*](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) — vendor guidance on exemplars and structured output the scaffolds follow.
- [Cursor, *Rules*](https://cursor.com/docs/rules) — corroborates per-context rule rendering, supporting the tier dimension.

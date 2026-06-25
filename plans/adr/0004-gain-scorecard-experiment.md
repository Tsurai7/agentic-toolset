# ADR-0004: Compose every instrument into one `agentic-cfg gain` balanced scorecard with a task-mix-normalized before/after experiment

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** measurement, process
- **Related:** [ADR-0001](0001-real-usage-measurement-baseline.md) (baseline + units), [ADR-0002](0002-quality-latency-proxies.md) (quality/latency proxies), [ADR-0003](0003-eval-backbone-canary.md) (canary + differential harness), [ADR-0005](0005-model-tiering-routing.md) (routing KPI), [ADR-0007](0007-adoption-flywheel.md) (adoption metric); implementation in [`plans/impl/04-gain-scorecard-experiment.md`](../impl/04-gain-scorecard-experiment.md); upstream roadmap items GO-15/GO-16 ([`plans/01-go-rewrite.md:773-774`](../01-go-rewrite.md)), and the static north-star tables in [`plans/00-master-plan.md`](../00-master-plan.md) and [`plans/02-maturity-review.md`](../02-maturity-review.md) (MAT-01, MAT-10) that this ADR turns into a live artifact.

## Context and problem statement

The other six ADRs each add one instrument: a captured baseline and corrected
units (ADR-0001), per-model quality and latency proxies (ADR-0002), a canary and
differential-uplift harness (ADR-0003), a routing KPI (ADR-0005), and an adoption
rate (ADR-0007). Individually they answer narrow questions. Collectively they do
*not* answer the owner's actual question — "is this week's config better than last
week's, on **both** goals, and should I keep it?" — because the numbers live in
five different scripts with five different invocations, and nothing reconciles a
cost win against a quality regression.

The existing planning corpus has a north-star table, but it is static design
rationale ([`plans/00-master-plan.md`](../00-master-plan.md)), not a live
scorecard regenerated from transcripts. There is no single artifact the owner
reads in under a minute, and no defined review checkpoint at which "measure over
several days" resolves to keep / iterate / revert.

Worse, a naive roll-up would be *wrong on the owner's real data*. The verified
205-session corpus is Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53
assistant records, with `isSidechain=true` on 28% of records and subagent
transcripts written as **separate** `.jsonl` files under `.../subagents/...`
(`/tmp/research_digest.json`, critique P0-1 and P0-2). So:

- A blended "Opus token share" baseline assumed to be >80% is **empirically
  false** — Haiku is already heavily used as background work.
- `report.collect()` globs `**/*.jsonl` and takes the N most-recent **files**
  ([`telemetry/report.py:179-189`](../../telemetry/report.py)), so a single user
  task that fanned out into subagents is counted as many "sessions." Every
  per-session metric (turns, latency, cost-per-task) is computed on the wrong
  unit over the wrong population.

The scorecard cannot be a cosmetic table over these primitives. It must sit on
top of session reconstruction (ADR-0001) and a task-class-aware before/after
experiment, or its headline numbers are unattributable. And the dollar column
must be honest: the owner is on a flat \$200/month Claude Max subscription, not
API pay-as-you-go, so `report.py`'s `$est` is an API-list-price estimate the file
itself labels "for relative comparison, not invoices"
([`telemetry/report.py:19-21`](../../telemetry/report.py), `report.py:35`). The
real cost constraint is **Opus token consumption** (a proxy for rolling/weekly
rate-limit headroom and latency), not money.

## Decision drivers

- **Goal 1 — weak-model intelligence:** the scorecard must surface whether Haiku
  4.5 and Sonnet 4.6 got measurably better (lower tool-error / edit-revert /
  correction rates; positive differential uplift) under this config.
- **Goal 2 — heavy-model consumption and latency:** the scorecard's primary cost
  row must be **main-thread Opus token-share / consumption** (rate-limit headroom
  and latency proxy), with `$est` kept only as a clearly-labeled secondary
  "API-equivalent resource proxy, not the owner's bill."
- **Balanced decision rule (the tie-breaker):** a single weighted scorecard, both
  goals roughly equal, *never* one KPI. A cost win that regresses any quality
  proxy or judged correctness is **not accepted** — the correctness-vs-tokens gate
  is encoded in the scorecard's pass/fail logic, not left to judgement.
- **Sub-minute legibility:** the owner reads one committed artifact and decides
  keep / iterate on a fixed weekly cadence. Regenerating on two different days
  must yield a diff readable in under a minute.
- **Attribution over vanity:** every row traces to a concrete telemetry/eval
  source (no hand-typed numbers), computed on reconstructed sessions bucketed by
  task class, so "this week was just harder" cannot masquerade as a config effect.
- **Forward-compatible surface:** ship the command as a thin shell dispatcher now,
  designed to fold into the future Go `agentic` binary (GO-15/GO-16) without a
  contract change.

## Considered options

1. **Status quo — five separate scripts, a static north-star table** (rejected):
   the owner runs `report.py`, `gate.py`, `adoption.py`, `uplift.py`, and reads
   the canary history by hand, then reconciles them mentally.
2. **A Markdown table generator with no experiment layer** (rejected): one
   `scorecard.py` that aggregates the current-window numbers into `SCORECARD.md`,
   but with no cutover, no task-class buckets, and no variance reduction.
3. **One `agentic-cfg gain` command backed by `scorecard.py` + `experiment.py`,
   with task-class bucketing and CUPED-adjusted before/after deltas, output to a
   committed `SCORECARD.md`** (chosen): the scorecard rows are *populated by* the
   experiment layer, so every delta is within-task-class, variance-reduced, and
   carries a confidence interval; the balanced decision rule is computed, not
   asserted.
4. **A full external observability stack** (Langfuse / Phoenix dashboards)
   (rejected): correct names exist (ADR-0002 aliases OTel GenAI conventions) but a
   hosted dashboard is heavy ceremony for a single developer, adds a network
   dependency, and re-reads the same JSONL the local scripts already parse.

## Decision outcome

**Chosen: Option 3 — one `agentic-cfg gain` command backed by
`telemetry/scorecard.py` and `telemetry/experiment.py`, emitting a committed
`SCORECARD.md`.**

The command surface is a thin shell dispatcher [`bin/agentic-cfg`](../../bin)
with a `gain` subcommand, mirroring how `bin/ci-check.sh` already shells out to
the Python harness ([`bin/ci-check.sh:77-85`](../../bin/ci-check.sh)). It calls a
new stdlib-only `telemetry/scorecard.py`, which in turn calls `telemetry/report.py`,
`telemetry/gate.py`, `telemetry/adoption.py` (ADR-0007), `evals/uplift.py`
(ADR-0003), and the canary history. This is the same wrapper pattern the Go
rewrite already plans for `agentic ci-check` ([`plans/01-go-rewrite.md:181-184,195-197`](../01-go-rewrite.md)),
so when GO-15/GO-16 land, `agentic gain` shells to the identical Python with no
contract change.

The scorecard reproduces the digest's `synthesis.scorecard`
(`/tmp/research_digest.json`, lines 353-425) as a table with one row per metric —
`metric / goal / source / baseline_method / target / cadence` — **with the
cost-framing correction applied**: the primary cost row is *main-thread Opus
token-share / consumption*, and `$est` is a separate, explicitly-labeled secondary
row ("API-equivalent resource proxy, not the bill").

The experiment layer is the part that makes a low-n personal before/after
informative. `telemetry/experiment.py` takes a **cutover date**, buckets
reconstructed sessions into a small set of task classes (single-file fix,
multi-file refactor, codebase Q&A, PR creation — inferred from dominant tool mix /
git branch / cwd, exactly as the routing telemetry already clusters in ADR-0005),
and reports **per-class** and **CUPED-adjusted** deltas with confidence intervals,
using each class's recorded pre-period mean as the covariate.

This is justified by published method and the owner's own data:

- **Why a single balanced scorecard, not a single KPI:** Cursor's CursorBench
  scores models on a *correctness-vs-token* trade-off rather than either axis
  alone, precisely because a token win that loses correctness is a regression
  ([CursorBench](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)).
  The digest's scorecard proposal makes this concrete: "Lets the owner read one
  artifact in under a minute to decide keep/iterate" (`/tmp/research_digest.json`,
  lines 65-72). We encode the balance as a hard rule in `scorecard.py`: a row is
  green only if its target is met *and* no quality row regressed.
- **Why CUPED, and why it is a hard dependency (not "after"):** CUPED reduces the
  variance of a metric by regressing out a pre-experiment covariate, cutting the
  sample size needed to detect an effect by roughly 30-50%
  ([Optimizely — What is CUPED](https://www.optimizely.com/optimization-glossary/what-is-cuped);
  [arXiv:2510.03468](https://arxiv.org/abs/2510.03468)). For a single noisy
  developer this is the difference between detecting a real change in days versus
  weeks (`/tmp/research_digest.json`, lines 51-58). The critique (P0-3) is
  explicit that without task-class bucketing the "turns to completion" and
  "cost per session" rows are *uninterpretable* — a hard 40-turn task and five
  easy 8-turn tasks land in the same bucket — so CUPED-style normalization is
  promoted from "after" to a **prerequisite** of those rows existing at all.
- **Why per-class with CIs and not a blended number:** the experiment reports the
  headline within-class, so "this week was just harder" cannot masquerade as a
  config effect (`/tmp/research_digest.json`, lines 53-58).

The expected outcome is the artifact every plan in this corpus references but none
builds: one `SCORECARD.md`, regenerated by `agentic-cfg gain`, readable in under
a minute, every row sourced from live reconstructed transcripts, reviewed on a
documented weekly keep/iterate cadence.

### Consequences

**Good**

- One command, one committed artifact: the owner runs `agentic-cfg gain` and reads
  `SCORECARD.md` — both goals, pass/fail per row, in under a minute.
- The balanced decision rule is *computed*: a cost win that regresses a quality
  proxy or judged correctness shows red, so the owner cannot accidentally ship a
  Goal-2 win that costs Goal 1.
- CUPED + task-class bucketing make a personal, low-n before/after attributable —
  deltas are within-class and variance-reduced, with CIs.
- The shell dispatcher folds into Go `agentic gain` (GO-15/GO-16) for free,
  because it is a thin wrapper over the same Python (`plans/01-go-rewrite.md:195-197`).

**Cost**

- Two new stdlib modules (`scorecard.py`, `experiment.py`), a `bin/agentic-cfg`
  dispatcher, and a committed `SCORECARD.md` to keep regenerated. No new runtime
  dependencies (stdlib only, read-only on transcripts, zero LLM cost for the
  aggregation itself).
- A documented review ritual the owner must actually perform weekly.

**Risks and mitigations** (critique points folded in as named risks)

- **Risk — wrong unit / wrong population (critique P0-1, P0-2):** computing the
  scorecard over raw `**/*.jsonl` files double-counts subagent fragments and
  blends sidechain and `<synthetic>` records into the Opus-share baseline, which
  is *empirically* not >80%. *Mitigation:* `scorecard.py` and `experiment.py`
  consume **only** the reconstructed-session view from ADR-0001 (sessions grouped
  by top-level id, sidechain files attached as children) and the *main-thread,
  sidechain-excluded, `<synthetic>`-filtered* Opus share from ADR-0005. The
  scorecard refuses to emit a row whose source has not been reconstructed; this is
  a hard dependency on ADR-0001, declared in "Dependencies."
- **Risk — undefined "completion / resolved" (critique P0-3):** "turns to
  completion" and "cost per resolved task" have no ground-truth resolved signal.
  *Mitigation:* the scorecard drops "resolved" and reports cost/turns **per
  session bucketed by task class with confidence intervals** (CUPED-adjusted),
  exactly as the experiment layer produces them; "cost per resolved task" appears
  only as a labeled, lower-confidence secondary derived from `treatment_not_worse`
  judged quality, never as a headline.
- **Risk — CUPED oversold on rare binary events (critique P2-11):** CUPED reduces
  variance for *continuous* metrics with a good covariate (tokens, latency, cost)
  but does little for low-rate binary events (reverts, corrections, tool errors).
  *Mitigation:* `experiment.py` separates the two families. Continuous metrics get
  CUPED-adjusted deltas with CIs over a multi-day window; rare-event rates are
  pooled across a longer window or the canary, and the scorecard **labels which
  KPIs are not detectable in a multi-day window and require weeks** so the owner
  does not over-read a flat revert rate as "no change."
- **Risk — statistical power overclaimed (critique P2-11):** with ~450
  text-bearing user turns across 205 sessions, "detect a >=15% change in any KPI
  in a few days" is optimistic for the quality proxies. *Mitigation:* every
  rare-event row in the scorecard carries a CI and a "needs N more sessions /
  weeks" annotation when the CI straddles zero, so the owner sees *underpowered*
  rows as gray, not green or red.
- **Risk — Goodhart on the scorecard itself:** optimizing a config to make the
  table green is the failure mode of any dashboard. *Mitigation:* the deterministic
  canary trend (ADR-0003) is the primary quality guard for routing, separate from
  the scorecard's real-session proxies; a config change is never accepted on a
  scorecard improvement alone if the canary or differential-uplift rows regress.
- **Risk — drift between the scorecard and reality:** a hand-edited `SCORECARD.md`
  rots. *Mitigation:* every cell is generated; `agentic-cfg gain` overwrites the
  file wholesale, and a committed header records the generating command, the
  cutover date, and the session window so the artifact is reproducible.

## Pros and cons of the options

- **Option 1 — status quo (five scripts + static table).** *Pro:* nothing to
  build. *Con:* the owner reconciles five outputs by hand every review; no balanced
  rule, no attribution, no cadence; fails the sub-minute and correctness-vs-tokens
  drivers outright.
- **Option 2 — table generator, no experiment layer.** *Pro:* cheap; one command.
  *Con:* the headline numbers are computed over un-bucketed, un-normalized,
  possibly un-reconstructed sessions, so a hard week reads as a config regression.
  Directly hits critique P0-2 and P0-3; cannot satisfy "attribution over vanity."
- **Option 3 — `agentic-cfg gain` + scorecard + experiment (chosen).** *Pro:* one
  artifact, balanced rule computed, CUPED-normalized per-class deltas with CIs,
  honest cost framing, folds into Go. *Con:* the most code (two modules + a
  dispatcher) and a real dependency chain on ADR-0001/0002/0007; the experiment
  math must be implemented correctly. The dependency is the point — it is what
  makes the numbers trustworthy.
- **Option 4 — external observability stack.** *Pro:* mature dashboards, standard
  OTel names. *Con:* a hosted/network dependency and operational weight that is
  disproportionate for one developer; re-reads the same local JSONL; conflicts
  with the repo's stdlib-only, read-only, local-first telemetry posture
  ([`telemetry/report.py:10`](../../telemetry/report.py)).

## Validation — how we confirm it worked

The decision is validated by the scorecard's own properties, with target numbers:

1. **Sub-minute diff (the headline acceptance test).** Run `agentic-cfg gain` on
   two different days; `git diff SCORECARD.md` must be readable in under a minute —
   a handful of changed cells, each a single number with its pass/fail color, no
   reflowed prose (`/tmp/research_digest.json`, scorecard verification, lines
   72). *Target:* the day-over-day diff touches only value/target/status cells.
2. **Every row populates from live transcripts.** `agentic-cfg gain --json` emits
   every scorecard row with a non-null `value` and a non-null `source` that names
   a concrete script + flag; zero hand-typed numbers. *Target:* all 9 scorecard
   rows (the `synthesis.scorecard` set, lines 353-425) populate from live
   reconstructed transcripts; any row whose source is unavailable renders gray
   ("not yet measurable"), never green.
3. **The balanced rule is enforced.** Feed `scorecard.py` a synthetic window where
   the Opus-token-share row meets target but a quality-proxy row regressed; the
   overall verdict must be **NOT ACCEPTED** (red), not "1 of 9 green." *Target:* a
   selftest asserts a cost win + a quality regression yields a blocking verdict
   (the correctness-vs-tokens gate).
4. **Experiment attribution.** `experiment.py --cutover <date>` over transcripts
   spanning the cutover reports per-task-class and CUPED-adjusted deltas with CIs
   for the continuous KPIs (tokens, latency, Opus-share, `$est`), and pooled
   rare-event rates labeled with their detectability window. *Target:* a >=15%
   change in a continuous KPI is detected within the developer's real variance;
   rare-event rows that are underpowered render gray with a "needs weeks"
   annotation rather than a false green/red.
5. **Cadence documented.** The repo carries a weekly keep / iterate / revert review
   checkpoint (in `telemetry/README.md` or a `REVIEW.md`) so "measure over several
   days" resolves to a defined decision. *Target:* one documented cadence with the
   exact command (`agentic-cfg gain`) and the keep/iterate decision rule.

These targets reproduce the digest's `scorecard` verification verbatim
("regenerating on two different days yields a diff readable in under a minute; all
6-10 scorecard rows populate from live transcripts", `/tmp/research_digest.json`,
line 72) and bind them to the balanced decision rule.

## References

- [CursorBench — how Cursor compares model quality](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench) — supports the single correctness-vs-token scorecard and the balanced decision rule (a token win that loses correctness is a regression).
- [Optimizely — What is CUPED](https://www.optimizely.com/optimization-glossary/what-is-cuped) — supports CUPED as standard A/B variance reduction (~30-50% sample-size cut) and the use of a pre-period mean as covariate; also grounds the P2-11 caveat that CUPED helps continuous, not rare-binary, metrics.
- [arXiv:2510.03468 — variance reduction / sensitivity in experimentation](https://arxiv.org/abs/2510.03468) — peer-reviewed integration of CUPED-style variance reduction for low-sample sensitivity, supporting the task-mix-normalized longitudinal design.
- [OpenTelemetry GenAI semantic conventions — metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md) — supports naming the scorecard's latency/token rows against `operation.duration` / `token.type` so the artifact lines up with real observability tools (the OTel aliasing landed in ADR-0002).
- [Langfuse — evaluation overview](https://langfuse.com/docs/evaluation/overview) — supports online-evaluation of live traces as the model the scorecard follows locally (zero-LLM transcript analysis rather than a hosted dashboard), the basis for rejecting Option 4.
- `/tmp/research_digest.json` (`synthesis.scorecard`, lines 353-425; the scorecard and experiment proposals, lines 51-72; critique P0-1/P0-2/P0-3, P2-11) — the cited synthesis this ADR encodes, including the verified model-mix and session-reconstruction facts that force the cost-framing correction and the hard ADR-0001 dependency.

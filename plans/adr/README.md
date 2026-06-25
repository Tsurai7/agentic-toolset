# Decision log — measure-and-uplift program

This directory holds the Architecture Decision Records (ADRs) for a focused
program with two goals the owner set:

1. **Uplift weak models** — make Sonnet 4.6 and especially Haiku 4.5 measurably
   smarter when driven by this config.
2. **Cut heavy-model consumption and latency** — route routine work off Opus 4.8
   and keep context lean, so the work stays under the subscription's usage caps and
   responds faster.

The format and rationale for using ADRs is
[ADR-0000](0000-use-architecture-decision-records.md). Each ADR (the *what/why*)
links 1:1 to an implementation plan in [`plans/impl/`](../impl/) (the *how*). This
program is **additive** to the existing planning corpus
([`plans/00-master-plan.md`](../00-master-plan.md) … [`plans/05-test-coverage.md`](../05-test-coverage.md));
it does not modify those documents and references them read-only.

## Why this program exists — the gaps the prior corpus will not close

The existing `plans/00–05` are a strong review: severity-ranked, deduplicated,
and reconciled into a P0–P3 roadmap (stop the bleeding → robust Go foundation →
measure → compound). But they answer a different question than the owner's. Their
measurement story (P2) is the **synthetic** eval harness — A/B in a throwaway
repo — and the one component that reads the owner's **real** daily sessions
([`telemetry/`](../../telemetry/)) is orphaned from the roadmap and measures only
tokens/cache/cost. The owner's question is longitudinal and real-world: *applied
to my daily Claude Code, did weak models get smarter and Opus get cheaper, over
several days, by an explicit metric?* These nine gaps block that question and are
each owned by an ADR below.

| Gap | What the prior plans miss | Goal blocked | Owned by |
|-----|---------------------------|--------------|----------|
| **G1** | Real-usage telemetry is an afterthought; `telemetry/` is not in the P0–P3 roadmap and there is no captured **before** baseline, so no real-session delta is attributable. | both | [ADR-0001](0001-real-usage-measurement-baseline.md) |
| **G2** | The measurement **unit is wrong**: `report.collect()` counts `.jsonl` *files*, but subagent sidechains are separate files, so a fanned-out task is mis-counted; model-mix and `<synthetic>` records confound any "Opus share". | both | [ADR-0001](0001-real-usage-measurement-baseline.md) |
| **G3** | **Quality/intelligence is unmeasured in real sessions** — telemetry is tokens/cache/cost only; no turns-to-completion, tool-error, edit-revert, or correction rate. "Haiku got smarter" is unfalsifiable. | weak-model | [ADR-0002](0002-quality-latency-proxies.md) |
| **G4** | **Latency is named but instrumented nowhere**, though session timestamps and the stream-json `duration_ms` are present. | heavy-model | [ADR-0002](0002-quality-latency-proxies.md) |
| **G5** | No **falsifiable, controlled** signal: the harness runs single-shot A/Bs (no time series, no reliability number, no weak-vs-strong differential, no judge-free check, uncalibrated judge). | both | [ADR-0003](0003-eval-backbone-canary.md) |
| **G6** | Metrics are scattered across `BENCHMARKS.md`, `report.py`, `gate.py`; there is **no single balanced scorecard** and no `agentic-cfg gain` surface, and no task-mix-normalized experiment design. | both | [ADR-0004](0004-gain-scorecard-experiment.md) |
| **G7** | **No model-tiering / routing strategy** — the plans *measure* Haiku (MAT-03) and ship one subagent (MAT-04) but give zero operational guidance to shift work off Opus. The cost goal has a measurement plan but no mechanism. | heavy-model | [ADR-0005](0005-model-tiering-routing.md) |
| **G8** | **Weak-model uplift is measured, never engineered** — nothing in the config *causes* uplift (no plan-first, self-critique, structured-output, or edit-lint scaffolds). | weak-model | [ADR-0006](0006-weak-model-reasoning-uplift.md) |
| **G9** | **Installed ≠ firing**, and there is no feedback loop: no real-session adoption metric (do `rtk`/`ast-grep`/skills/hooks actually fire?) and no mechanism to turn observed failures into eval cases, though `PLAYBOOK.md` mandates exactly that. | both | [ADR-0007](0007-adoption-flywheel.md) |

## The real baseline (measured, not assumed)

Every decision below is grounded in the owner's actual transcripts, not generic
guidance. The headline facts (from [`telemetry/report.py`](../../telemetry/report.py)
over the live `~/.claude/projects` corpus):

- **Cache hygiene is already maxed:** weighted cache hit rate **96.3%** over a
  40-session sample (range 78–99%). The cost lever is therefore **model routing and
  output/context volume, not cache**.
- **Cost is concentrated in a few long Opus sessions.** Over 40 sessions, more than
  half of the API-equivalent total came from two long Opus sessions that — verified
  by their edited file basenames (`run.py`, `gate.py`, `report.py`, `PLAYBOOK.md`) —
  were **agentic-cfg development itself** (deep research plus building the
  evals/telemetry harness), run from a worktree under the `team-mtp/infra/boss-mr-infra-v2`
  path. The expensive pattern is the long "research + multi-file build" Opus session
  with a large cache-read context.
- **The model mix is not Opus-only:** a 205-session corpus is Opus 5421 / Haiku 1335
  / Sonnet 219 / `<synthetic>` 53 assistant records, with `isSidechain=true` on **28%**
  of records. Haiku is *already* heavily used (mostly as background sidechains), so a
  naïve "Opus share > 80%" baseline is empirically wrong — the routing KPI must be
  **main-thread, sidechain-excluded, `<synthetic>`-filtered** (ADR-0001).
- **User turns are mostly tool results:** 3496 `tool_result`-only versus 452
  text-bearing, so the correction heuristic runs only on the 452 and needs a Russian
  lexicon (ADR-0002).

### A correction on cost framing — dollars are not the owner's bill

The `$` figures in [`telemetry/report.py`](../../telemetry/report.py) come from a
hardcoded `PRICING` table of **API list prices** and the script itself warns they
are "ESTIMATES … for relative comparison, not invoices." The owner is on a flat
**$200/month Claude Max** subscription: there is no per-token billing — usage is
governed by **rolling and weekly caps** (Opus tighter than Sonnet/Haiku; Claude
Code spends from the same quota). Therefore the **primary cost KPI is Opus token
consumption / main-thread Opus token-share** (a proxy for rate-limit headroom and
latency), and `$est` is kept only as a clearly-labeled **secondary "API-equivalent
resource proxy (not the bill)"**. Goal 2 is framed as *consume less Opus, stay
under the caps, respond faster* — never *spend fewer dollars*.

## The decision log

| ADR | Decision | Goal | Status | Implementation |
|-----|----------|------|--------|----------------|
| [0001](0001-real-usage-measurement-baseline.md) | Make telemetry a first-class pillar; capture a frozen pre-install baseline; reconstruct logical sessions; fix the cost unit to a main-thread, sidechain-excluded, `<synthetic>`-filtered Opus share | both | Proposed | [impl/01](../impl/01-baseline-and-session-reconstruction.md) |
| [0002](0002-quality-latency-proxies.md) | Add four model-segmented quality proxies (tool-error, turns, edit-revert, user-correction) and honest wall-clock + true `duration_ms` latency | weak-model, heavy-model | Proposed | [impl/02](../impl/02-quality-latency-proxies.md) |
| [0003](0003-eval-backbone-canary.md) | A deterministic-first eval backbone: differential-uplift harness, scheduled canary, `pass^k` reliability, trajectory + scored grading, judge calibration | both | Proposed | [impl/03](../impl/03-eval-backbone-canary.md) |
| [0004](0004-gain-scorecard-experiment.md) | One balanced scorecard via `agentic-cfg gain`, plus a CUPED-normalized longitudinal before/after experiment | both | Proposed | [impl/04](../impl/04-gain-scorecard-experiment.md) |
| [0005](0005-model-tiering-routing.md) | A model-agnostic in-config tiering/routing policy (routing rule, `effort=medium` default, architect/editor split, single-threaded default), gated by the deterministic canary | heavy-model | Proposed | [impl/05](../impl/05-model-tiering-routing.md) |
| [0006](0006-weak-model-reasoning-uplift.md) | Reasoning-uplift scaffolds (plan-first, conditional self-critique, answer-shapes, edit-lint hook) plus model-aware render so they uplift Haiku without taxing Opus | weak-model | Proposed | [impl/06](../impl/06-weak-model-reasoning-uplift.md) |
| [0007](0007-adoption-flywheel.md) | A real-session adoption/conformance metric and a harvester that turns observed failures into draft eval cases | both | Proposed | [impl/07](../impl/07-adoption-flywheel.md) |

## Sequencing — four waves, gated by the existing P0–P3 roadmap

The single most important ordering constraint: **the baseline (Wave 0) and the
differential harness (Wave 1) precede all content work (Wave 2)** — they are the
difference between measured impact and asserted impact.

```
WAVE 0  Instrument before touching anything (BEFORE the team's P0 install)
        ADR-0001 baseline corpus + session reconstruction + corrected unit
        ADR-0002 quality proxies + latency        [read-only, stdlib, P0-independent]

WAVE 1  Measurement backbone (parallel with the team's BUG/PORT/GO P0–P1 work)
        ADR-0003 differential harness + canary track + pass^k + calibration

WAVE 2  The two content levers, now each falsifiable
        ADR-0005 model-tiering / routing   (Goal 2)  — gated by the Wave-1 canary
        ADR-0006 reasoning scaffolds       (Goal 1)  — gated by the Wave-1 harness
                 + model-aware render so scaffolds do not tax Opus's prefix/cache

WAVE 3  Close the loop and roll up
        ADR-0004 agentic-cfg gain scorecard + CUPED experiment
        ADR-0007 adoption metric + harvest.py feedback flywheel
```

Cross-cutting rules: every Wave-2 content change ships its required conformance +
value case (per [`AGENTS.md`](../../core/instructions/AGENTS.md) lines 54–56);
nothing is accepted if it improves cost while regressing judged correctness or a
quality proxy (the correctness-vs-tokens gate); and `gate.py` runs before/after
every always-on prefix edit so a cache-hit regression blocks the change.

## The balanced scorecard — `agentic-cfg gain`

The owner reads one artifact in under a minute to decide keep / iterate / revert.
`agentic-cfg gain` (a `bin/agentic-cfg` shell dispatcher now, folding into the Go
`agentic gain` subcommand later per GO-15/GO-16) regenerates this from live
transcripts. No row is hand-typed; each traces to a telemetry metric or eval case.

| # | Metric | Goal | Source | Target |
|---|--------|------|--------|--------|
| 1 | **Main-thread Opus token-share** (headline cost KPI) | heavy-model | `report.py --by-model` | ≥ 20 pp below baseline on routine sessions, quality proxies not regressed |
| 2 | API-equivalent resource proxy / task (`$est`, *not the bill*) | heavy-model | `report.py` cost ÷ task-class | ≥ 20% lower vs baseline at `treatment_not_worse` quality |
| 3 | Per-turn wall-clock latency p50/p95 (per tier) | heavy-model | `report.py` timestamps + eval `duration_ms` | cheap-task median −15%; hook overhead < 50 ms/call |
| 4 | Weighted cache hit rate | heavy-model | `gate.py` (existing) | stay ≥ 0.85; gate fails < 0.80 |
| 5 | Tool-error rate (per model) | weak-model (+ cost guard) | `report.py` (new) | gate fails if last-20-session rate > 8%; Haiku/Sonnet fall vs baseline |
| 6 | Edit-revert + user-correction rate (per model) | weak-model | `report.py` (new) | drop after the scaffolds land |
| 7 | Adoption: `rtk`-coverage, `ast-grep`-share, per-skill fire | both | `adoption.py` (new) | `rtk` ≥ 0.7, `ast-grep` ≥ 0.6, every expected skill > 0 |
| 8 | Weak-model differential uplift (weak − strong margin) | weak-model | `uplift.py` (new) | ≥ 0.20; on the 10-task canary Haiku +≥15 pp while Opus +<5 pp |
| 9 | Canary `pass@1` + `pass^5` reliability (Haiku) | both | `evals/canary/history.jsonl`, `run.py --k 5` | `pass@1` flat-or-up; `pass^5` ≥ 0.80 |

### How to measure over several days — the honest protocol

1. **Before the team's P0 install,** run `telemetry/snapshot.py` to freeze a 2–3 day
   baseline corpus (ADR-0001). Without a frozen *before*, no delta is attributable.
2. Apply the config. Each day, glance at `agentic-cfg gain`; review the full
   scorecard weekly and decide keep / iterate / revert.
3. **Statistical honesty (do not over-read a few days):** CUPED task-mix
   normalization (ADR-0004) reduces variance for **continuous** metrics (tokens,
   latency, cost proxy) and lets a ≥15% change surface in days — but it does little
   for **rare-event rates** (reverts, corrections, tool errors), which need a longer
   window or pooling across the canary. Real-session "latency" is **wall-clock
   including human think-time**, not model latency; true model latency comes only
   from the eval/canary `duration_ms`. The deterministic **canary** — not the noisy
   real-session proxies — is the primary, controlled quality signal and the blocking
   gate for routing changes.

## Reading order

Start here, then [ADR-0000](0000-use-architecture-decision-records.md) for the
format. Read the ADRs in numeric order; open an implementation plan when you are
ready to build that decision. Each ADR's *Validation* section names the eval case,
telemetry metric, or canary — with a target number — that confirms it worked.

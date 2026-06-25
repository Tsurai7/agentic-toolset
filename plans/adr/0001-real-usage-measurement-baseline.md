# ADR-0001: Measure on real usage with a captured baseline and correct measurement units

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** measurement, process
- **Supersedes:** —
- **Superseded by:** —
- **Related:** [ADR-0002](0002-quality-latency-proxies.md) (quality & latency proxies built on this corpus), [ADR-0004](0004-gain-scorecard-experiment.md) (the `agentic-cfg gain` scorecard that aggregates these units), [ADR-0005](0005-model-tiering-routing.md) (the routing rule whose KPI this ADR defines), the implementation plan [`plans/impl/01-baseline-and-session-reconstruction.md`](../impl/01-baseline-and-session-reconstruction.md), and the prior planning corpus [`plans/00-master-plan.md`](../00-master-plan.md) (P0 install roadmap, BUG-01..23 / PORT-01..12) and [`plans/05-test-coverage.md`](../05-test-coverage.md) (TEST-08 synthetic baseline this ADR contrasts with).

## Context and problem statement

The repository ships a telemetry harness — [`telemetry/report.py`](../../telemetry/report.py) and [`telemetry/gate.py`](../../telemetry/gate.py) — that already parses the JSONL transcripts Claude Code writes under `~/.claude/projects/**/<session>.jsonl` and reports token volume, cache hit rate, an estimated cost, a main-thread/subagent split, and a tool-call distribution. That harness is real and working, but it is **orphaned from the program**: [`plans/00-master-plan.md`](../00-master-plan.md) treats it as already-done Phase 0 plumbing, and no ADR or scorecard makes it the measurement pillar that decides whether a config change helped. Before a single uplift or routing change lands, three foundations have to be true, and today none of them are.

First, there is **no captured before-window**. `report.py` and `gate.py` read transcripts that were *already produced with whatever config was installed at the time*. The only "baseline" the planning corpus describes is the synthetic, fixed-prompt ablation in TEST-08 / MAT-01 ([`plans/05-test-coverage.md`](../05-test-coverage.md)), which measures a frozen prompt, not the owner's real daily mix. A before/after with no immutable "before" is not an experiment — any post-install delta is unattributable to config versus the natural drift of what the owner happened to work on that week.

Second, the **measurement unit is wrong in two ways that the real telemetry baseline proves empirically**:

- **Cost is framed in dollars that the owner does not pay.** The dollar figures in `report.py` come from a hardcoded `PRICING` table of API list prices (`report.py:36-40`: Opus `$15/$1.5/$75`, Sonnet `$3/$0.3/$15`, Haiku `$1/$0.1/$5` per MTok for input / cache-read / output), and `report.py` itself warns they are estimates "for relative comparison, not invoices" (`report.py:18-20`). The owner is on a flat $200/month Claude Max subscription, not API pay-as-you-go: spend is governed by usage limits and throttling (Opus has tighter rolling and weekly caps, and Claude Code draws from the same quota), not per-token billing. The headline cost KPI must therefore be **main-thread Opus token consumption / token-share** — a direct proxy for rate-limit headroom and latency — with the dollar estimate demoted to a clearly-labeled secondary "API-equivalent resource proxy, not the owner's bill."

- **The token-share denominator is computed over the wrong population.** A 205-session sample of the owner's own corpus contains Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 assistant records, with `isSidechain=true` on 28% of records. So Haiku is *already heavily used* — mostly as background and sidechain work the owner never consciously routed — and a naïve "Opus share is ~80–100%, drive it to 60%" baseline is empirically false. Worse, `report.collect()` (`report.py:179-189`) globs `**/*.jsonl` and `--last N` takes the N most-recent *files*; subagent transcripts are written as *separate* files under `.../subagents/...`, so one user task that fans out becomes many files and `--last 30` can be thirty fragments of one workflow. Every per-session metric is computed on the wrong unit over the wrong population.

Third, the same 40-session telemetry sample shows the **weighted cache hit rate is already 96.3%** (range 78–99%). Cache hygiene is essentially maxed, so the real levers are model routing and output/context volume — not cache. The measured cost concentration confirms where to aim: roughly $158 of the ~$300 API-equivalent over 40 sessions (more than half) came from just two long Opus "research + multi-file build" sessions that were `agentic-cfg` development work. The expensive pattern is long heavy-model sessions with huge cache-read context, not the owner's everyday coding.

This ADR makes `telemetry/` a first-class measurement pillar and fixes the unit *before* any metric is trusted: capture a frozen real-session baseline corpus before the P0 install, reconstruct logical sessions so per-session metrics mean something, and report a sidechain-excluded, `<synthetic>`-filtered, main-thread Opus token-share as the headline cost unit.

## Decision drivers

- **Goal 2 — consume less Opus, stay under subscription caps, respond faster.** The primary cost KPI must be main-thread Opus token-share/consumption (a rate-limit-headroom and latency proxy), never dollars. The metric has to be computed on a population that the routing rule can actually move.
- **Goal 1 — cardinally improve weak-model (Sonnet 4.6, Haiku 4.5) performance.** Every "Haiku got smarter" claim needs a frozen before-corpus to diff against; without it, uplift is unfalsifiable.
- **Balanced scorecard, never one KPI.** Both goals are weighted roughly equally ([ADR-0004](0004-gain-scorecard-experiment.md)). The unit fix is upstream of every row in that scorecard, so it must be correct before any single KPI is read.
- **Attribution over assertion.** A measured change must be attributable to the config and not to task drift. This requires an immutable before-window and a stable session unit — pure experiment hygiene.
- **Honesty of units.** Per the repo's own honesty principle, no number may imply a cost the owner does not pay or a population it was not computed over.

## Considered options

1. **Status quo — keep measuring live transcripts only, in dollars and per-file "sessions."** Run `report.py --last N` and `gate.py` against `~/.claude/projects` as they are, report `$est`, and treat each `.jsonl` file as a session. (Rejected.)
2. **Synthetic baseline only — lean on TEST-08 / MAT-01 fixed-prompt ablation as the "before."** Treat the deterministic eval harness as the reference and skip capturing real pre-install transcripts. (Rejected as insufficient on its own.)
3. **Capture a frozen real-session baseline corpus before P0 install, reconstruct logical sessions, and fix the cost unit to main-thread Opus token-share — `<synthetic>`-filtered and sidechain-corrected (chosen).** Add `telemetry/snapshot.py` to freeze the pre-install corpus, add a `--baseline` diff mode to `report.py` and `gate.py`, reconstruct sessions by grouping subagent files under their parent, and make the headline cost KPI a sidechain-excluded main-thread Opus token-share with `$est` relabeled as a secondary API-equivalent proxy.

## Decision outcome

**Chosen: Option 3 — capture a frozen baseline corpus before the P0 install, reconstruct logical sessions, and fix the measurement unit to a sidechain-excluded, `<synthetic>`-filtered, main-thread Opus token-share.** This is **Wave 0** of the program: it must land *before* the P0 install (the [`plans/00-master-plan.md`](../00-master-plan.md) BUG/PORT hook and install fixes), because once the new config is installed, the pre-config window is gone forever and every before/after number becomes unattributable.

The justification is first-principles experiment hygiene corroborated by how leading teams measure model and config changes. A before/after with no captured "before" is not an experiment; CursorBench's published methodology compares model quality against a *fixed, frozen* reference suite precisely so a change is attributable rather than confounded by drift ([Agent Wars, "How Cursor compares model quality with CursorBench"](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)). Capturing the immutable before-corpus is what lets the digest's target — "post-install fresh-input tokens/session down ≥15% and weighted cache hit% up vs the frozen corpus, with the delta attributable because the before-corpus is immutable" — be stated honestly instead of asserted.

The unit fix is grounded in the owner's own verified corpus, not assumption. Because the real mix is already Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 with 28% sidechain records, the routing KPI defined in [ADR-0005](0005-model-tiering-routing.md) — `opus_input_token_share` — will move for reasons unrelated to any routing rule (more or fewer background subagent spawns, more `<synthetic>` summarization records) unless the numerator and denominator exclude `isSidechain` and `model == "<synthetic>"` and report *main-thread interactive* share. The cost-framing correction (token-share as headline, `$est` as a labeled secondary proxy) follows directly from the flat-subscription reality: under Max, the binding constraint is the Opus rolling/weekly cap and the resulting throttling/latency, which token consumption proxies and dollars do not.

This ADR deliberately scopes itself to the *baseline + unit* layer. The quality and latency proxies that ride on this corpus are owned by [ADR-0002](0002-quality-latency-proxies.md); the scorecard that aggregates the corrected units is [ADR-0004](0004-gain-scorecard-experiment.md); the routing rule that consumes the corrected Opus-share KPI is [ADR-0005](0005-model-tiering-routing.md). What lands here is the corpus freeze (`telemetry/snapshot.py`), the `--baseline` diff on `report.py`/`gate.py`, logical session reconstruction in `collect()`, the `<synthetic>` filter and tier normalization, and the main-thread Opus-share KPI with honest cost framing.

### Consequences

**Good:**

- Every later before/after number becomes *attributable*: the pre-install window is frozen and immutable, so a measured delta is config-versus-config, not config-versus-task-drift.
- The headline cost KPI matches the owner's actual constraint (Opus consumption / rate-limit headroom under a flat subscription), and `$est` survives only as an honestly-labeled secondary proxy — no number ever implies a charge the owner does not pay.
- Per-session metrics (turns, latency, cost-per-task in later ADRs) finally have a correct unit, because subagent fragments are grouped under their parent session instead of inflating the file count.
- The routing KPI is computed over the population a routing rule can actually move (main-thread, interactive, real-model), so [ADR-0005](0005-model-tiering-routing.md) can be judged honestly.

**Cost:**

- A one-time pre-install discipline: the owner must run `telemetry/snapshot.py` and a 2–3 day before-window *before* installing the new config, which gates the P0 rollout on a measurement step.
- Net-new read-only code in `telemetry/` (snapshot, session reconstruction, baseline diff, filters) and a documentation pass in [`telemetry/INTEGRATION.md`](../../telemetry/INTEGRATION.md). All of it is stdlib and zero-token, matching the existing harness.

**Risks and mitigations** (these fold in the critique's P0 and minor confounds as named risks):

- **Risk R1 — routing-share confounded by the existing model mix (critique P0-1).** Because Haiku/Sonnet/`<synthetic>` records are already a large share, a blended "Opus share" moves for reasons unrelated to routing. *Mitigation:* the KPI is defined as **main-thread Opus input-token share** with `isSidechain == true` and `model == "<synthetic>"` records excluded from both numerator and denominator, computed on interactive sessions only; the frozen baseline corpus captures this real split so the scorecard target is calibrated to the owner's actual ~present share rather than an assumed 80–100%.
- **Risk R2 — "session" is the wrong unit (critique P0-2).** Subagent transcripts are separate files under `.../subagents/...`; `--last N` over `**/*.jsonl` mis-counts a fanned-out task. *Mitigation:* `collect()` reconstructs logical sessions by grouping sidechain child files under their parent session id / workflow root before any per-session metric, and the `--last N` window operates on reconstructed sessions, not raw files.
- **Risk R3 — `<synthetic>` records corrupt per-model token math (critique minor note).** 53 `<synthetic>` assistant records exist in the sample. *Mitigation:* filter `model == "<synthetic>"` everywhere model-segmented math is done (token-share, per-model rates), and normalize raw ids `claude-opus-4-8` / `claude-sonnet-4-6` / `claude-haiku-4-5-20251001` to tier labels (`opus` / `sonnet` / `haiku`) so the routing KPI and the differential harness in [ADR-0003](0003-eval-backbone-canary.md) key on stable tier names.
- **Risk R4 — adoption/share baseline assumed to be zero (critique minor note).** The corpus already contains some rtk/ast-grep usage, so assuming a zero baseline inflates "improvement." *Mitigation:* `snapshot.py` freezes the *real* pre-install rate; later ADRs diff against that captured number, never against an assumed zero.
- **Risk R5 — dollars misread as a bill.** *Mitigation:* the cost-framing correction is enforced in output: `report.py`/`gate.py` label `$est` as "API-equivalent resource proxy (not the owner's bill)" and surface main-thread Opus token-share as the primary cost line.

## Pros and cons of the options

**Option 1 — status quo (live transcripts, dollars, per-file sessions).**
*Pros:* zero new code; the harness already runs. *Cons:* fatal for attribution — no frozen before-window, so post-install deltas confound config with task drift; the per-file "session" double-counts fanned-out subagent workflows (critique P0-2); the dollar headline implies a charge the owner does not pay; the Opus-share denominator includes sidechain and `<synthetic>` records, so the routing KPI is uninterpretable (critique P0-1). Rejected.

**Option 2 — synthetic baseline only (TEST-08 / MAT-01).**
*Pros:* deterministic, repeatable, already partly designed; useful as a controlled signal. *Cons:* a fixed-prompt ablation cannot capture the owner's real daily task mix, so it cannot attribute a *real-usage* change to the config; it answers "did the prompt change behavior on this frozen prompt," not "did my real work get leaner/smarter." It is complementary to, not a substitute for, a captured real-session baseline. The eval/canary backbone in [ADR-0003](0003-eval-backbone-canary.md) owns the synthetic controlled signal; this ADR owns the real-usage corpus. Rejected as a standalone baseline.

**Option 3 — frozen real-session baseline + session reconstruction + corrected unit (chosen).**
*Pros:* makes every downstream delta attributable (immutable before-corpus); fixes the unit to match the owner's real constraint (Opus consumption under a flat cap) and real population (main-thread, sidechain-excluded, `<synthetic>`-filtered); gives per-session metrics a correct unit via reconstruction; calibrates the routing KPI to the owner's actual share. *Cons:* a one-time pre-install snapshot discipline and net-new read-only code. The cons are small and one-time; the pros are prerequisite to the entire program.

## Validation — how we confirm it worked

This ADR is "done" only when its falsifiable checks pass in the repo's own harness, with target numbers:

1. **Baseline corpus exists and is immutable.** `python3 telemetry/snapshot.py` produces a gitignored `telemetry/baseline/<date>-<repo-sha>/` corpus copied from `~/.claude/projects/**/*.jsonl`, tagged with capture date and repo SHA, captured **before** the P0 install. *Target:* a documented 2–3 day before-window exists on disk and is referenced by SHA; re-running `snapshot.py` never mutates an existing tagged corpus (append-only).
2. **Baseline diff runs.** `python3 telemetry/report.py --baseline telemetry/baseline/<tag> --last 30` emits a per-metric delta table (live window vs frozen corpus). *Target:* post-install, fresh-input tokens/session down ≥15% and weighted cache hit% not below the frozen number, with the delta attributable because the before-corpus is immutable.
3. **Session reconstruction is correct.** `python3 telemetry/report.py --last 30 --json` groups subagent (`.../subagents/...`, `isSidechain`) files under their parent session, so a fanned-out workflow appears as **one** reconstructed session, not many. *Target:* a known fanned-out workflow in the corpus reports a single reconstructed session whose subagent token share is non-zero; the reconstructed session count is strictly ≤ the raw `.jsonl` file count for any window containing a fan-out.
4. **Corrected headline cost unit.** `report.py --json` emits `main_thread_opus_input_token_share` computed with `isSidechain == true` and `model == "<synthetic>"` excluded from numerator and denominator, with `$est` relabeled "API-equivalent proxy (not the owner's bill)." *Target:* the share is in `[0, 1]` and is *lower* than the naïve blended share on the same window (because Haiku/sidechain records are excluded); `gate.py --baseline` exposes the same corrected share as the cost line. This becomes the baseline value the [ADR-0005](0005-model-tiering-routing.md) routing rule is judged against and the [ADR-0004](0004-gain-scorecard-experiment.md) scorecard reads.
5. **Filters applied everywhere.** No `<synthetic>` record contributes to any model-segmented token or share number; raw model ids are normalized to tier labels in `--json`. *Target:* `--json` model keys are `{opus, sonnet, haiku}` (plus an explicit `synthetic_excluded` count), never raw ids, and never `<synthetic>`.

## References

- [Agent Wars — *How Cursor compares model quality with CursorBench*](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench) — supports the chosen option's core claim that a *frozen reference corpus* is what makes a model/config change attributable rather than confounded by drift; the model for the immutable before-window.
- [Optimizely — *What is CUPED?*](https://www.optimizely.com/optimization-glossary/what-is-cuped) — supports treating a captured pre-period as the covariate for variance-reduced before/after analysis; the baseline corpus here is the prerequisite the CUPED-style longitudinal analysis ([ADR-0004](0004-gain-scorecard-experiment.md)) builds on.
- [`telemetry/report.py`](../../telemetry/report.py) (the repo's own harness) — primary source for the unit problem: the `PRICING` table at `report.py:36-40`, the self-described "estimates … not invoices" warning at `report.py:18-20`, the per-file glob in `collect()` at `report.py:179-189`, and the existing main/sub split keyed on `isSidechain` at `report.py:99` — the evidence that the cost unit and session unit are wrong as shipped.

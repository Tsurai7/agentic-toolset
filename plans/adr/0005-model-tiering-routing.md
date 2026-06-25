# ADR-0005: Route routine work off Opus with a model-tiering policy guarded by a deterministic weak-agent gate

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** cost-tiering, weak-model
- **Related:** [ADR-0001](0001-real-usage-measurement-baseline.md) (the captured baseline and main-thread Opus-share unit this ADR's KPI depends on), [ADR-0002](0002-quality-latency-proxies.md) (the quality proxies that act as a secondary guard), [ADR-0003](0003-eval-backbone-canary.md) (the deterministic canary this ADR makes a *blocking* gate), [ADR-0004](0004-gain-scorecard-experiment.md) (the balanced scorecard this routing KPI feeds), [ADR-0006](0006-weak-model-reasoning-uplift.md) (the reasoning scaffolds that make the weak tier trustworthy enough to route to), [ADR-0007](0007-adoption-flywheel.md) (the adoption metric this ADR extends to detect a strong model ignoring the routing rule). Implementation: [plans/impl/05-model-tiering-routing.md](../impl/05-model-tiering-routing.md). Prior corpus (read-only): MAT-04 (one locked read-only research subagent), MAT-07 (byte-stable render golden), MAT-10 (weak-agent regression gate), TEST-11 (per-arm token capture).

## Context and problem statement

This repository has **zero routing guidance today**. [`core/instructions/AGENTS.md`](../../core/instructions/AGENTS.md) lists six global defaults at lines 11–16 covering search, shell, commits, PRs, and verification — but nothing tells the agent *which model tier* a task belongs on, when to escalate to the heavy tier, or when to fan out into subagents. Every decision about model strength is made implicitly by whatever model the session happened to start in.

That matters because model selection, not cache hygiene, is now the dominant cost lever. The owner's verified 40-session telemetry sample shows a weighted cache hit rate of **96.3%** (range 78–99%) — cache hygiene is essentially maxed, so there is no headroom left there. What *is* left is the model mix and the output/context volume. The owner runs on a flat Claude Max subscription, so the governing constraint is not a per-token invoice but **Opus usage limits and latency** (Opus carries tighter rolling and weekly caps, and Claude Code spends from the same quota). The primary cost KPI for Goal 2 is therefore **main-thread Opus token consumption / Opus token-share**, a proxy for rate-limit headroom and responsiveness — not dollars. The dollar figures in [`telemetry/report.py`](../../telemetry/report.py) come from a hardcoded `PRICING` table of API list prices (`report.py:36-40`) that the file itself warns are "ESTIMATES … for relative comparison, not invoices"; we keep `$est` only as a clearly labeled secondary API-equivalent resource proxy, never as the owner's bill.

The empirical baseline also corrects a naive assumption. Across a 205-session corpus the assistant-record model mix is **Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53**, with `isSidechain=true` on **28%** of records. Haiku is *already* heavily used, mostly as background and sidechain work the owner never consciously routed. So a "Opus share is >80%, drive it down" framing is empirically wrong; the lever is the **main-thread, interactive, sidechain-excluded, `<synthetic>`-filtered** Opus share, which is the only share the routing policy can actually move and the only one whose movement is attributable to a routing decision rather than to a change in background subagent spawning.

The gap this ADR closes is the *policy* that decides tiers, plus the guard that prevents that policy from silently trading correctness for cheapness. The single biggest risk of any routing rule is that it routes work to a weaker model that quietly produces worse output, and the personal-usage quality proxies are too noisy at this sample size to catch it inside a measurement week. The policy is worthless without a deterministic guard.

## Decision drivers

- **Goal 2 is primary here** — cut Opus consumption and latency so the owner stays under subscription caps and gets faster responses. This ADR is the dominant cost lever in the program.
- **Goal 1 is a hard guard, not an afterthought** — routing routine work to a weaker model must not cardinally lower quality. A cheaper model that needs more turns, more corrections, or produces subtly wrong diffs is not actually cheaper and violates the balanced scorecard.
- **Balanced scorecard, never one KPI** — a routing change is accepted only if the main-thread Opus-share drop comes *with* the weak-agent canary staying green. Cost wins are rejected if they regress judged correctness or the quality proxies (the program's cross-cutting correctness-vs-tokens rule).
- **Model-agnostic, byte-stable, cache-safe** — the rule must survive model upgrades (tier-relative language, not model names baked into the decision) and must not depress the already-instrumented cache-hit rate when it adds bytes to the always-on prefix (MAT-07).
- **Attributable** — the routing KPI must be computed on the correct unit (main-thread, sidechain-excluded, `<synthetic>`-filtered) or it will move for reasons unrelated to the rule.

## Considered options

1. **Status quo — no routing rule.** Leave model selection implicit; rely on the owner to remember to switch models. (Rejected.)
2. **A hardcoded model-name routing table.** Write "use claude-haiku-4-5 for renames, claude-opus-4-8 for refactors" directly into AGENTS.md. (Rejected.)
3. **An external classifier/router process** (RouteLLM-style trained router, or a cheap LLM that classifies each task and dispatches). (Rejected for this repo.)
4. **A model-agnostic in-config tiering policy: a short always-on rule plus a `model-routing` skill with a tier decision table, an effort-default convention, a write-path split, a single-threaded-by-default rule, and an Opus-share KPI — all gated by the deterministic canary as a blocking weak-agent regression test.** (Chosen.)

## Decision outcome

**Chosen: Option 4 — a model-agnostic in-config tiering policy, guarded by the deterministic canary.**

The policy has five parts, each backed by a primary source and each verified by the harness before and after it lands.

**(a) An always-on routing rule plus a `model-routing` skill with a tier decision table in tier-relative language.** A short rule is added to the AGENTS.md global defaults; the detail lives in a new [`core/skills/model-routing/SKILL.md`](../../core/skills/model-routing/SKILL.md) whose decision table maps task classes to tiers without naming models: mechanical/boilerplate/format/rename/search-and-summarize/conventional-commit work goes to the **cheap tier**; a standard single-feature implementation goes to the **mid tier**; ambiguous, multi-file blast-radius, architecture, or hard-debugging work goes to the **heavy tier**. An explicit "escalate to heavy only when X, Y, Z" clause and a **~10–20% heavy-tier session budget** keep escalation deliberate. Capability-first-then-downscale ([OpenAI, *A Practical Guide to Building Agents*](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)), a three-tier cheap-router cascade ([Verdent, *Gemini Flash-Lite vs Flash vs Pro*](https://www.verdent.ai/guides/gemini-3-1-flash-lite-vs-flash-vs-pro)), and [RouteLLM](https://lmsys.org/blog/2024-07-01-routellm/) ([arXiv:2406.18665](https://arxiv.org/abs/2406.18665)) converge: routing a third of routine sub-tasks off the heavy tier cuts blended cost 35–70% at roughly 95% of quality, given the ~5× Opus/Sonnet and ~15× Opus/Haiku input-price gap visible in the repo's own `PRICING` table (`report.py:36-40`). RouteLLM's transferability result is why the phrasing is tier-relative — it survives the next model swap. The built-in Claude Code **Explore subagent (Haiku, read-only)** is named as the canonical cheap-exploration tier ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)).

**(b) Opus effort=medium as the default for routine agentic coding, escalate-on-hard.** A one-line convention defaults Opus to medium effort for routine work and escalates to high/max only when a task is verifiably hard or a medium attempt fails verification. Anthropic reports that **Opus at medium effort matches Sonnet's best SWE-bench Verified score using 76% fewer output tokens, and at high beats Sonnet by 4.3 points using 48% fewer** ([Anthropic, *Claude Opus 4.5*](https://www.anthropic.com/news/claude-opus-4-5)); because **Opus 4.8 defaults effort to high** ([Claude models overview](https://platform.claude.com/docs/en/about-claude/models/overview)), the saving is opt-in and currently unclaimed. Output tokens are the most expensive class ($75/MTok on Opus in the repo table), so this is the single biggest per-task heavy-model lever. The convention is composed with the existing "think before coding" principle so the two do not both maximize thinking.

**(c) An architect/editor write-path split.** The skill documents the architect-reasons / editor-emits-the-diff pattern: the heavy tier describes the change in prose and a cheaper tier converts it to a well-formed diff. Aider's leaderboard ablation shows the split **raises pass rate for every architect model** (Sonnet+Sonnet 80.5% vs 77.4%; o1-mini+GPT-4o 70.7% vs 61.1%, +9.6pp) while the verbose edit-formatting tokens bill at the cheap editor's rate ([Aider, *Separating code reasoning and editing*](https://aider.chat/2024/09/26/architect.html)). It cuts cost *and* lifts correctness, and is distinct from MAT-04 (a read-only research subagent) — this is the *write* path.

**(d) Single-threaded by default; fan out only for read-only, decomposable breadth.** A short decision rule defaults to a single-threaded linear agent and spawns parallel subagents only when the task is read-only, decomposable, and exceeds one context window, with an explicit "do not fan out tightly-coupled coding tasks" clause. Cognition's *Don't Build Multi-Agents* argues single-threaded continuous context for coding ([Cognition](https://cognition.com/blog/dont-build-multi-agents)); Anthropic's multi-agent research system wins on breadth-first research but **burns roughly 15× the tokens** and is a poor fit for coupled coding ([Anthropic, *Multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system)). This avoids the largest accidental cost source on the dominant case. It complements MAT-04 by acting as the gating condition on when to spawn.

**(e) An `opus_input_token_share` + delegation-rate KPI by model and task class.** [`report.py`](../../telemetry/report.py) already reads per-message `msg.get('model')` into a `models` Counter (`report.py:96-98`) and buckets tokens by `isSidechain` (`report.py:99`). We derive `opus_input_token_share` = main-thread Opus input tokens / main-thread total input, `cheap_token_share`, and `delegation_rate` = subagent tokens / total — segmented by tier and by task class — and add an opus-share regression line to `gate.py` analogous to the existing cache-hit floor. Per the P0-1 correction the numerator and denominator **exclude `isSidechain` records and `model == "<synthetic>"`**, and the share is reported on main-thread interactive sessions only.

Targets from the digest: the routing rule classifies a labeled easy/medium/hard prompt set to the correct tier **≥90%** with **zero hard tasks mis-routed to the cheap tier**, and main-thread Opus token-share drops **≥20 percentage points** on routine sessions with the weak-agent gate (MAT-10) staying green ([digest workstream-2 verification](#references)).

### Consequences

**Good.**

- The dominant Goal-2 lever finally exists as content, not aspiration: routing routine work off Opus directly buys rate-limit headroom and lower latency under the Max subscription.
- Three of the five parts (effort default, architect/editor split, single-threaded rule) raise *or hold* correctness while cutting cost, so they serve both goals at once.
- The KPI is computed on the correct, attributable unit, so a measured drop traces to the rule rather than to background subagent churn.

**Cost.**

- Added always-on prefix bytes (the routing rule) and a new skill to maintain, plus the meta-cost of the value A/Bs that verify the rule (themselves Opus/Sonnet spend during the measurement window — kept small and periodic, deterministic checks preferred as the primary signal).
- A real behavioral cost: forcing routine work to a cheaper tier will occasionally produce a worse first attempt that escalates, spending more total than a straight-to-Opus run. The escalate-on-fail clause and the budget bound this.

**Risks and mitigations** (the critique points, folded in as named risks).

- **Risk P1-5 — routing to a weak model silently lowers quality, and the noisy real-session proxies miss it.** This is the biggest risk. *Mitigation:* the **deterministic canary from [ADR-0003](0003-eval-backbone-canary.md), not the noisy real-session proxies, is the primary quality guard and a blocking gate.** The canary (MAT-10 weak-agent regression gate) runs **before and after** any routing change; the change is rejected if the canary regresses, full stop. Real-session proxies are a secondary trend, never the gate.
- **Risk P1-8 — a strong model ignores the added always-on routing/effort/threading rules.** Vendor guidance warns that bloated instructions cause strong models to drop rules ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)), yet this ADR adds instruction content. *Mitigation:* extend [ADR-0007](0007-adoption-flywheel.md)'s adoption metric to **count routing/effort/threading conformance in real transcripts** (presence of escalation reasoning, effort flags, parallel-spawn events on coupled tasks), so "the rule is installed" is distinguished from "the rule fired."
- **Risk P2-12 — a cheaper editor produces subtly wrong but plausible diffs a verbosity-biased pairwise judge misses.** *Mitigation:* **every write-path routing value case includes an apply-and-run-tests deterministic check** (does the routed edit make a fixture test pass), not only a pairwise judge.
- **Risk P2-13 — the new always-on rule adds bytes to the AGENTS.md prefix and depresses the already-gated cache-hit rate before the model-aware-render mitigation lands.** *Mitigation:* run [`telemetry/gate.py`](../../telemetry/gate.py) **before and after each prefix edit**; a cache-hit drop is a **blocking regression**. Keep the rule short and byte-stable per MAT-07 (the byte-stability golden), and push detail into the skill file (loaded on demand) rather than the prefix.
- **Risk P0-1 — the Opus-share KPI is confounded by the existing model mix and sidechain churn.** *Mitigation:* the KPI is **main-thread, sidechain-excluded, `<synthetic>`-filtered, interactive-only**, and the [ADR-0001](0001-real-usage-measurement-baseline.md) baseline corpus captures the real pre-install split so the target is calibrated to reality, not to the empirically-wrong ">80%" assumption.

## Pros and cons of the options

**Option 1 — status quo (no routing rule).**
- Good: zero added prefix bytes; no cache-hit risk.
- Bad: leaves the dominant cost lever untouched; Opus-share stays at the mercy of whatever model a session opened in; Goal 2 unmet.

**Option 2 — hardcoded model-name routing table.**
- Good: unambiguous; trivially conformance-testable.
- Bad: breaks on every model rename/upgrade (e.g. `claude-haiku-4-5-20251001` → next id); violates the RouteLLM transferability lesson; couples policy to ephemeral identifiers.

**Option 3 — external classifier/router process.**
- Good: can be tuned and benchmarked independently; RouteLLM shows strong cost/quality trade-offs.
- Bad: heavyweight for a single-developer config repo; adds an extra LLM call (latency and the very Opus/Sonnet spend we are trying to cut) and a service to operate; not how this repo ships behavior (it ships skills and rules, not daemons).

**Option 4 — model-agnostic in-config policy, canary-gated (chosen).**
- Good: tier-relative language survives upgrades; ships as skill+rule like the rest of the repo; each part is independently cited and verified; the deterministic canary gives a hard quality floor; the KPI is attributable.
- Bad: relies on the agent actually obeying the always-on rule (mitigated by the ADR-0007 conformance metric); adds prefix bytes (mitigated by the gate.py cache check and keeping the rule short).

## Validation — how we confirm it worked

A routing change is accepted only when **all** of the following hold; cost wins alone never suffice.

1. **Tier-classification conformance (named eval case `model-routing-tier-classification`, conformance track).** A labeled easy/medium/hard prompt set is classified to the correct tier with `expect`/`expect_not` on the stated tier. **Target: ≥90% correct, with ZERO hard tasks mis-routed to the cheap (Haiku) tier.** A single hard-task mis-route to Haiku fails the gate regardless of the aggregate.
2. **Write-path value A/B with an apply-and-test check (named eval case `model-routing-architect-editor-writepath`, value track).** Same multi-file edit prompt, architect/editor split (treatment) vs single-Opus (control); pairwise judge for correctness **plus a deterministic apply-and-run-tests check** (closing P2-12). **Target: `treatment_not_worse` with ≥30% lower total cost at equal-or-better correctness over n≥5**, and the routed edit makes the fixture test pass.
3. **Effort-default value A/B (named eval case `model-routing-effort-medium`, value track).** Same coding prompt at effort=medium vs effort=high on Opus, pairwise-judged for parity with the `report.py` output-token delta from the stream-json result event (TEST-11 plumbing). **Target: medium achieves ≥90% judge win/tie while cutting output tokens ≥40%.**
4. **Single-threaded conformance (named eval case `model-routing-single-threaded-coupled`, conformance track).** A tightly-coupled multi-file coding task asserts the agent does **not** spawn parallel subagents. **Target: pass = single-threaded.**
5. **The blocking weak-agent canary (MAT-10, [ADR-0003](0003-eval-backbone-canary.md)).** The deterministic canary runs before and after the routing change. **Target: canary pass@1 flat-or-up; any regression blocks the change** (closing P1-5).
6. **Telemetry KPI (`telemetry/report.py --by-model --by-task-class`, the `gain` scorecard row in [ADR-0004](0004-gain-scorecard-experiment.md)).** **Target: main-thread, sidechain-excluded, `<synthetic>`-filtered `opus_input_token_share` drops ≥20 percentage points on routine sessions vs the [ADR-0001](0001-real-usage-measurement-baseline.md) frozen baseline**, with no rise in the tool-error / edit-revert proxies, and `gate.py` failing if main-thread Opus-share on routine projects exceeds the calibrated ceiling.
7. **Cache-hit non-regression (`telemetry/gate.py`, closing P2-13).** Run before and after the prefix edit. **Target: weighted cache hit rate stays ≥0.85; a drop below the floor is a blocking regression.**
8. **Rule-conformance in real transcripts ([ADR-0007](0007-adoption-flywheel.md) extension, closing P1-8).** **Target: routing/effort/threading conformance is non-zero and trends up in real sessions; a strong model silently dropping the rule is visible as a flat-zero conformance line.**

## References

- [OpenAI — *A Practical Guide to Building Agents* (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf) — supports capability-first-then-downscale tiering and the escalate-only-when clause.
- [Verdent — *Gemini 3.1 Flash-Lite vs Flash vs Pro*](https://www.verdent.ai/guides/gemini-3-1-flash-lite-vs-flash-vs-pro) — supports the three-tier cheap-router cascade and the cheap/mid/heavy decision table.
- [LMSYS — *RouteLLM*](https://lmsys.org/blog/2024-07-01-routellm/) and [arXiv:2406.18665](https://arxiv.org/abs/2406.18665) — supports the 35–70% blended-cost reduction at ~95% quality and the transferability argument for model-agnostic tier language.
- [Anthropic — *Claude Opus 4.5*](https://www.anthropic.com/news/claude-opus-4-5) — supports the effort=medium numbers: medium matches Sonnet's best SWE-bench Verified at −76% output tokens; high beats Sonnet by 4.3 points at −48%.
- [Claude models overview](https://platform.claude.com/docs/en/about-claude/models/overview) — supports that Opus 4.8 defaults effort to high, so the medium-default saving is opt-in.
- [Aider — *Separating code reasoning and editing*](https://aider.chat/2024/09/26/architect.html) — supports the architect/editor write-path split pass-rate ablation (Sonnet+Sonnet 80.5% vs 77.4%; o1-mini+GPT-4o +9.6pp).
- [Cognition — *Don't Build Multi-Agents*](https://cognition.com/blog/dont-build-multi-agents) — supports single-threaded-by-default for coupled coding tasks.
- [Anthropic — *Multi-agent research system*](https://www.anthropic.com/engineering/multi-agent-research-system) — supports the ~15× multi-agent token cost and the read-only-decomposable-breadth fan-out condition.
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices) — supports the built-in Explore (Haiku, read-only) cheap-exploration tier and the warning that bloated instructions cause strong models to ignore rules (the P1-8 risk).
- [Claude Code sub-agents](https://code.claude.com/docs/en/sub-agents) — supports the delegation-rate KPI derived from subagent transcripts.

# ADR-0007: Measure real-session adoption and harvest observed failures into regression guards

- **Status:** Proposed
- **Date:** 2026-06-26
- **Deciders:** repo owner (Tsurai7)
- **Tags:** adoption, process
- **Related:** [ADR-0001](0001-real-usage-measurement-baseline.md) (real pre-install baseline), [ADR-0002](0002-quality-latency-proxies.md) (failure-signature parser), [ADR-0003](0003-eval-backbone-canary.md) (canary rotation consumes harvested cases), [ADR-0005](0005-model-tiering-routing.md) (the routing/effort/threading rules whose conformance this measures), [ADR-0004](0004-gain-scorecard-experiment.md) (the scorecard that surfaces these KPIs). Implementation plan: [plans/impl/07-adoption-flywheel.md](../impl/07-adoption-flywheel.md). Prior planning corpus: MAT-09 (harness conformance), MAT-10 (weak-agent gate), TEST-10..14 (the hand-authored eval suite this flywheel feeds).

## Context and problem statement

Every other decision in this program adds capability — a routing rule (ADR-0005), a plan-first scaffold (ADR-0006), an edit-lint hook — and then proves it in the harness on *crafted* prompts. None of them answers the question that decides whether any of it matters in practice: **does the config actually fire in the owner's real work?** Installed is not the same as firing. A skill that never triggers, a hook that fails open, and a routing rule a strong model silently ignores all produce a perfectly green token report, because [`telemetry/report.py`](../../telemetry/report.py) measures tokens, cache, and cost — never whether the load-bearing behaviors occurred.

The repo already carries most of the raw material. [`report.py:84-85`](../../telemetry/report.py) parses every `tool_use` block into a `tools` Counter, but only ever prints it under `--by-tool`; it never derives "of the Bash calls, how many were `rtk`-prefixed" or "of the code searches, how many used `ast-grep`". So the adoption signal is one Counter away and has never been computed.

The second gap is that the repo's own discipline is not mechanized. [`evals/PLAYBOOK.md`](../../evals/PLAYBOOK.md) is explicit — "a case is born from a **real weakness you observed**" — yet all 14 current cases under [`evals/conformance/cases/`](../../evals/conformance/cases/) and [`evals/value/cases/`](../../evals/value/cases/) are hand-authored. Nothing bridges "a real session went badly" to "a committed regression guard". Without that bridge the eval suite is a frozen snapshot: it cannot track the weaknesses the owner is actually hitting this week, and the longitudinal canary (ADR-0003) trends against a synthetic set rather than the live failure surface.

The baseline matters here, and the owner's verified telemetry corrects a tempting assumption. Adoption is **not** zero before install: `rtk` and `ast-grep` already appear in the 205-session corpus, so claiming an "improvement from 0" would inflate the result. The real model mix (Opus 5421 / Haiku 1335 / Sonnet 219 / `<synthetic>` 53 assistant records, with `isSidechain=true` on 28% of records) means any adoption number must be computed on a reconstructed, sidechain-aware, `<synthetic>`-filtered population — the same correction ADR-0001 makes for every per-session metric. And of the 3948 user turns in the sample, only 452 are text-bearing (3496 are `tool_result`-only), so the "user immediately corrected the edit" failure signature must run only on those 452 and must include a Russian correction lexicon, because the owner works in Russian.

This ADR decides to build that missing process layer: a real-session adoption/conformance metric, and a feedback loop that harvests observed failures into draft eval cases for human review. It is the flywheel that turns one-time fixes into compounding, permanent regression guards over the multi-day measurement window.

## Decision drivers

- **Goal 1 — verify weak-model uplift actually lands.** A scaffold (ADR-0006) only helps if the skill fires; adoption is the leading indicator that a Goal-1 content edit took effect in daily work, before the noisy quality proxies can even register a trend.
- **Goal 2 — verify the cost levers are obeyed.** ADR-0005's routing, effort, and single-threading rules cut Opus consumption only if the agent follows them. The set's own critique warns that bloated always-on instructions get silently dropped by strong models — so "did Opus obey the routing rule" must be *measured*, not assumed.
- **Balanced scorecard, not one KPI.** Per ADR-0004, adoption and harvest serve both goals at once and feed one reviewable artifact; neither goal is optimized at the other's expense.
- **Compounding over the window.** A measurement program that only fixes today's failures plateaus. Turning each observed failure into a permanent eval guard makes uplift accumulate across the weeks of the experiment.
- **Honest, near-zero meta-cost.** Both tools must be offline, read-only, stdlib transcript analysis with no LLM calls, so the measurement layer does not itself spend Opus quota it is trying to protect.
- **No inflated baselines.** The pre-install adoption rate is non-zero and must be captured from ADR-0001's frozen snapshot, never assumed to be zero.

## Considered options

1. **Status quo — token report plus manual eyeballing.** Keep `report.py` token/cache/cost output and trust the owner to notice when a skill stops firing or the routing rule is ignored, and to hand-author eval cases when a session goes badly.
2. **Adoption metric only — count tool-prefix conformance, skip harvesting.** Add `telemetry/adoption.py` to compute `rtk`-coverage, `ast-grep`-share, per-skill fire counts, hook deny/rewrite counts, and the bounded-read ratio, but leave eval-case authoring fully manual.
3. **Adoption metric extended to rule conformance, plus an automated harvester feeding a quarantine (chosen).** Build `telemetry/adoption.py` to measure tool-prefix *and* ADR-0005 routing/effort/threading conformance in real transcripts, and `telemetry/harvest.py` to mine failure signatures into quarantined draft eval-case stubs for human review before promotion — wiring the loop the PLAYBOOK mandates and feeding ADR-0003's canary rotation.
4. **Live online evaluation via a hosted observability platform** (Langfuse / Phoenix online evals on streamed traces): instrument every session and score it with an LLM judge in production.

## Decision outcome

**Chosen: Option 3 — a real-session adoption metric extended to rule conformance, plus an automated failure harvester feeding a human-reviewed quarantine.**

Two new stdlib tools, both reusing `report.collect()` and the existing `tool_use` parsing, both read-only and zero-LLM:

- **[`telemetry/adoption.py`](../../telemetry/adoption.py)** computes, per the reconstructed and `<synthetic>`/sidechain-aware session population from ADR-0001: `rtk-coverage` = `rtk`-prefixed Bash ÷ total Bash; `ast-grep-share` = (`sg` | `ast-grep`) ÷ (`sg` + `grep`|`rg` code-search); per-skill fire count; hook deny/rewrite counts; and the bounded-read ratio (Grep/Glob/lines-range/signatures vs full Read). Critically, it extends past tool prefixes to **ADR-0005 rule conformance** — routing (escalation reasoning present on hard tasks, cheap-tier use on routine ones), effort (medium-default honored), and threading (no parallel-subagent fan-out on tightly-coupled coding tasks) — answering "did the agent obey the rules", not just "which tools ran".
- **[`telemetry/harvest.py`](../../telemetry/harvest.py)** scans recent transcripts for failure signatures — hook false-denies on the owner's *own* commands, text-bearing user turns that immediately correct or revert the prior assistant edit (English + Russian lexicon, restricted to the 452-style text turns), `tool_result` blocks with `is_error=true`, and grep-on-code the `ast-grep` rule should have caught — and emits draft eval-case JSON stubs (`id`, `prompt` = the real user message, `expect_not` = the observed bad behavior) into a new `evals/quarantine/` directory for human review before promotion to `evals/conformance/cases` or `evals/value/cases`.

**Why this option and not the others.** Option 1 fails on first principles: a green token report is exactly what a silently-non-firing skill and a fail-open hook both produce, so the status quo cannot detect the failure mode that most threatens the program. Option 2 is a real improvement but leaves the largest Goal-2 risk unguarded — the critique's P1-8 finding that strong models silently drop bloated instructions means we must *measure* routing/effort/threading conformance, not merely tool prefixes, or ADR-0005's cost claims rest on an unverified assumption. Option 4 contradicts the cost-framing correction outright: streaming every real session to a hosted LLM judge spends the Opus/Sonnet quota the whole program exists to protect, and (P2-9) the measurement layer must be zero-LLM offline analysis.

The evidence for the offline-trace-to-dataset loop is a widely-adopted practice. Langfuse documents the production-trace-to-dataset pipeline as the standard way to turn live failures into a regression set ([Langfuse, *Evaluation overview*](https://langfuse.com/docs/evaluation/overview); [Langfuse, *External evaluation pipelines cookbook*](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines)), and CursorBench derives its cases from real sessions rather than invented prompts ([Cursor / agent-wars, *How Cursor compares model quality with CursorBench*](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)). The adoption-rate-as-leading-indicator framing and the firing-vs-installed distinction follow Anthropic's sub-agent guidance that a configured behavior is only worth measuring once you confirm it actually triggers ([Anthropic, *Sub-agents*](https://code.claude.com/docs/en/sub-agents)). The expected impact is process, not a single token figure: the adoption table makes a regressed config edit (a session where coverage drops to ~0) visible the same day, and the harvester converts the observed-failure stream into committed cases at a rate of at least one promoted, FAIL-then-PASS case per measurement week — the mechanism that makes uplift compound instead of plateau.

### Consequences

**Good.**

- The single most important "is it firing in *my* real work" gap closes: every other measurement in this program is a synthetic A/B or a token count, and conformance (MAT-09) only tests firing on crafted harness prompts, never in daily sessions.
- Goal 2's cost claims become falsifiable at the behavior level — if Opus ignores the routing rule, the adoption table shows it, rather than the savings silently failing to materialize.
- The eval suite stops being a frozen synthetic set: harvested cases keep it tracking the owner's live weaknesses, and (P1-6) feed ADR-0003's canary rotation so the longitudinal trend is read against real failures.
- Both tools are stdlib, read-only, and zero-LLM, so the adoption/harvest layer adds essentially nothing to Opus consumption (P2-9) — it serves Goal 2 without taxing it.

**Cost.**

- Authoring and maintaining two ~80-150 line stdlib modules and a small set of failure-signature heuristics.
- A standing human-review obligation: harvested stubs are *drafts*, never auto-promoted, so the owner spends a few minutes per week triaging the quarantine.
- A modest schema surface: `evals/lint.py` must learn to skip (not fail on) the quarantine directory until a stub is promoted.

**Risks and mitigations.**

- **Risk (P1-8): the adoption metric measures only tool prefixes and misses whether the agent obeyed ADR-0005's routing/effort/threading rules — the exact rules a strong model is warned to silently drop.** Mitigation: `adoption.py` ships a rule-conformance layer from day one — escalation-reasoning presence on hard tasks, cheap-tier use on routine ones, effort-flag honoring, and parallel-spawn detection on coupled coding tasks — reported alongside the tool-prefix rates, so "did Opus obey the rule" is a measured column.
- **Risk (P1-6): harvested cases sit in quarantine and the canary stays a frozen synthetic set.** Mitigation: the harvest output directory is the documented feed for ADR-0003's canary rotation; the PLAYBOOK loop is wired so that a promoted case enters both the regression suite and the rotating canary pool, keeping the longitudinal signal anchored to real weaknesses rather than a static fixture (also blunts the Goodhart/overfit risk the critique raises against a tiny frozen canary).
- **Risk (P2-9): the measurement layer itself spends the Opus quota it is trying to protect.** Mitigation: stated honestly and enforced structurally — both `adoption.py` and `harvest.py` are zero-LLM, read-only, offline transcript analysis (stdlib only, matching `report.py`); no agent runs, no judge calls. The only LLM cost in the loop is the *eventual* `evals/run.py` execution of a *promoted* case, which is bounded by the one-per-week promotion target.
- **Risk (minor): the adoption baseline is treated as zero and the improvement is inflated.** Mitigation: the pre-install rate is captured from ADR-0001's frozen snapshot — `rtk` and `ast-grep` are already partly used in the corpus, so the week-1 number is reported as a delta against the real pre-install rate, never against an assumed zero.
- **Risk: failure-signature false positives flood the quarantine** (an `is_error` block that the agent recovered from cleanly, or an edit re-touch that was iteration, not a revert). Mitigation: signatures depend on ADR-0002's validated detectors; the user-correction signature runs only on text-bearing turns with the bilingual lexicon; every stub is human-reviewed before promotion, so a false positive costs a triage glance, never a bad committed case.

## Pros and cons of the options

**Option 1 — status quo (token report + manual eyeballing).**
Pros: zero new code; no maintenance. Cons: cannot detect a non-firing skill, a fail-open hook, or an ignored routing rule — all three produce a green report; leaves the PLAYBOOK's real-weakness loop entirely manual, so the eval set never tracks live failures and uplift plateaus.

**Option 2 — adoption metric only.**
Pros: closes the firing-vs-installed gap cheaply; reuses `report.collect()`. Cons: leaves P1-8 open (no routing/effort/threading conformance, so Goal-2 obedience is unverified) and P1-6 open (no harvesting, so the canary stays frozen and the suite cannot compound).

**Option 3 — adoption + rule conformance + harvester to quarantine (chosen).**
Pros: closes the firing gap *and* the rule-obedience gap; mechanizes the PLAYBOOK loop; feeds ADR-0003's canary rotation; zero-LLM and offline. Cons: two modules to maintain plus a standing weekly human-review obligation; a small `evals/lint.py` change to tolerate the quarantine directory.

**Option 4 — live online evaluation via a hosted observability platform.**
Pros: rich production-trace dataset and continuous scoring out of the box. Cons: directly violates the cost-framing correction and P2-9 — streaming every session to an LLM judge spends the very Opus/Sonnet quota the program protects; adds an external dependency and network egress of private transcripts; far heavier than a stdlib offline analysis for a single-developer config repo.

## Validation — how we confirm it worked

The decision is validated by two new telemetry surfaces and one process target, all on the reconstructed, `<synthetic>`/sidechain-aware population from ADR-0001:

- **Adoption metric (named surface: `telemetry/adoption.py --last 30 --json`).** Must emit non-zero counts for `rtk`, `ast-grep`, and ≥3 skills, with `rtk-coverage` and `ast-grep-share` in [0, 1], plus the routing/effort/threading conformance columns. **Targets for measurement week 1:** `rtk-coverage ≥ 0.7`, `ast-grep-share ≥ 0.6`, and per-skill fire-count `> 0` for every expected skill — each reported as a delta against the ADR-0001 pre-install rate, not against an assumed zero. A regression (a session where coverage drops to ~0 after a config edit) must be visible in the table.
- **Harvest loop (named surface: `telemetry/harvest.py --emit-stubs`).** Seeded against a transcript fixture containing one hook-false-deny and one edit-revert, it must produce two well-formed stubs that pass `evals/lint.py` schema validation after a one-line human edit. **Process target:** ≥1 harvested case promoted per measurement week, and that promoted case must reproduce **FAIL** under `evals/run.py` *before* the corresponding scaffold/rule fix and flip to **PASS** *after* it — the falsifiable proof that the loop captured a real, fixable weakness.
- **Goodhart guard (the gain scorecard, ADR-0004).** The adoption and harvest KPIs land as scorecard rows, and a promoted case is wired into ADR-0003's rotating canary pool, so no config change is accepted solely because a frozen canary improved.

## References

- [Langfuse, *Evaluation overview*](https://langfuse.com/docs/evaluation/overview) — supports the offline online-evaluation pattern and the firing-in-live-traces signal that the adoption metric implements as zero-LLM transcript analysis.
- [Langfuse, *External evaluation pipelines cookbook*](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines) — supports the production-trace-to-dataset feedback loop that `harvest.py` mechanizes from real failures into draft eval cases.
- [Cursor / agent-wars, *How Cursor compares model quality with CursorBench*](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench) — supports the "a case is born from a real session, not an invented prompt" principle that the harvester encodes and that `evals/PLAYBOOK.md` already mandates.
- [Anthropic, *Sub-agents*](https://code.claude.com/docs/en/sub-agents) — supports the installed-is-not-firing distinction and the need to confirm a configured behavior actually triggers before trusting it, the core motivation for the adoption metric.
- [Cursor, *Agent best practices*](https://cursor.com/blog/agent-best-practices) — supports keeping a rule only as long as a measurement shows it helps, the discipline the adoption-plus-harvest flywheel keeps true as the config grows.

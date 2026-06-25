# Impl 05 — Model-tiering and routing policy

**Implements:** [ADR-0005](../adr/0005-model-tiering-routing.md). **Wave:** 2. **Status:** Proposed.

This is the executable *how* for the routing policy. The *what/why* and the cited evidence live in the ADR; this plan carries file paths, line anchors, new functions, CLI flags, data formats, build order, and validation commands. Dollar talk stays honest: the primary KPI is **main-thread Opus token-share** (subscription rate-limit headroom and latency), and `$est` is a clearly labeled secondary API-equivalent proxy, never the owner's bill.

## Scope and deliverables

1. A short always-on **routing rule** appended to the AGENTS.md global defaults (`core/instructions/AGENTS.md:11-16`), kept byte-stable per MAT-07.
2. A new skill [`core/skills/model-routing/SKILL.md`](../../core/skills/model-routing/SKILL.md) holding the tier decision table (tier-relative language), the escalate-to-heavy-only-when clause, the ~10–20% heavy-tier budget, the effort=medium default, the architect/editor write-path split, and the single-threaded-by-default rule.
3. The **required conformance + value cases** for that skill, per `core/instructions/AGENTS.md:54-56` (a skill with no eval fails `evals/lint.py`).
4. The **`opus_input_token_share` + delegation-rate KPI** in [`telemetry/report.py`](../../telemetry/report.py), reusing the `models` Counter (`report.py:96-98`) and the `isSidechain` bucketing (`report.py:99`), with a `gate.py` opus-share floor.

Out of scope (owned elsewhere, referenced read-only): the deterministic canary harness and the weak-agent regression gate (ADR-0003 / MAT-10); the main-thread/sidechain session-reconstruction primitive and the frozen baseline corpus (ADR-0001); the per-arm token-capture plumbing (TEST-11); the routing/effort/threading transcript-conformance counter (ADR-0007). This plan *consumes* those; it does not rebuild them. This complements MAT-04 (one read-only research subagent) — MAT-04 is a subagent definition, this is the routing **policy**.

## File-by-file changes

### 1. `core/instructions/AGENTS.md` — add one routing default + a routing section

Append a seventh global default after line 16 (the list currently ends at item 6, "Done means verified"). Keep it to one short, byte-stable line that points at the skill; the detail must NOT live in the prefix (P2-13 cache hazard).

```markdown
7. **Model tier & escalation** — Match the model tier to the task: routine/mechanical work on the cheap tier, standard features on the mid tier, ambiguous or high-blast-radius work on the heavy tier. Escalate to heavy only on a verifiable hard signal; default Opus to medium effort; stay single-threaded unless the task is read-only and decomposable. See skill `model-routing`.
```

Add `model-routing` as one row in the Skills table (`AGENTS.md:58-68`):

```markdown
| `model-routing` | Task-class → model-tier decision, escalation budget, effort default |
```

**Byte-stability rule:** edit only these two insertions; do not reflow surrounding lines. Run `telemetry/gate.py` before and after (step in Build order) — a cache-hit drop blocks the change (P2-13).

### 2. `core/skills/model-routing/SKILL.md` — new skill (the policy detail)

Front-matter matches the existing skill convention (see `core/skills/ast-grep/SKILL.md`): a `name` and a `description` written so it auto-discovers on routing/tier/effort/fan-out questions. Body contents:

- **Tier decision table** in tier-relative language (no model ids in the decision column, per the RouteLLM transferability lesson):

  | Task class | Tier |
  |---|---|
  | mechanical / boilerplate / format / rename / search-and-summarize / conventional-commit | cheap |
  | standard single-feature implementation | mid |
  | ambiguous / multi-file blast radius / architecture / hard debugging | heavy |

  A short mapping note records the current binding (cheap ≈ `claude-haiku-4-5-20251001`, mid ≈ `claude-sonnet-4-6`, heavy ≈ `claude-opus-4-8`) in *one* clearly-marked line so the table stays model-agnostic while the agent can still act. The built-in Claude Code **Explore subagent (Haiku, read-only)** is named as the canonical cheap-exploration tier.

- **Escalate-to-heavy-only-when clause:** escalate when (a) a cheap/mid attempt fails verification, (b) the task is genuinely ambiguous after one clarification pass, or (c) blast radius spans 3+ coupled files. Otherwise stay on the assigned tier. A **~10–20% heavy-tier session budget** is stated as a self-check, not a hard limiter.

- **Effort=medium default:** "Default Opus to medium effort for routine agentic coding; escalate to high/max only when a task is verifiably hard or a medium attempt fails verification." Compose with the `core/principles` "think before coding" rule so the two do not both maximize thinking.

- **Architect/editor write-path split:** "For large multi-file edits, let the heavy tier describe the change in prose and a cheaper tier emit the diff." One sentence; the value case proves it.

- **Single-threaded-by-default rule:** "Default to a single linear agent. Spawn parallel subagents ONLY when the task is read-only, decomposable, and exceeds one context window. Do not fan out tightly-coupled coding tasks." Include the effort-scaling ladder (simple = 1 agent; comparison = 2–4 subagents; complex breadth = 10+, read-only only). This feeds MAT-04's subagent skill as a gating condition.

Keep the file focused — it is loaded on demand, so detail here costs no always-on prefix bytes.

### 3. Required eval cases (per `AGENTS.md:54-56`)

Case schema is enforced by [`evals/lib/cases.py`](../../evals/lib/cases.py): conformance cases need `id`, `prompt`, `rule`, and a non-empty `expect` or `expect_not` (`cases.py:48-53`); value cases need `id`, `prompt`, `hypothesis`, `skill`, `ablate`, `rubric`, and a `pass_condition` in `{treatment_preferred, treatment_not_worse}` (`cases.py:54-66`).

**Conformance — `evals/conformance/cases/model-routing-tier-classification.json`** (closes the routing-correctness gate):

```json
{
  "id": "model-routing-tier-classification",
  "rule": "agent classifies each task to the correct model tier and never routes a hard task to the cheap tier",
  "prompt": "For each task, name the tier (cheap/mid/heavy) you would run it on and why: (1) rename a variable across one file; (2) write a conventional-commit message; (3) implement a standard CRUD endpoint; (4) debug a race condition spanning 4 files; (5) redesign the auth module's interface.",
  "expect": ["routes the rename to the cheap tier", "routes the conventional-commit to the cheap tier", "routes the CRUD endpoint to the mid tier", "routes the race-condition debug to the heavy tier", "routes the auth redesign to the heavy tier"],
  "expect_not": ["routes the race-condition debug to the cheap tier", "routes the auth redesign to the cheap tier"]
}
```

This single case asserts ≥90%-style correctness and, via `expect_not`, the **zero-hard-tasks-to-cheap-tier** guard. The two hard tasks (4, 5) appearing in `expect_not` for the cheap tier is the falsifiable form of "ZERO hard tasks mis-routed to Haiku."

**Value — `evals/value/cases/model-routing-architect-editor-writepath.json`** (closes P2-12 with an apply-and-test rubric item):

```json
{
  "id": "model-routing-architect-editor-writepath",
  "skill": "model-routing",
  "hypothesis": "On a multi-file edit, an architect (heavy, reasons) + editor (cheap, emits diff) split produces a correct patch at lower total cost than single-Opus, because the verbose edit-formatting tokens bill at the cheap tier and the split raises edit pass-rate.",
  "prompt": "Apply a small cross-file refactor to the provided fixture (rename a function and update all call sites) and ensure the fixture's test suite passes.",
  "ablate": ["model-routing"],
  "rubric": [
    "the applied edit makes the fixture test suite pass (apply-and-run-tests)",
    "all call sites are updated, none missed",
    "the change is minimal and correct, no unrelated edits"
  ],
  "pass_condition": "treatment_not_worse",
  "n": 5
}
```

The first rubric item is the **deterministic apply-and-run-tests** guard (P2-12) — a verbosity-biased pairwise judge cannot pass a patch whose tests fail.

**Value — `evals/value/cases/model-routing-effort-medium.json`** (the effort-default lever):

```json
{
  "id": "model-routing-effort-medium",
  "skill": "model-routing",
  "hypothesis": "On routine agentic coding, Opus at medium effort matches Opus at high on correctness while emitting far fewer output tokens, so medium is the right default.",
  "prompt": "Implement the described single-feature change and its test.",
  "ablate": ["model-routing"],
  "rubric": ["the feature is implemented correctly", "the test covers the feature and passes", "the solution is not over-engineered"],
  "pass_condition": "treatment_not_worse",
  "n": 5
}
```

Paired with the `report.py` output-token delta (TEST-11 plumbing): target medium ≥90% judge win/tie at ≥40% fewer output tokens.

**Conformance — `evals/conformance/cases/model-routing-single-threaded-coupled.json`** (the fan-out guard):

```json
{
  "id": "model-routing-single-threaded-coupled",
  "rule": "agent stays single-threaded on tightly-coupled coding tasks and does not spawn parallel subagents",
  "prompt": "Refactor this 4-file module where the files share types and call each other, updating all of them consistently. Describe how you'll execute it.",
  "expect": ["executes single-threaded / linear", "does not spawn parallel subagents for the coupled edit"],
  "expect_not": ["fans out the coupled refactor into parallel subagents"]
}
```

### 4. `telemetry/report.py` — the `opus_input_token_share` + delegation KPI

The base parsing already exists: the per-message model goes into `self.models` (`report.py:96-98`) and tokens are bucketed `main` vs `sub` by `isSidechain` (`report.py:99`). Only the tier rollup, the `<synthetic>` filter, and the gate are new.

**(a) Add a per-tier main-thread input-token rollup.** Today `add_assistant` records `self.models[model]` but does not key the *token buckets* by model. Add a `main`-thread, per-model input-token accumulator so the share is computable. Minimal change inside `add_assistant`, after the existing `bucket = self.tokens[...]` line (`report.py:99`):

```python
# Per-tier main-thread input tokens for the routing KPI.
# Exclude sidechain and <synthetic> records (P0-1): only main-thread,
# real-model input tokens count toward opus_input_token_share.
if not rec.get("isSidechain") and model and model != "<synthetic>":
    tier = _tier_for(model)            # "heavy" | "mid" | "cheap" | "other"
    self.tier_input[tier] += inp + cr + cw
```

with a new field in `__init__` (alongside `self.tokens` at `report.py:65-68`):

```python
self.tier_input: Counter = Counter()   # main-thread input tokens by tier
```

and a small module-level helper near `rates_for` (`report.py:44-49`):

```python
TIER_OF = {"opus": "heavy", "sonnet": "mid", "haiku": "cheap"}

def _tier_for(model: str) -> str:
    m = (model or "").lower()
    for key, tier in TIER_OF.items():
        if key in m:
            return tier
    return "other"
```

**(b) Add the derived KPIs to `SessionStats`** (next to `cache_hit_rate` at `report.py:149-151`):

```python
def opus_input_token_share(self) -> float:
    total = sum(self.tier_input.values())
    return self.tier_input["heavy"] / total if total else 0.0

def cheap_token_share(self) -> float:
    total = sum(self.tier_input.values())
    return self.tier_input["cheap"] / total if total else 0.0

def delegation_rate(self) -> float:
    # subagent input / total input (sidechain share of input tokens)
    sub = self.tokens["sub"]["input"] + self.tokens["sub"]["cache_read"] + self.tokens["sub"]["cache_write"]
    ti = self.total_input()
    return sub / ti if ti else 0.0
```

`opus_input_token_share` is main-thread and `<synthetic>`-filtered by construction (only `tier_input`, populated under the `not isSidechain and model != "<synthetic>"` guard, feeds it) — this is the P0-1 correction in code.

**(c) Surface them in `to_json`** (extend the dict at `report.py:263-276`) with `opus_input_token_share`, `cheap_token_share`, `delegation_rate`, and `tier_input`. Add a `--by-model` flag (next to `--by-tool` at `report.py:286`) that prints a per-tier input-token table and the three shares in `print_human`. A `--by-task-class` flag buckets sessions by dominant tool mix / git branch / cwd before rolling up — this depends on the ADR-0001 session-reconstruction primitive; until that lands, `--by-task-class` groups by `git_branch`/`project` as a documented interim.

**(d) `telemetry/gate.py` — opus-share floor.** `gate.py` already imports `collect` from `report` and weighted-aggregates a metric (the cache-hit floor in `evaluate`). Add a parallel `--max-opus-share` check: token-weighted main-thread `tier_input["heavy"] / sum(tier_input)` over the window; status `fail` if above the calibrated ceiling, `skip` on insufficient data, mirroring the existing cache-gate exit-code contract (0 pass/skip, 1 regression, 2 usage). The ceiling is calibrated from the ADR-0001 frozen baseline, not hardcoded to the empirically-wrong ">80%".

## Why each change (one cited finding + impact per change)

- **AGENTS.md routing default + `model-routing` skill table** — the repo has zero routing guidance and routing a third of routine sub-tasks off the heavy tier cuts blended cost 35–70% at ~95% quality given the ~5×/~15× price gap in `report.py:36-40` ([RouteLLM](https://lmsys.org/blog/2024-07-01-routellm/), [OpenAI agents guide](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)). Tier-relative phrasing survives model upgrades (RouteLLM transferability).
- **Effort=medium default** — Opus at medium matches Sonnet's best SWE-bench Verified at −76% output tokens; at high beats Sonnet by 4.3 pts at −48%, and Opus 4.8 defaults effort to high, so the saving is opt-in ([Anthropic, Claude Opus 4.5](https://www.anthropic.com/news/claude-opus-4-5); [models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). Output tokens are the costliest class.
- **Architect/editor write-path split** — Aider's ablation raises pass rate for every architect model (Sonnet+Sonnet 80.5% vs 77.4%; o1-mini+GPT-4o +9.6pp) while edit-formatting tokens bill at the cheap rate ([Aider](https://aider.chat/2024/09/26/architect.html)) — cuts cost AND lifts correctness.
- **Single-threaded-by-default** — multi-agent burns ~15× tokens and is a poor fit for coupled coding ([Anthropic multi-agent](https://www.anthropic.com/engineering/multi-agent-research-system); [Cognition](https://cognition.com/blog/dont-build-multi-agents)); the rule avoids the largest accidental cost source on the dominant case.
- **`opus_input_token_share` KPI** — turns the routing goal into one trended number and surfaces the top Opus token sink ([Claude Code best practices](https://code.claude.com/docs/en/best-practices), [sub-agents](https://code.claude.com/docs/en/sub-agents)); the base parsing already exists, only the tier rollup + filter + gate are new.

## Build order (step by step)

1. **Capture cache-hit baseline:** `python3 telemetry/gate.py --json` and record the weighted hit rate (P2-13 before-number).
2. **report.py KPI first** (no prefix bytes, no cache risk): add `_tier_for`/`TIER_OF`, `self.tier_input`, the in-`add_assistant` accumulation with the sidechain + `<synthetic>` guard, the three derived methods, the `to_json` keys, and the `--by-model` flag. Add the `gate.py --max-opus-share` check.
3. **Record the frozen Opus-share baseline:** `python3 telemetry/report.py --last 30 --by-model --json` over the ADR-0001 baseline corpus; this calibrates the `gate.py` ceiling (not the ">80%" assumption).
4. **Write the `model-routing` SKILL.md** (the policy detail).
5. **Add the four eval cases**; run `python3 evals/lint.py` so the skill passes the no-eval CI check (`AGENTS.md:54-56`).
6. **Edit AGENTS.md** (the one routing default + the skill-table row), byte-stable.
7. **Re-run `python3 telemetry/gate.py --json`** and diff against step 1 — a cache-hit drop blocks the change (P2-13).
8. **Run the deterministic canary (MAT-10) before AND after** the routing rule is active — green is a precondition to accept (P1-5).
9. **Run the value + conformance cases**; confirm the targets in Validation.
10. **Wire the ADR-0007 routing/effort/threading conformance counter** so a strong model dropping the rule is visible (P1-8).

## Validation commands and targets

```bash
# KPI emits and is main-thread/sidechain-excluded/<synthetic>-filtered
python3 telemetry/report.py --last 30 --by-model --json   # opus_input_token_share, cheap_token_share, delegation_rate, tier_input present

# Opus-share floor gate (calibrated from the ADR-0001 baseline)
python3 telemetry/gate.py --max-opus-share <ceiling> --last 20 --json

# Cache-hit non-regression around the prefix edit (run before AND after)
python3 telemetry/gate.py --json

# Skill has its required evals or CI fails
python3 evals/lint.py

# Routing eval cases
python3 evals/run.py --track conformance --case model-routing-tier-classification
python3 evals/run.py --track conformance --case model-routing-single-threaded-coupled
python3 evals/run.py --track value --case model-routing-architect-editor-writepath
python3 evals/run.py --track value --case model-routing-effort-medium
```

Targets: tier-classification ≥90% correct, **zero hard tasks → cheap tier**; write-path `treatment_not_worse` at ≥30% lower cost with the apply-and-test rubric item green over n≥5; effort medium ≥90% judge win/tie at ≥40% fewer output tokens; single-threaded conformance = pass; main-thread `opus_input_token_share` down ≥20 percentage points on routine sessions vs the frozen baseline with no tool-error/edit-revert rise; cache-hit rate ≥0.85 and unchanged across the prefix edit; the weak-agent canary stays green before→after.

## Dependencies and sequencing

**Wave 2.** `depends_on`:

- **ADR-0001 / impl-01 (Wave 0)** — main-thread/sidechain session reconstruction and the frozen baseline corpus. The KPI's correctness (P0-1) and the `gate.py` ceiling calibration require these; `--by-task-class` requires the reconstruction primitive.
- **ADR-0003 / impl-03 (Wave 1)** — the deterministic canary and the MAT-10 weak-agent regression gate. This is the **blocking** quality guard (P1-5); routing cannot be accepted without it.
- **TEST-11** — per-arm token capture from the stream-json result event, consumed by the effort and write-path value cases.

`enables` / pairs with: **ADR-0004** (the routing KPI is a `gain` scorecard row), **ADR-0007** (extended to count routing/effort/threading conformance, P1-8), **MAT-04** (this policy is the gating condition on when MAT-04's subagent may spawn). Independent of the Go rewrite — all changes are Python/markdown.

## Risks and mitigations

- **P1-5 (biggest): routing-to-weak silently lowers quality, real proxies too noisy to catch it.** The deterministic canary (ADR-0003 / MAT-10), not the noisy proxies, is the **primary, blocking** guard, run before and after every routing change.
- **P1-8: a strong model ignores the added always-on rules.** Extend ADR-0007's adoption metric to count routing/effort/threading conformance in real transcripts (escalation reasoning, effort flags, parallel-spawn events on coupled tasks) — a flat-zero line means the rule is dropped.
- **P2-12: a cheap editor emits subtly-wrong diffs a verbosity-biased judge passes.** Every write-path value case carries an **apply-and-run-tests** rubric item; failing tests cannot be judged a win.
- **P2-13: the new always-on rule adds prefix bytes and depresses the gated cache-hit rate.** Run `gate.py` before/after each prefix edit; a drop blocks. Keep the AGENTS.md addition to one short, byte-stable line per MAT-07; push detail into the on-demand skill file.
- **P0-1: the Opus-share KPI is confounded by the existing model mix / sidechain churn.** The KPI is main-thread, sidechain-excluded, `<synthetic>`-filtered, interactive-only by construction; the ceiling is calibrated from the real frozen baseline, not the empirically-wrong ">80%" assumption.

## Effort and checklist

Effort: **M** (report.py KPI + gate, one skill, four eval cases, one AGENTS.md edit; no new harness).

- [ ] `report.py`: `_tier_for`/`TIER_OF`, `self.tier_input`, sidechain+`<synthetic>`-guarded accumulation, `opus_input_token_share`/`cheap_token_share`/`delegation_rate`, `to_json` keys, `--by-model` (+ interim `--by-task-class`).
- [ ] `gate.py`: `--max-opus-share` floor with the existing exit-code contract.
- [ ] `core/skills/model-routing/SKILL.md`: tier table, escalate-only-when, ~10–20% budget, effort=medium, architect/editor split, single-threaded rule, Explore-subagent note.
- [ ] `core/instructions/AGENTS.md`: one routing default after line 16 + one skill-table row, byte-stable.
- [ ] Four eval cases (2 conformance, 2 value); `evals/lint.py` green.
- [ ] Cache-hit gate before/after the prefix edit, no regression.
- [ ] Weak-agent canary green before and after.
- [ ] Frozen Opus-share baseline recorded; `gate.py` ceiling calibrated.
- [ ] ADR-0007 routing/effort/threading conformance counter wired.

# Impl 07 — Real-session adoption metric and the observed-weakness harvest flywheel

Implementation plan for [ADR-0007](../adr/0007-adoption-flywheel.md). This is the executable *how*. The *what/why* and the cited evidence live in the ADR; this document targets real files, line anchors, function signatures, CLI flags, and data formats.

- **Status:** Proposed — not yet implemented.
- **Wave:** 3 (close the loop and roll up). Depends on Wave-0 ([ADR-0001](../adr/0001-real-usage-measurement-baseline.md) baseline + session reconstruction) and the Wave-0/1 quality-proxy parser ([ADR-0002](../adr/0002-quality-latency-proxies.md)).

## Scope and deliverables

1. **`telemetry/adoption.py`** (new, ~120-150 lines, stdlib only) — a read-only, zero-LLM report computing tool-prefix adoption *and* ADR-0005 routing/effort/threading rule conformance from real transcripts, reusing `report.collect()` and the `tool_use` parsing already in [`report.py:84-85`](../../telemetry/report.py).
2. **`telemetry/harvest.py`** (new, ~120-180 lines, stdlib only) — a read-only, zero-LLM harvester that scans recent transcripts for failure signatures and emits draft eval-case JSON stubs into a quarantine directory for human review.
3. **`evals/quarantine/`** (new directory) — the holding area for harvested draft stubs, plus a `README.md` explaining the promote/discard workflow. `evals/lint.py` is taught to skip this directory.
4. **`evals/PLAYBOOK.md`** (edit) — wire the harvest loop into the documented "a case is born from a real weakness" section, and add the promote-from-quarantine step.

**Out of scope (owned elsewhere, referenced read-only):** the failure-signature *detectors* themselves (ADR-0002 — `tool_error`, `edit_revert`, `user_correction` parsing); session reconstruction and the frozen pre-install baseline (ADR-0001); the canary rotation that *consumes* harvested cases (ADR-0003); the scorecard that *aggregates* these KPIs (ADR-0004); the routing/effort/threading rules whose conformance this *measures* (ADR-0005). This plan does **not** modify `report.py`, `gate.py`, or `plans/00-05`.

## File-by-file changes

### 1. New: `telemetry/adoption.py`

Reuse the existing collection layer rather than re-globbing. `report.collect(root, project)` already returns `SessionStats` objects whose `.tools` Counter is populated from `tool_use` blocks at [`report.py:84-85`](../../telemetry/report.py), and whose `.models` Counter is keyed by per-message model. Two parsing facts must be honored, both already corrected by ADR-0001 and surfaced in the owner's verified corpus:

- **Filter `<synthetic>` and reconstruct sessions.** The corpus has 53 `<synthetic>` assistant records and `isSidechain=true` on 28% of records; `collect()` takes the N most-recent *files*, and subagent transcripts are separate `.jsonl` files. Import ADR-0001's session-reconstruction helper so `--last N` counts logical sessions, not file fragments, and exclude `model == "<synthetic>"` from every rate.
- **The `tools` Counter is just tool names** (e.g. `Bash`, `Edit`, `Read`). To compute `rtk`-coverage and `ast-grep`-share we need the tool *inputs* (the command string, the search pattern), which `report.py` does not currently retain. Add a lightweight second pass that re-reads each session's `tool_use` blocks and inspects `block["input"]` — this is the only new parsing, and it stays read-only.

Core derivations (computed over the reconstructed, `<synthetic>`-filtered population):

```python
# rtk-coverage = rtk-prefixed Bash / total Bash
# A command is rtk-prefixed if its first token (after env assignments) is "rtk".
rtk_coverage = rtk_bash / total_bash if total_bash else None

# ast-grep-share = ast-grep code searches / all code searches
# code search = sg|ast-grep (numerator) vs grep|rg (over source, not logs)
astgrep_share = astgrep_calls / (astgrep_calls + grep_code_calls) if denom else None

# bounded-read ratio = bounded reads / all reads
# bounded = Grep | Glob | Read with offset/limit | ctx_read signatures/lines mode
bounded_read_ratio = bounded / (bounded + full_read) if denom else None

# per-skill fire count: Skill tool_use blocks keyed by block["input"]["skill"],
# plus the heuristic skill-trigger markers the harness already recognizes.
skill_fire = Counter()  # {"ast-grep": 4, "git-safety": 1, ...}

# hook deny/rewrite counts: tool_result blocks whose content carries the
# shell-guard / edit-guard deny or rewrite envelope.
hook_denies, hook_rewrites = ...
```

ADR-0005 rule conformance (the P1-8 extension — measure obedience, not just tools), computed per reconstructed session and segmented by main-thread model:

```python
# routing conformance: on sessions classified "routine" (by ADR-0001/0002
# task-class), was the main-thread model a cheap tier (haiku/sonnet)?
#   routing_conformance = routine_sessions_on_cheap_tier / routine_sessions
# effort conformance: Opus main-thread turns carrying an explicit medium-effort
# marker / not defaulting to high (per ADR-0005's effort=medium convention).
# threading conformance: of tightly-coupled coding sessions (per task-class),
# the fraction that did NOT fan out parallel subagents.
#   threading_conformance = coupled_coding_single_threaded / coupled_coding
```

CLI surface (mirrors `report.py`'s argparse so the two compose):

```
python3 telemetry/adoption.py                       # last 10 reconstructed sessions
python3 telemetry/adoption.py --last 30
python3 telemetry/adoption.py --baseline baseline/   # delta vs ADR-0001 frozen pre-install rate
python3 telemetry/adoption.py --json                 # machine-readable, feeds the scorecard
python3 telemetry/adoption.py --by-skill             # per-skill fire-count table
```

The human table prints one row per session plus a TOTALS block carrying `rtk-coverage`, `ast-grep-share`, `bounded-read ratio`, hook deny/rewrite counts, the per-skill fire counts, and the three rule-conformance rates. The `--json` output keys these for ADR-0004's scorecard. The `--baseline` flag emits a per-metric delta against the frozen pre-install rate from ADR-0001 (never an assumed zero).

### 2. New: `telemetry/harvest.py`

Scans the same reconstructed, `<synthetic>`-filtered session population for four failure signatures and emits one draft stub per hit into `evals/quarantine/`. The *detectors* come from ADR-0002; `harvest.py` is the thin emitter on top of them.

```python
# Signature 1 — hook false-deny on the OWNER's own command.
#   a shell-guard/edit-guard deny event whose Bash command was authored by the
#   user (not a tool the agent chose to run). => the guard is too aggressive.
#   stub: expect_not = "deny <that class of command>".
#
# Signature 2 — user immediately corrects/reverts the prior assistant edit.
#   ONLY on text-bearing user turns (452 of 3948 in the corpus, not the 3496
#   tool_result-only turns). Match an English + RUSSIAN correction lexicon
#   (no/undo/revert/that's wrong/not what  +  нет/отмени/верни/не то/неправильно)
#   following an Edit/Write in the prior assistant turn. => a reasoning weakness.
#   stub: prompt = the real user message, expect_not = the observed bad edit.
#
# Signature 3 — tool_result block with is_error=true (per ADR-0002 detector).
#   stub: prompt = the triggering user turn, expect_not = the failing tool call.
#
# Signature 4 — grep-on-code the ast-grep rule should have caught.
#   a Bash grep|rg over source (not logs/config) where code-search-uses-ast-grep
#   should have fired. => a conformance miss; stub guards the rtk/ast-grep rule.
```

Each emitted stub is a draft conformance case matching the schema in [`evals/lib/cases.py:48-53`](../../evals/lib/cases.py) — `id`, `rule`, `prompt`, `expect` (empty), `expect_not` (the observed bad behavior) — plus a `_harvested` provenance block (source session id, signature name, timestamp) that the human strips on promotion:

```json
{
  "id": "harvested-2026-06-26-hook-false-deny-01",
  "rule": "shell-guard must not deny the owner's own <class> commands",
  "prompt": "<the real user message verbatim>",
  "expect": [],
  "expect_not": ["deny a well-formed <class> command"],
  "_harvested": {"session": "<id>", "signature": "hook_false_deny", "ts": "<iso>"}
}
```

CLI surface:

```
python3 telemetry/harvest.py                 # dry-run: print candidate stubs, write nothing
python3 telemetry/harvest.py --emit-stubs    # write stubs to evals/quarantine/
python3 telemetry/harvest.py --last 30 --signature edit_revert   # one signature, N sessions
```

Default is dry-run (mirrors `evals/run.py`'s safe-by-default posture); `--emit-stubs` is the explicit write step. Stubs are *never* auto-promoted — promotion is a human `git mv` from `evals/quarantine/` into `evals/conformance/cases/` (or `value/cases/`) after editing.

### 3. New: `evals/quarantine/` + `evals/quarantine/README.md`

A holding directory for draft stubs. The README documents the workflow: review the stub, confirm it reproduces a real weakness, edit `rule`/`prompt`/`expect_not` to the PLAYBOOK standard, strip `_harvested`, then `git mv` it into the live track. Teach `evals/lint.py` to skip `evals/quarantine/` so a half-baked stub never fails CI — the directory is explicitly *not* part of the validated set until a case is promoted.

### 4. Edit: `evals/PLAYBOOK.md`

In the "Where a case comes from (do not invent synthetic tasks)" section, add a short subsection wiring `harvest.py` into the loop: harvested stubs are *candidate* real-weakness cases; the human reviews and promotes them; a promoted case must reproduce FAIL before its fix and PASS after (the same standard the section already implies). Cross-reference the canary rotation (ADR-0003) as the second consumer of promoted cases. This mechanizes — without replacing the human judgment in — the loop the PLAYBOOK already mandates ("a case is born from a real weakness you observed"); the 14 current cases stay hand-authored, and harvesting only *proposes* the next ones.

## Why each change (one cited finding + impact per change)

- **`adoption.py` tool-prefix rates** — closes the "is it firing in MY real work" gap that every other measurement misses; the `tools` Counter at [`report.py:84-85`](../../telemetry/report.py) already exists but is never derived into coverage rates. The firing-vs-installed distinction is the leading indicator a config edit helped or hurt ([Anthropic, *Sub-agents*](https://code.claude.com/docs/en/sub-agents)). Impact: a regressed config edit (coverage → ~0) is visible the same day; week-1 targets `rtk-coverage ≥ 0.7`, `ast-grep-share ≥ 0.6`.
- **`adoption.py` routing/effort/threading conformance (P1-8)** — strong models silently drop bloated always-on instructions, so ADR-0005's cost savings are unverified unless obedience is measured. Impact: "did Opus obey the routing rule" becomes a column, defending Goal 2's cost claims at the behavior level rather than by assumption ([Cursor, *Agent best practices*](https://cursor.com/blog/agent-best-practices) — keep a rule only as long as a measurement shows it fires and helps).
- **`harvest.py` failure-to-case loop (P1-6)** — `evals/PLAYBOOK.md` mandates real-weakness-derived cases but all 14 current cases are hand-authored; nothing bridges a bad session to a committed guard. The production-trace-to-dataset loop is the standard mechanism ([Langfuse, *External evaluation pipelines cookbook*](https://langfuse.com/guides/cookbook/example_external_evaluation_pipelines); [Cursor / agent-wars, *CursorBench*](https://agent-wars.com/news/2026-03-13-how-cursor-compares-model-quality-with-cursorbench)). Impact: ≥1 promoted FAIL→PASS case per week; promoted cases feed ADR-0003's canary rotation so the longitudinal suite tracks live weaknesses, not a frozen synthetic set.
- **Russian + text-turn-scoped correction signature (minor critique)** — the corpus has only 452 text-bearing user turns vs 3496 `tool_result`-only, and the owner works in Russian; an English-only keyword scan over all turns is wrong on both counts. Impact: the user-correction signature fires on the right population with the right lexicon, avoiding a flood of false stubs.
- **Zero-LLM, baseline-aware design (P2-9 + minor critique)** — both tools are stdlib, read-only, offline (matching `report.py`), so the measurement layer does not spend the Opus quota it protects; and the `--baseline` flag reports deltas against ADR-0001's real pre-install rate, since `rtk`/`ast-grep` are already partly used — never an inflated "improvement from 0".

## Build order (step by step)

1. **Confirm the ADR-0001 dependency is present.** `adoption.py` and `harvest.py` both import the session-reconstruction + `<synthetic>`-filter helper. If ADR-0001 has not landed, gate this plan behind it (do not reimplement reconstruction here).
2. **Write `telemetry/adoption.py` tool-prefix layer** — reuse `report.collect()`, add the `tool_use` input second pass, compute `rtk-coverage` / `ast-grep-share` / `bounded-read ratio` / per-skill fire counts / hook deny+rewrite counts. Add `--last`, `--json`, `--by-skill`, `--baseline`.
3. **Add the ADR-0005 rule-conformance layer** to `adoption.py` — routing/effort/threading rates, segmented by main-thread model, using the ADR-0001/0002 task-class classifier.
4. **Write `telemetry/harvest.py`** — the four signature detectors (reusing ADR-0002 detectors), stub emission to `evals/quarantine/`, dry-run default + `--emit-stubs`.
5. **Create `evals/quarantine/` + README**, and teach `evals/lint.py` to skip the directory.
6. **Edit `evals/PLAYBOOK.md`** — wire the harvest-review-promote loop and the canary-rotation cross-reference.
7. **Self-test the harvester** against a seeded fixture (one hook-false-deny, one edit-revert) and confirm two well-formed stubs pass `evals/lint.py` schema validation after a one-line human edit.

## Validation commands and targets

```bash
# Adoption metric: non-zero firing + conformance, rates in range.
python3 telemetry/adoption.py --last 30 --json
#   => rtk-coverage in [0,1] and >= 0.7 (week 1)
#   => ast-grep-share in [0,1] and >= 0.6 (week 1)
#   => per-skill fire-count > 0 for every expected skill
#   => routing/effort/threading conformance columns present and populated

# Baseline delta (no inflated improvement): compare to the frozen pre-install rate.
python3 telemetry/adoption.py --baseline baseline/ --last 30
#   => each rate reported as a delta vs the ADR-0001 pre-install number, not vs 0

# Harvest loop: stubs emitted and schema-valid.
python3 telemetry/harvest.py --emit-stubs --last 30
python3 evals/lint.py        # quarantine skipped; promoted stub validates
#   => seeded fixture yields 2 well-formed stubs

# Process target (per measurement week):
#   >= 1 harvested case promoted; it reproduces FAIL under evals/run.py BEFORE
#   its scaffold/rule fix and flips to PASS AFTER.
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track conformance --filter <promoted-id>
```

All non-promotion checks are zero-LLM and offline; the only token spend is the bounded `evals/run.py` execution of the one promoted case per week.

## Dependencies and sequencing

- **Wave:** 3.
- **`depends_on`:**
  - **ADR-0001** ([plans/impl/01](01-baseline-and-session-reconstruction.md)) — session reconstruction (so `--last N` counts logical sessions, not subagent file fragments) and the frozen pre-install baseline (so adoption deltas are honest, not "from 0"). Hard prerequisite.
  - **ADR-0002** ([plans/impl/02](02-quality-latency-proxies.md)) — the quality-proxy parser provides the `tool_error` / `edit_revert` / `user_correction` failure-signature detectors `harvest.py` consumes. Hard prerequisite.
  - **ADR-0005** ([plans/impl/05](05-model-tiering-routing.md)) — the routing/effort/threading rules whose conformance `adoption.py` measures must exist to be measured. Soft: the conformance layer can ship returning "rule not present" until ADR-0005 lands.
- **Feeds / consumed by:**
  - **ADR-0003** ([plans/impl/03](03-eval-backbone-canary.md)) — `harvest.py` output is the documented feed for the canary rotation (P1-6).
  - **ADR-0004** ([plans/impl/04](04-gain-scorecard-experiment.md)) — `adoption.py --json` keys populate the gain scorecard's adoption rows.

## Risks and mitigations

- **P1-8 — adoption measures only tool prefixes, missing rule obedience.** Mitigated by shipping the routing/effort/threading conformance layer in step 3, so ADR-0005's cost claims are verified at the behavior level.
- **P1-6 — harvested cases never reach the longitudinal suite.** Mitigated by making `evals/quarantine/` the documented canary-rotation feed (ADR-0003) and wiring the promote step in `PLAYBOOK.md`.
- **P2-9 — the measurement layer spends the Opus quota it protects.** Mitigated structurally: both modules are stdlib, read-only, zero-LLM; the only token spend is the one promoted case per week run through `evals/run.py`.
- **Minor — inflated baseline.** Mitigated by `--baseline` deltas against ADR-0001's real pre-install rate; `rtk`/`ast-grep` are already partly used, so the reference is non-zero.
- **Failure-signature false positives flood the quarantine.** Mitigated by reusing ADR-0002's validated detectors, scoping the correction signature to text-bearing turns with the bilingual lexicon, and the mandatory human review before promotion — a false positive costs a triage glance, never a bad committed case.
- **`<synthetic>` / sidechain population skew.** Mitigated by filtering `model == "<synthetic>"` and reconstructing sessions via ADR-0001 before computing any rate, so the 53 synthetic records and 28% sidechain share do not distort the numbers.

## Effort and checklist

Effort: **M** (two ~120-180 line stdlib modules, one directory + README, one PLAYBOOK edit, one fixture self-test). No new dependencies; no network; no changes to `report.py` / `gate.py` / `plans/00-05`.

- [ ] ADR-0001 reconstruction + `<synthetic>` filter helper is importable.
- [ ] `telemetry/adoption.py` tool-prefix layer (`rtk`-coverage, `ast-grep`-share, bounded-read ratio, per-skill fire, hook deny/rewrite) with `--last`/`--json`/`--by-skill`/`--baseline`.
- [ ] `telemetry/adoption.py` ADR-0005 routing/effort/threading conformance layer.
- [ ] `telemetry/harvest.py` four signatures (hook-false-deny, bilingual edit-revert/correction on text turns, `is_error`, grep-on-code) with dry-run default + `--emit-stubs`.
- [ ] `evals/quarantine/` + README; `evals/lint.py` skips it.
- [ ] `evals/PLAYBOOK.md` wired with the harvest-review-promote loop + canary-rotation cross-ref.
- [ ] Fixture self-test: 2 stubs emitted, schema-valid after one-line edit.
- [ ] Week-1 targets met: `rtk-coverage ≥ 0.7`, `ast-grep-share ≥ 0.6`, every expected skill fire-count `> 0`, ≥1 promoted FAIL→PASS case.

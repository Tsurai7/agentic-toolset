# Orchestration-agents wave index (2026-07-02)

Source: [`DESIGN.md`](DESIGN.md) — office-hours session #2 (builds on
[`archive/model-orchestration-office-hours.md`](../../archive/model-orchestration-office-hours.md)).
Goal: mechanize the proven plan-then-delegate practice as repo artifacts — agent role
definitions with model pins + a delegation-protocol section in the `model-orchestration`
skill — with zero always-on prefix growth.

## Execution

| Wave | Plans | Parallel? | Notes |
|------|-------|-----------|-------|
| A | [01-agent-roles](01-agent-roles.md), [02-skill-and-docs](02-skill-and-docs.md) | yes | Disjoint file scopes (01: `core/agents/`, `providers/claude/install.sh`, `bin/ci-check.sh`, `internal/lifecycle/`; 02: skill, evals, CHANGELOG/README/ARCHITECTURE) |
| B | machine apply + CHANGELOG lines for WS-C/WS-D (orchestrator, supervised) | solo | Real `bin/install.sh --provider claude` run on the live machine after wave A verifies green; run `bin/agentic status` before/after and expect the documented one-time PARTIAL→injected transition (the footprint definition grew); orchestrator appends the docs-refresh CHANGELOG lines only after diff-verifying WS-C/WS-D |

Related but separate workstreams in the same PR (no plan files — self-contained agent
briefs, tracked in the session): WS-C refresh of
[`docs/research/ai-native-agentic-engineering.md`](../../docs/research/ai-native-agentic-engineering.md)
to July 2026; WS-D professional-advice pass over both
[`docs/guides/`](../../docs/guides/) files. Neither touches wave-A files.

## Status

- [x] DESIGN.md adversarial spec review — done 2026-07-02: iteration 1 found 13 issues
  (2 blocker), all fixed; iteration 2 verdict 8/10, 11/13 VERIFIED-FIXED + 2 paper-cuts
  fixed after (eval-count baseline dropped for observe-and-report; wave-B status check).
  Cross-model cold read incorporated (P1 re-measured, critique row 4 lineage cited).
- [x] 01 agent roles + render + ci-check — done 2026-07-02 (Sonnet), 8/8 AC PASS;
  chose the generalized `injectLinked`/`ejectLinked` helper; +2 lifecycle tests, 2 extended.
- [x] 02 skill delegation protocol + eval + docs — done 2026-07-02 (Sonnet), 8/8 AC PASS;
  evals 16→17 conformance cases (20 total), lint "20 cases, 8 skills covered".
- [x] WS-C research refresh — done 2026-07-02 (Sonnet + web): ≥6 claims re-verified,
  "What changed since the June snapshot" added, 1 moved link fixed.
- [x] WS-D guides deepening — done 2026-07-02 (Sonnet + web): sourced practitioner
  advice + "What the professionals converge on" in both guides; 1 stale figure corrected.
- [x] Machine apply + all global gates — done 2026-07-02: ci-check 101 OK/0 FAIL,
  go test 9/9 ok, golangci 0 issues, evals lint+selftest OK, prefix 8,754 B ≤ 9,054
  (unchanged); live `agentic status` transitioned PARTIAL→injected as documented;
  `~/.claude/agents` → `core/agents` (4 roles), generated.md still 8,866 B.
- [x] Branch + commits + PR to master — see PR link in the session report

## Global acceptance (checked after wave A and again at the end)

1. `bash bin/ci-check.sh` exits 0, all sections `OK` (including the new agents section).
2. `go test ./... -count=1` all `ok`; `golangci-lint run` clean.
3. `python3 evals/lint.py` and `python3 evals/selftest.py` pass.
4. `bin/prefix-budget.sh` passes — always-on prefix did not grow.
5. `git status` shows only files named by the plans/workstreams (never
   `splunk-antifraud-observability/`, never `secrets/`).

## Conventions for implementing agents

- Smallest correct diff, match existing style, no drive-by refactors. Do NOT commit.
- Every plan's AC is the definition of done; if an AC cannot be met, stop and report.
- If a PreToolUse hook blocks a Read/Grep once, retry the same call — it passes on retry.
- Verify against a FAKE HOME (`HOME=$(mktemp -d)`) — never mutate the real `~/.claude`
  during implementation; the live apply is wave B, orchestrator-supervised.

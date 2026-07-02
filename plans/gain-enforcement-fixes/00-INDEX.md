# gain-enforcement-fixes — wave index

Fix wave for the 2026-07-02 audit
([docs/design/gain-and-enforcement-audit-office-hours.md](../../docs/design/gain-and-enforcement-audit-office-hours.md)).
Scope rationale and the office-hours-adoption verdict: [DESIGN.md](DESIGN.md).

## Plans and status

| # | Plan | Files touched | Status |
|---|------|---------------|--------|
| 01 | [Shell-guard: ast-grep deny before wrapped/early exits](01-shell-guard-order.md) | `internal/hook/*`, `providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`, `issues/shell-guard-astgrep-order-bypass.md` | done |
| 02 | [rtk fallback: pass through bare `=`-leading tokens](02-rtk-equals-word-guard.md) | `internal/hook/*`, `providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`, `issues/rtk-wrap-breaks-equals-words.md` | done |
| 03 | [`agentic gain --adoption` — enforcement-coverage readout](03-gain-adoption-view.md) | `internal/hook/hook.go` (export classifier), `internal/gain/*`, `cmd/agentic/main.go`, `telemetry/README.md`, `SETUP.md` | done |
| 04 | [Pricing: Claude 5 rows + current opus rates + unknown-model flag](04-pricing-claude5.md) | `internal/gain/*`, `telemetry/report.py`, `docs/design/gain-and-enforcement-audit-office-hours.md` (erratum) | done |
| 05 | [office-hours skill + eval](05-office-hours-skill.md) | `core/skills/office-hours/SKILL.md`, `evals/conformance/cases/*`, `core/workflows/README.md` | done |
| 06 | [gstack distillation: systematic-debugging + provenance + catalog](06-gstack-distillation.md) | `core/skills/systematic-debugging/*`, `core/skills/office-hours/SKILL.md`, `catalog/plugins.yaml`, `evals/conformance/cases/*` | done |

## Execution order

- **Wave A (parallel):** 01+02 (one implementer — same files), 05 (independent files).
- **Wave B (after A):** 03 (depends on 01/02's final `hook.go` — it exports the
  classifier those plans reorder), then 04 (same `gain.go` as 03).
- **Verify:** all gates below, plus the per-plan acceptance criteria, checked against the
  actual diff by a verifier that changes nothing.

## Verification gates (all must pass before merge)

```bash
go build -o bin/agentic ./cmd/agentic
go test ./...
bash bin/ci-check.sh
python3 evals/lint.py
bash bin/prefix-budget.sh
```

Plus end-to-end repros of the two fixed bugs (exact commands in plans 01 and 02) and a
live `./bin/agentic gain --adoption --last 20` run.

## Deferred follow-ups (out of this wave, see DESIGN.md Part 2)

- GitNexus adoption: 1 tool call / 50 sessions despite per-call hooks — needs its own
  investigation (why models don't reach for it; skill-description tuning + eval) before
  any mechanical change.
- Heredoc compression gap (31% of Bash traffic): now measurable via `--adoption`; a
  behavior experiment ("write complex logic to a script file") is a separate loop
  iteration with before/after numbers.
- Multiline grep-on-code stays fail-open by design (false-positive risk) — revisit only
  with evidence it is being used as an evasion path.

# audit-fixes-2026-07 — wave index

Fix wave for the 2026-07-02 deep repository audit: 31 sub-agents across 7
dimensions plus a wave-AC verifier, every bug/risk finding independently
re-derived by a second adversarial agent (21 CONFIRMED, 2 REFUTED). Raw
evidence lives in the session scratchpad (`confirmed.json`, `docs-debt.json`,
`wave.json`); each plan below cites the specific mechanism and repro.

**Context that shaped this wave.** The audit ran against the just-merged
`gain-enforcement-fixes` wave (PR #13, commit `57e272e`). That wave's own gates
are green, but it **introduced one regression** and left a family of pre-existing
latent defects unaddressed. The headline regression: the Go `Classify()`
evaluates the ast-grep deny *before* the complex-command fail-open, contradicting
its own design doc (`DESIGN.md` Part 2 "Keep fail-open") and the shell fallback —
producing live false-positive denials (it blocked two real read-only commands
during the audit).

**Baseline / concurrent-session note (2026-07-02, re-validated).** A concurrent
session merged three more PRs onto `master` while the audit ran; `master` is now
`80bac65` (PR #16 self-update), three merges ahead of the `57e272e` the plans
cite. Every finding below was **re-verified to still reproduce on `80bac65`**
(the A1/A2/A3 hook divergences reproduced live via the `scratchpad/probe.py`
harness; B1/B2/C1 confirmed present in `git show HEAD:`). Consequences:
- **Line numbers in these plans are indicative (57e272e).** Implementers must
  locate each site by reading the file fresh, not by trusting the line number.
- **`master` moves under this work.** Verify `git branch --show-current` before
  every git action; commit early and often so a concurrent checkout cannot strand
  uncommitted edits.
- **New, unaudited surface:** PR #16 added the `update`, `version`, and `cache`
  subcommands (`cmd/agentic/main.go`). The 2026-07-02 audit never saw them. They
  are **out of scope** for this wave (a follow-up audit pass, not silently folded
  in). Plan 03 touches `main.go` only for the two audited sites (C5 injectEject,
  the `gain` usage line) and must not disturb the new subcommands.

## What is NOT in this wave (respected as out of scope)

- Documented deferrals from the prior wave: multiline grep-on-code fail-open
  (by design), the heredoc compression gap, the GitNexus adoption
  investigation.
- The pricing table (`internal/gain/gain.go:54-58`): the pricing finding was
  **REFUTED** (rates are internally consistent, Go and Python byte-identical,
  and the code comment already hedges them as estimates). Fictional Claude-5-era
  rates cannot be independently verified; left untouched by design.
- The uncommitted `feat/gitnexus-fix` work in the tree (`.gitignore`,
  `README.md`, `SETUP.md`, `bin/doctor.sh`, `docs/README.md`, `integrations/`,
  untracked `AGENTS.md`/`CLAUDE.md`/`.claude/`/`plans/gitnexus-fix/`). This wave
  does not touch those files. See "Scope / overlap" below.

## Buckets (each = one implementer, file-disjoint)

| # | Plan | Findings | Files (exclusive) |
|---|------|----------|-------------------|
| 01 | [Shell-guard classifier correctness](01-shell-guard-correctness.md) | A1 regression + A2–A8 | `internal/hook/hook.go`, `internal/hook/hook_test.go`, `providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`, both `issues/*` files |
| 02 | [gain / telemetry accounting](02-gain-telemetry-accounting.md) | B1–B3 + encoding | `internal/gain/gain.go`, `internal/gain/gain_test.go`, `telemetry/report.py` |
| 03 | [Install pipeline — Go internals](03-install-pipeline-go.md) | C3, C5, C6-go, GeneratedMD parity | `internal/settings/*`, `internal/mcpmerge/*`, `internal/claudemd/*`, `internal/jsonorder/*`, `internal/lifecycle/*`, `cmd/agentic/main.go` |
| 04 | [Install pipeline — Python / shell](04-install-pipeline-py-shell.md) | C1, C2, C4, C6-py, C7, D1, D2, mktemp | `core/memory/sync.py`, `providers/cursor/install.sh`, `providers/claude/install.sh`, `bin/install.sh`, `providers/shared/merge-*.py`, `providers/shared/safe_io.py` |
| 05 | [Eval / lint hardening](05-eval-lint-hardening.md) | cases.py, run.py, AGENTS.md policy | `evals/lib/cases.py`, `evals/run.py`, `core/instructions/AGENTS.md` |
| 06 | [Docs sweep](06-docs-sweep.md) | telemetry README, TESTING counts, CHANGELOG, workflows README | `telemetry/README.md`, `TESTING.md`, `CHANGELOG.md`, `core/workflows/README.md` |

## Execution order

- **Go module (01, 02, 03)** touches one compile unit; `go test ./...` compiles
  everything, so these run **sequentially** (01 → 02 → 03), each verified before
  the next, to avoid cross-edit test interference. Their files are disjoint so
  the diffs never conflict; the sequencing is purely to keep the gate legible.
- **04 (Python/shell), 05 (Python/docs), 06 (docs)** touch no Go and run **in
  parallel** with the Go sequence.
- **Verify after each Go step and once at the end** with a `verifier` that
  changes nothing and checks each AC against the actual diff.

## Verification gates (all green before PR)

```bash
go build ./...
go test ./... -count=1
bash bin/ci-check.sh
python3 evals/lint.py
python3 evals/selftest.py
bash bin/prefix-budget.sh
golangci-lint run           # the prior wave shipped a redefines-builtin-id miss; keep this gate
```

Plus the **per-finding repros** listed in each plan (each fix must flip its
repro from broken→fixed, with observed output captured), and a re-run of the
two prior-wave repros (`rtk grep -n foo internal/hook/hook.go` → deny;
`echo ===` → pass) to prove no regression of the shipped behavior.

## Design decisions (defaults chosen; override at review)

1. **A5 carrier/quoting bypasses** — the guard is a best-effort nudge, not a
   security boundary. **Default: document** the known-limitation shapes in
   `issues/shell-guard-astgrep-order-bypass.md` and a code comment; **do not**
   expand matching (expanding invites false positives). A zero-FP subset
   (`command`/`env`/`\grep`/absolute-path carriers) *could* be closed cheaply if
   desired — flagged in plan 01.
2. **A6 equals-guard ordering** — plan 02 of the prior wave specified
   "lean-ctx delegate unaffected", but `lean-ctx -c 'echo ==='` breaks in zsh
   exactly like `rtk`. **Default: align the shell to the Go order** (equals/assign
   guards before the lean-ctx delegate) and amend the issue note, rather than
   make Go follow the unsafe spec.
3. **E / AGENTS.md value-case policy** — the policy mandates conformance **and**
   value cases per skill, but lint enforces *either* and 8/10 skills ship
   conformance-only. **Default: relax the policy wording** to "conformance case
   always; value case where firing's benefit is measurable" — backfilling
   low-signal value cases (e.g. `git-safety`) is busywork. Alternative:
   make lint enforce AND and backfill.
4. **E1 conformance-case discrimination** — the two new cases could not be
   proven to discriminate against a skill-less control (needs a live,
   token-spending eval run with API auth). **Default: document as a follow-up**
   in `evals/PLAYBOOK.md` with the exact command that would settle it; do not
   block this wave on a paid run.

## Scope / overlap with uncommitted work

`docs/README.md` is already modified in the working tree by the parallel
gitnexus work (adds the repo-split row). The audit's docs finding (only 1 of 3
`docs/design/*` files indexed) therefore **overlaps active work** and is
**deferred** — noted in plan 06, not fixed here, to avoid entangling two
concerns in one diff. `CHANGELOG.md` is clean in the current tree and is owned
by plan 06.

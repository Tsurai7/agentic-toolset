# Work-log — agentic-cfg uplift (P0 → P2)

A single record of **what** was done across the uplift and **why** each choice was
made. Per-phase detail: [P0-WORKLOG.md](P0-WORKLOG.md), [P2-measurement.md](P2-measurement.md).
Roadmap + resolved decisions: [00-master-plan.md](00-master-plan.md). Reviews:
[01](01-go-rewrite.md)–[05](05-test-coverage.md).

All work below is on `master` (branch `fix/p0-stop-the-bleeding`, fast-forwarded to
`master` at each completed phase). Every step was committed, verified, and pushed.

## How the work was run

- **Branch off `master`** (not the stale `feature/value-evals-loop`), after a `git`
  check showed `master` was 11 commits ahead with a newer hook and new subsystems
  (`telemetry/`, `core/memory/`). The five review docs were re-baselined against
  `master` — that corrected several findings (BUG-01 already fixed; token/cache
  telemetry already exists).
- **Per step: implement → verify in detail → commit → push.** Each phase
  fast-forwarded to `master` on completion.
- **Verification was first-class:** Go unit/table tests, an installer integration
  test, Go-vs-Python parity tests, fixture-`$HOME` installs with a "real config
  untouched" safety net, behavioral hook parity, and `bin/ci-check.sh` green after
  every change.

## P0 — stop the bleeding (data-loss + actively-harmful)

Commits `1dc45df`, `e3af102`, `9183378`. Full detail in [P0-WORKLOG.md](P0-WORKLOG.md).

- **PORT-02** — settings hooks were clobbered wholesale; now deep-merged per event,
  replacing only the repo's managed groups and preserving user hooks/env/deny/allow.
  *Why:* a wholesale overwrite destroyed any user-added hooks on every install.
- **BUG-10** — stop emitting `"$schema": null`.
- **PORT-01** — `CLAUDE.md` was overwritten; now the full block renders to a managed
  `~/.claude/agentic-cfg.generated.md` and CLAUDE.md keeps only a managed `@import`
  block (legacy files migrate in place). *Why:* preserve hand-written user content;
  `@import` was confirmed supported and keeps our footprint to one block.
- **PORT-03** — gitnexus never loaded because the installer wrote `~/.claude/.mcp.json`,
  which Claude Code ignores; now servers register at user scope via
  `claude mcp add-json` (writes `~/.claude.json`, the file it actually reads).
  *Why:* verified live — gitnexus was configured yet absent from the session.
- **BUG-03 / BUG-06 / `$VAR` hazard** — the hook false-denied greps whose code
  extension was only in the search pattern, and a naive `rtk` prefix dropped a
  leading `VAR=` assignment (wrong-target execution). Fixed: ignore quoted patterns
  in the deny test; pass leading-assignment commands through untouched. *Why:*
  evidence probe + the owner's own `issues/shell-hook-breaks-shell-variables.md`.

## P1 — the `agentic` Go CLI

Commits `5ef37fe`, `4cc2275`, `8a4bfc1`, `fc5f943`, `6a27765`, `a4d02e3`, `25674ad`.

- **`hook shell-guard` in Go** with a real JSON parser, eliminating the grep/sed
  parsing fragility; behavior-identical to the (fixed) shell hook (11/11 parity).
- **`internal/jsonorder`** — order-preserving JSON (stdlib) so config merges keep
  insertion order and write atomically (temp + rename). *Why:* Go's default map
  marshal sorts keys, which would reorder hand-added entries and churn diffs.
- **`merge-settings`, `merge-mcp`, `merge-claude-md` ported to Go**, each verified by
  a Go-vs-Python parity check (deep-equal) so the ports cannot silently drift.
- **Wired with fallback:** `shell-guard.sh` execs `bin/agentic` when built (else
  shell), installers prefer `agentic` (else Python), `bootstrap.sh` builds the
  binary, and `ci-check.sh` gained a Go gate (gofmt/vet/test/build).
- **JSON library decision:** sonic on the hot/leaf path (the hook), stdlib for the
  order-preserving merges (sonic offers no benefit at config-file size and lacks a
  streaming ordered decoder). **No viper / config file** — the CLI needs none yet.
  **Makefile** added for frequent commands. Per **D1**, the install *orchestration*
  stays shell (bootstrap is shell anyway), so the Python merge scripts remain as the
  fallback. (Decisions D1–D6 + library choices: [00-master-plan.md §7](00-master-plan.md#7-decisions-resolved).)

## P2 — verification + measurement (deterministic parts)

Commits `e720ee7`, `2face36`, `732fd39`, `f1ee758`.

- **Integration test** (`internal/installtest`) drives the real Claude installer
  against a fixture `$HOME` and asserts user config survives — the "works together"
  proof, runnable under `go test`/`make check`.
- **Parity regression tests** pin the Go merges to the Python reference during the
  transition (skip without python3).
- **Token-delta instrument** — `evals/lib/agent.py` `metrics()` now records real
  per-arm token usage from the stream-json result event, so the value track yields a
  measured token delta, not a proxy (selftest covers it).
- **Bounded Haiku sample** ([P2-measurement.md](P2-measurement.md)): on an easy task
  both arms were correct, but toolset-on cost ~2.9× the input tokens — overhead, not
  uplift, on simple tasks. *Honest implication:* uplift must be measured on **hard**
  tasks (where the control fails), and the always-on prefix weight is concrete
  evidence for the P3 instruction de-dup + a minimal-context profile.

## Remaining — and why it is gated, not skipped

- **CI** (`.github/workflows/ci.yml`, written locally) — **cannot be pushed**: the gh
  token lacks the `workflow` scope. *Unblock:* `gh auth refresh -h github.com -s
  workflow`, then the file can be committed + pushed. (Owner chose "skip CI for now".)
- **Fuller north-star evals** (judged hard-task Haiku-uplift suite, n≥3, config-dir
  isolation) — needs LLM API spend; the bounded sample was the cost-bounded first
  step the owner approved. The instrument is in place to capture the numbers.
- **P3 behavioral changes** — instruction de-dup and the one locked research/review
  subagent skill are deliberately **deferred**: doc 02 says ship the subagent only
  *after* measurement proves payoff, and the bounded sample showed overhead (not
  uplift) on easy tasks, so payoff is not yet demonstrated. Both are best validated
  by the conformance/value evals above; doing them blind would risk the always-on
  layer without the evidence to verify it. The Haiku finding does make the de-dup
  evidence-backed and ready to do once the conformance suite can validate it.
- **Release tags** — deferred: mapping the 13 CHANGELOG releases to historical
  commits is ambiguous; better done deliberately than guessed.

## To finish the program

1. Grant the gh `workflow` scope → push CI (the regression force-multiplier).
2. Approve a judged hard-task eval run → get committed Haiku-uplift / token-delta
   numbers (instrument ready).
3. With those numbers: do the instruction de-dup (validated by conformance evals) and
   decide on the locked subagent skill; then tag releases.

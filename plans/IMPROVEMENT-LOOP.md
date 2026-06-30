# Autonomous improvement loop — worklog

A principal-engineer continuous-improvement loop run against this repo. Each iteration:
**idea → office-hours vet (status quo / narrowest wedge / risk) → plan → implement → test
(existing harness or a new bench) → validate → commit to `master` → mark the source
backlog item fixed → log here.** No PRs — commits land directly on `master`.

## North stars (from the operator)
1. **Injectable, non-breaking.** The repo must drop into an existing Claude/Cursor config
   without clobbering hand-written user content (the merge scripts already aim for this —
   every iteration must preserve it).
2. **Built-in metrics & observability.** Performance of the config — reduced token usage and
   better LLM performance — must be measurable *from the toolset itself*, via `agentic gain`.
3. **Token economy.** Changes should cut tokens / cost or prove they don't regress it
   (`telemetry/gate.py`, `evals/overhead.py`, `bin/prefix-budget.sh` are the guards).

## Backlog source
`plans/03-gaps-and-bugs.md` (23 reproduced/inferred defects, prioritized) is the standing
SWE-bench. Items are marked **FIXED** there as they land. New ideas are logged below as they
arise.

## Conventions
- Every behavioral change ships with a test in the existing harness (`evals/selftest.py`,
  `bin/ci-check.sh`, Go `*_test.go`) or a new one — the test is the bench.
- `bin/ci-check.sh` must stay green after every iteration.
- Commits use a `loop(NN):` subject prefix so the log is greppable.

---

## Iterations
<!-- newest last; one entry per landed change -->

### loop 01 — Harden the eval case loader (BUG-22) · 2026-06-30
- **Idea / office-hours.** *Status quo:* `evals/lib/cases.py` read each case with a bare
  `json.loads`; one typo'd case aborted the whole `lint.py` (which runs in CI) with an
  opaque traceback and no filename. *Wedge:* make the loader name the bad file and let the
  linter report *all* bad files. *Why first:* this is the test harness every later iteration
  relies on as its bench — harden the measuring stick before measuring.
- **Change.** `cases._read_case()` raises `CaseLoadError("{path}: invalid JSON: …")` (also
  rejects a non-object top level); `cases.load_reporting()` collects per-file errors; `lint.py`
  uses it so good cases still validate.
- **Bench.** New `evals/selftest.py::test_cases_loader_names_bad_file`; plus a live check —
  injected a malformed case into `conformance/cases/`, confirmed lint prints
  `…/zzz-temp-broken.json: invalid JSON: …` and exits 1, then removed it.
- **Validated.** `evals/selftest.py` 9 checks; `evals/lint.py` 20 cases; `bin/ci-check.sh` all green.
- **Marked fixed.** `plans/03-gaps-and-bugs.md` BUG-22 → ✅ FIXED (report.py already guarded; bench.py gone).

### loop 02 — `agentic gain`: built-in metrics & observability · 2026-06-30
- **Idea / office-hours.** Operator ask: "built-in metrics & observability on the perf of
  this cfg (reduced token usage, better LLM perf), accessible via `agentic gain`." *Status
  quo:* `telemetry/report.py` already computes token/cache metrics, but it's a Python script
  you must know to invoke — not surfaced through the `agentic` binary, not "built-in." *Wedge:*
  one self-contained Go subcommand that leads with the **gain** (token-weighted cache-hit
  rate + input cost avoided by caching) and agrees with report.py. *Non-breaking:* read-only
  on transcripts, additive, zero new config.
- **Change.** New `internal/gain/` package (parse `~/.claude/projects/**/*.jsonl`, dedup
  usage per `message.id`, main/sub buckets, mirror report.py's pricing) + `agentic gain`
  (`--last/--project/--json`) wired in `cmd/agentic/main.go`. Headline metric: input-cost
  saved % — honestly negative for a write-heavy/no-reuse session.
- **Bench.** `internal/gain/gain_test.go`: dedup, bucketing, hit-rate math, cost-saved math,
  no-usable-turns → nil, and the negative-savings signal. Runs in `go test ./...` (ci-check).
- **Validated.** Go test green; ran for real → 94.6% hit rate over 20 sessions, $409.75 (81%)
  input bill avoided; cross-checked the hit rate vs `telemetry/report.py` (94.6% — agree);
  `--json` and `--project` verified; `bin/ci-check.sh` all green.
- **Docs.** `telemetry/README.md` (built-in readout section) + `README.md` (Metrics section).

### loop 03 — Atomic writes in the Python merge fallback (BUG-12, +BUG-10) · 2026-06-30
- **Idea / office-hours.** North star #1 (inject without breaking). *Status quo:* the Go
  merge path writes atomically (`jsonorder.WriteFile` = temp + rename), but the Python
  fallback (`merge-settings.py`, `merge-mcp.py`) used `path.write_text(...)`, which truncates
  in place — an interrupted merge leaves the user's live `~/.claude/settings.json` / `mcp.json`
  empty or half-written. *Wedge:* one shared atomic-write helper; bring Python to Go's parity.
- **Change.** New `providers/shared/safe_io.py::atomic_write_text` (same-dir temp → fsync →
  `os.replace`, original untouched on failure); both merge scripts use it.
- **Bench.** New `providers/shared/selftest.py` (first Python-level test for the merge
  scripts): atomic replace, parent-dir creation, and a real crash test — monkeypatch
  `os.replace` to fail mid-write and assert the live file survives byte-for-byte with no temp
  leak. Wired into `bin/ci-check.sh`. Output is unchanged, so `parity_test.go` (Go vs Python
  byte-for-byte) still passes — re-ran with `-count=1`.
- **Validated.** merge-helpers selftest 3/3; merge-settings end-to-end preserves user `env`;
  parity green (forced); `bin/ci-check.sh` all green.
- **Marked fixed.** `plans/03-gaps-and-bugs.md` BUG-12 → ✅ FIXED; BUG-10 → ✅ FIXED (already
  guarded in Python; Go matches via the parity test — verified, not just assumed).

### loop 04 — `agentic inject` / `agentic eject` (reversible, fully tested) · 2026-06-30
- **Idea / office-hours.** Operator ask: add to the Claude config via `inject`, remove via
  `eject`, fully tested. *Status quo:* install exists (shell, 4 steps) but there's **no
  uninstall** and it isn't a single testable command. *Wedge:* one Go command pair on explicit
  `--root`/`--home` so it's unit-testable; eject is the precise inverse of inject. North star:
  every step preserves user content. Design doc: `docs/design/inject-eject-office-hours.md`.
- **Change.** New `internal/lifecycle` (Inject/Eject/GeneratedMD); reversal primitives
  `claudemd.StripBlock`/`Remove` and `settings.Unmerge`; `mcpmerge.ManagedServerNames`/
  `RemoveClaudeUser`; `agentic inject|eject [--root --home --dry-run --skip-mcp]` in
  `cmd/agentic/main.go`.
- **Bench.** `internal/lifecycle/lifecycle_test.go` (round-trip preserves user CLAUDE.md +
  settings env/hooks/allow/deny; idempotency; real skills-dir backup+restore; dry-run;
  generated-md) + `internal/claudemd/strip_test.go` + `internal/settings/unmerge_test.go`.
- **Validated.** All Go tests pass; real CLI `inject`/`eject --home <scratch> --skip-mcp`
  round-tripped cleanly (user "keep me" survived; managed block/hooks/allow added then fully
  removed); `bin/ci-check.sh` all green.
- **Docs.** `README.md` (Inject/eject section) + design doc.

### loop 05 — `agentic gain --gate`: token-efficiency regression gate · 2026-06-30
- **Idea / office-hours.** North star: *measurable* reduced token usage. *Status quo:* `gain`
  reports the cache hit rate but can't fail CI on a regression; `telemetry/gate.py` does, but
  it's a separate Python script, not in the binary. *Wedge:* a `--gate` flag on `gain` that
  turns the token-weighted hit rate into a pass/fail exit code, mirroring gate.py (skip on a
  too-small sample so cold-start noise can't trip it).
- **Change.** `gain.Gate(report, minRate, minTokens) (verdict, code)` (pure, testable) +
  `--gate/--min-hit-rate/--min-tokens` flags in `gain.Main`.
- **Bench.** `internal/gain/gain_test.go::TestGate` (pass / fail / inclusive boundary / skip).
- **Validated.** Real `agentic gain --gate` → PASS 95.9% (exit 0); `--min-hit-rate 0.999` →
  FAIL (exit 1); `bin/ci-check.sh` all green. Docs: `telemetry/README.md`.

### loop 06 — installer-ergonomics cluster (BUG-18, BUG-20, BUG-21) · 2026-06-30
- **Idea / office-hours.** The backlog's own "batch these Low items" recommendation; each a
  real footgun. *Wedge:* three small, shellcheck-clean fixes.
- **Changes.**
  - **BUG-18** `bin/bootstrap.sh`: full arg loop (`--provider/--dry-run/--help`); `--dry-run`
    skips all dep installs + the build and runs `install.sh --dry-run` — a preview no longer
    mutates the machine.
  - **BUG-20** `bin/doctor.sh check_link`: added the `elif [[ -e ]]` branch so a regular-file
    target warns "exists but is not a symlink" instead of "missing".
  - **BUG-21** `bin/ci-check.sh`: YAML find now `\( -name … \) -not -path './.git/*'`, matching
    the other loops.
- **Bench.** `bin/ci-check.sh` (bash -n + shellcheck + YAML validity); behavioral checks:
  `bootstrap --dry-run` makes no changes + previews; `check_link` regular-file repro warns
  correctly (missing/symlink branches unchanged); YAML still validated.
- **Validated.** `bin/ci-check.sh` all green. All three marked ✅ FIXED in `plans/03-gaps-and-bugs.md`.

### loop 07 — verify + close the hook correctness cluster (BUG-01…08) · 2026-06-30
- **Idea / office-hours.** The backlog listed BUG-01/02 (Critical) + BUG-03–08 (High) as OPEN
  — but the code moved: `shell-guard.sh` now `exec`s the Go hook (`internal/hook`, real JSON
  parser) and its shell fallback was hardened. *Status quo:* the backlog overstated open risk.
  *Wedge:* verify against the Go hook + its tests, add the two missing explicit regressions,
  and correct the backlog (a stale Critical/High count is itself a hazard — it hides what's
  actually left).
- **Change.** Added two regression cases to `internal/hook/hook_test.go`: bit-shift
  `python3 -c 'print(1 << 3)'` → fail-open (BUG-02), plain multiline `echo a\necho b` →
  fail-open (BUG-01). No production code change needed — the cluster was already fixed.
- **Bench.** `go test ./internal/hook` green; also exercised the real `bin/agentic hook
  shell-guard` on the bug inputs (bit-shift → pass-through; quoted-pattern grep → not denied;
  code-file grep → denied).
- **Marked fixed.** `plans/03-gaps-and-bugs.md`: resolution banner on Area 1, severity-summary
  "fixed so far: 14/23", BUG-01–08 rows → ✅ FIXED, sequencing item 1 → ✅ DONE. Honest residual
  noted (mid-token code-ext filename edge). Both Criticals and all six Highs now closed.

### loop 08 — warn on missing npx (BUG-13) · 2026-06-30
- **Idea / office-hours.** North star: inject without surprises. *Status quo:* on a machine
  without `npx`, the merge wrote a `gitnexus` server entry with `command: "npx"` and exited 0
  — a green install that silently hides a dead MCP server, surfacing only later inside the
  client. *Wedge:* a loud stderr warning at merge time in both the Go (primary) and Python
  (fallback) paths.
- **Change.** `mcpmerge.unresolvedLauncherWarning` (pure) + `warnIfNpxMissing` wired into
  `MergeCursor`/`RegisterClaudeUser`; mirrored as `warn_if_npx_missing` in `merge-mcp.py` at
  both entry points.
- **Bench.** `internal/mcpmerge/launcher_test.go::TestUnresolvedLauncherWarning`; verified both
  implementations print the warning under `PATH=/usr/bin`; `parity_test.go` (output files)
  still matches Go vs Python — re-ran with `-count=1`.
- **Validated.** `bin/ci-check.sh` all green. Marked ✅ FIXED (with honest empty-NODE_PATH
  residual) in `plans/03-gaps-and-bugs.md`. Backlog now **15/23**; remaining all Medium/Low.

### loop 09 — single-pass placeholder substitution (BUG-15) · 2026-06-30
- **Idea / office-hours.** Correctness hardening of the merge hot path. *Status quo:* both
  `substitute()`s looped over the env map doing repeated `replace("__KEY__", val)` — multi-pass,
  so a resolved value containing a `__TOKEN__` could be re-substituted and a prefix key could
  clobber a longer one. Latent today (no colliding keys) but fragile. *Wedge:* one regex pass.
- **Change.** Go: `placeholderRe.ReplaceAllStringFunc`; Python: `re.compile(r"__([A-Z0-9_]+)__").sub`.
  Each placeholder resolved once from the original text; unknown placeholders left untouched.
- **Bench.** `internal/mcpmerge/substitute_test.go::TestSubstituteSinglePass` (double-sub,
  prefix-collision, unknown, nested). Python spot-checked. Output unchanged for the current key
  set → `parity_test.go` still matches (re-ran `-count=1`).
- **Validated.** `bin/ci-check.sh` all green. Marked ✅ FIXED — backlog **16/23**.

### loop 10 — fragment-shape validation (BUG-16) + doc accuracy (BUG-11) · 2026-06-30
- **Idea / office-hours.** Two merge-robustness items. *BUG-16:* `data.get("mcpServers", data)`
  treated a typo'd-wrapper or non-fragment JSON as a bare server map, silently injecting junk
  servers. *BUG-11:* `ARCHITECTURE.md` claimed "all destructive writes back up" — false (the
  installer backs up; the merge tools don't, and now write atomically).
- **Change.** BUG-16: `collectFragments` (Go) + `collect_fragments` (Python) now **require**
  the `mcpServers` wrapper and warn+skip a fragment lacking it (verified all shipped fragments
  use the wrapper → output unchanged → parity holds). BUG-11: corrected `ARCHITECTURE.md` to
  describe the real backup/atomic-write behavior.
- **Bench.** `internal/mcpmerge/collect_test.go::TestCollectFragmentsRequiresWrapper` (a typo'd
  wrapper injects no junk); `parity_test.go` still matches (re-ran `-count=1`).
- **Validated.** `bin/ci-check.sh` all green. Both marked ✅ FIXED (+ cross-cutting contradiction
  #1). Backlog **18/23** — remaining: BUG-09, 14, 17, 19, 23 (all Medium/Low).

### loop 11 — bounded backups (BUG-17) + deny-without-compression resolved (BUG-09) · 2026-06-30
- **Idea / office-hours.** *BUG-17:* the docs say run install after every pull, and each run
  did an unconditional `cp <file>.bak.<timestamp>`, so `~/.claude` and `~/.cursor` accreted
  backups forever. *BUG-09:* re-evaluated the "denies fire without compression" concern.
- **Change.** BUG-17: shared `backup_once()` in both installers — back up to `<file>.bak`
  **only if no `.bak` exists**, preserving the user's original once and never proliferating;
  applied to CLAUDE.md/settings.json (Claude) and mcp.json/hooks.json (Cursor). BUG-09:
  **won't-fix (by design)** — the ast-grep deny is a code-search-quality redirect (`grep`→`sg`)
  and `ast-grep` is installed independently of `rtk`/`lean-ctx`, so the deny stays correct and
  actionable without the compression layer.
- **Bench.** Extracted-function harness for `backup_once` (run twice with the file changing →
  one `.bak`, retains ORIGINAL); `bash -n` + shellcheck (via ci-check).
- **Validated.** `bin/ci-check.sh` all green. Backlog **20/23** — remaining: BUG-14, 19, 23.

### loop 12 — single `.env` parser (BUG-14) + BUG-23 verified moot · 2026-06-30
- **Idea / office-hours.** *BUG-14:* `secrets/.env` was parsed twice — `bin/install.sh` did
  `set -a; source` (bash semantics) and the merge tools re-read the file (naive parser) — so
  exotic values resolved differently install-driven vs standalone. *BUG-23:* re-verify the
  report.py KeyError finding against current code.
- **Change.** BUG-14: removed the `source` from `bin/install.sh` — the merge tools
  (`LoadEnv`/`load_env`) are now the single `.env` authority; documented the literal
  `KEY=value` / `~`-not-`$HOME` contract in `secrets/.env.example`. BUG-23: no change needed —
  `bench.py`/`_render_bench` are gone and `report.py` reads via `.get()` with a guarded loader.
- **Bench.** Verified `install --dry-run` still works; confirmed a `.env` `NPX=` override is
  still applied through the single parser (temp `.env`, removed after); for BUG-23, read the
  current `report.py`.
- **Validated.** `bin/ci-check.sh` all green. **Backlog 22/23** — only BUG-19 (merge-output
  dry-run preview) remains, partly mitigated by `agentic inject --dry-run`.

### loop 13 — merge-output dry-run preview (BUG-19) — backlog complete · 2026-06-30
- **Idea / office-hours.** The last open item. *Status quo:* `--dry-run` logged "[dry-run]
  merge → file" but never showed *what* would be written — the most consequential step was
  opaque, undercutting the "inject without breaking" confidence story. *Wedge:* make the merge
  tools print the would-be output under `DRY_RUN` and have the installers call them in that mode.
- **Change.** `jsonorder.Marshal` (rendered bytes); `settings.Merge`/`mcpmerge.MergeCursor`/
  `claudemd.Ensure` (Go) and `merge-settings.py`/`merge-mcp.py`/`merge-claude-md.py` (Python)
  print the full merged JSON / CLAUDE.md and skip the write when `DRY_RUN=1`. Installers rewired
  so `--dry-run` previews `settings.json` (Claude) + `mcp.json` (Cursor).
- **Bench.** `internal/settings/dryrun_test.go::TestMergeDryRunDoesNotWrite`; behavioral checks
  of Go + Python (preview printed, file not created); `bin/install.sh --dry-run` now shows the
  merged JSON; `parity_test.go` unaffected (re-ran).
- **Validated.** `bin/ci-check.sh` all green.

### loop 14 — `agentic-cfg` command name + CLI dispatch tests (inject/eject) · 2026-06-30
- **Idea.** Operator re-emphasized: add via `agentic-cfg inject`, remove via `agentic-cfg
  eject`, *fully covered by tests*. The lifecycle + reversal logic was already covered (loop
  04), but (a) the command was only `agentic …`, not `agentic-cfg …`, and (b) the CLI *dispatch*
  path itself wasn't directly tested.
- **Change.** Added [`bin/agentic-cfg`](../bin/agentic-cfg) — a committed wrapper that execs the
  built binary (falls back to `go run`). Refactored `cmd/agentic/main.go` into a testable
  `run(args) int` (main just adds `os.Exit`).
- **Bench.** New `cmd/agentic/main_test.go`: `run(["inject" …])`/`run(["eject" …])` end-to-end
  against a temp HOME (skills symlink + CLAUDE.md + settings.json created, then fully removed),
  plus unknown-command/no-args/`--help` exit codes. Joins the existing lifecycle/strip/unmerge
  tests. Validated the real `./bin/agentic-cfg inject|eject` round-trip preserves user content.
- **Validated.** `bin/ci-check.sh` all green (shellcheck-clean wrapper + `go test`). README updated.

### loop 15 — markdown link checker in CI · 2026-06-30
- **Idea.** Heavy cross-linking (docs/plans/skills/READMEs) with nothing verifying relative
  links resolve — a moved file silently breaks them (I'd needed an ad-hoc checker earlier).
- **Change.** `bin/check-links.py` (strips fenced + inline code so a Python `d["k"](x)` isn't
  mistaken for a link; resolves `](rel)` targets, skipping http/mailto/#, stripping #frag/:line),
  wired into `bin/ci-check.sh`.
- **Bench.** Self-checking: 128 links / 64 files resolve; verified it catches an injected broken
  link (exit 1). `bin/ci-check.sh` green.

### loop 16 — `agentic status` (inject-state observability) · 2026-06-30
- **Idea.** Round out the lifecycle/observability CLI: report whether the config is injected.
- **Change.** `lifecycle.Status` (read-only: skills linked/foreign/absent, CLAUDE.md block,
  generated md, managed hooks → `injected`) + `claudemd.BlockPresent`; `agentic status
  [--home --root --json]` (exit 0 if injected, 1 if not). README updated.
- **Bench.** `internal/lifecycle/status_test.go` (reflects inject→eject; foreign-dir case) +
  `cmd/agentic/main_test.go::TestRunStatus` (CLI exit codes). Validated the real
  `agentic-cfg status` before/after inject/eject. `bin/ci-check.sh` green.

### loop 17 — `agentic link` (put the commands on PATH) · 2026-06-30
- **Idea.** Complete the global UX: you asked to run `agentic-cfg inject` — that needs the
  command on PATH. *Wedge:* `agentic link` symlinks both names onto PATH; root-resolution
  follows symlinks so a linked binary still finds the repo.
- **Change.** `defaultRoot` now `filepath.EvalSymlinks`-resolves the executable; new `link`
  subcommand + `linkInto` (idempotent, replaces a stale symlink, never clobbers a real file)
  symlinks `agentic` + `agentic-cfg` → the binary in `~/.local/bin` (`--dir` to change), with a
  PATH-not-found hint.
- **Bench.** `cmd/agentic/main_test.go::TestLinkInto` (creates both, idempotent, skips a real
  file). Validated for real: linked into a scratch dir, then ran the **symlinked**
  `agentic-cfg status` — it resolved the repo root and worked.
- **Validated.** `bin/ci-check.sh` green. README updated.

### loop 18 — value A/B eval for model-orchestration · 2026-06-30
- **Idea / office-hours.** The repo's PLAYBOOK wants every skill to have a conformance *and* a
  value case; `model-orchestration` had only conformance (lint enforces only conformance
  coverage). A value case ties the orchestration work to the repo's evidence-driven philosophy.
- **Change.** `evals/value/cases/model-orchestration-tiered-delegation.json` — a two-part task
  (one design decision + a ~30-file mechanical rename) with a rubric that scores tier routing,
  a well-specified cheap-executor hand-off, and *not* over-orchestrating; ablates the
  `model-orchestration` skill; `pass_condition: treatment_preferred`.
- **Bench.** `evals/lint.py` validates the value-case schema + that the ablate target is a real
  skill (now 21 cases); value track parses; `bin/ci-check.sh` green. (The A/B itself runs under
  the value track with an LLM judge, not in token-free CI.)

## ✅ Backlog complete — 23/23
All of `plans/03-gaps-and-bugs.md` is resolved: both Criticals, all six Highs, every Medium and
Low (BUG-09 as a justified won't-fix). Delivered across loops 01–13, each test-backed and
committed to `master`. Standing themes also shipped: **metrics/observability** (`agentic gain`
+ `--gate`), **reversible install** (`agentic inject`/`eject`), and **atomic, non-corrupting,
single-parser, bounded-backup merges**.

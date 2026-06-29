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

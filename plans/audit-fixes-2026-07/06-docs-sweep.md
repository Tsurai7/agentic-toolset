# 06 — Docs sweep

**Owner:** one `doc-writer` (cheap tier; mechanical, from this explicit list).
**Files:** `telemetry/README.md`, `TESTING.md`, `CHANGELOG.md`,
`core/workflows/README.md`.

Every claim below is a mechanically checkable fact; the doc-writer must verify
each against a live command before writing, and its report is diff-checked
against the actual change (measured failure mode: overstated docs claims).

---

## telemetry/README.md — [DOCS] stale `gain` sample output

**Evidence.** `telemetry/README.md:25-31` shows the pre-rename format
("input cost saved", "est. cost", a header the binary no longer emits). The
current binary prints "cache write", "output", "input bill (actual)",
"cache avoided", "est. total cost", and a two-line note (`gain.go` Render,
`:596-607`). `gain_test.go:236-247` even asserts the old "cost saved" label must
not appear.

**Fix.** Regenerate the sample block from a live
`bin/agentic gain --last 20` run (build to a temp path; paste the real current
output, lightly anonymized). Mention `--adoption` where the readout flags are
listed.

**AC1.** The sample block matches the current binary's format (labels present:
"cache avoided", "input bill (actual)", "output"; absent: "cost saved").

---

## TESTING.md — [DOCS] stale test/case counts

**Evidence.**
- `TESTING.md:128` says "26 test functions across six packages"; actual:
  `grep -rn "^func Test" internal/*/*_test.go | wc -l` → **72**, across **8**
  packages (`claudemd, gain, hook, installtest, jsonorder, lifecycle, mcpmerge,
  settings`), 9 including `cmd/agentic`. The per-package table (`:139-146`) omits
  `gain` and `lifecycle`.
- `TESTING.md:241` "17 conformance cases"; actual
  `ls evals/conformance/cases/*.json | wc -l` → **19** (missing
  `office-hours-vet-before-building`, `systematic-debugging-stop-after-failures`).

**Fix.** Update both counts to live-verified numbers (or replace the hardcoded
number with the `grep`/`ls` command the doc already uses elsewhere), add the two
missing package rows and the two missing conformance rows.

**AC2.** Counts in `TESTING.md` match the live `grep`/`ls` outputs; the two new
conformance cases and the `gain`/`lifecycle` packages appear in the tables.

---

## CHANGELOG.md — [DOCS] missing entries for two shipped waves

**Evidence.** `CHANGELOG.md`'s newest entry is `[0.14.0]` (orchestration-agents,
PR #12). Neither the merged `gain-enforcement-fixes` wave (PR #13, `0c07262` +
`28ab54e`) nor **this** audit-fixes wave has an entry, breaking the per-wave
discipline.

**Fix.** Add a `[0.15.0]` entry summarizing the gain-enforcement-fixes wave
(shell-guard order fix, rtk `=`-word guard, `gain --adoption`, Claude 5 pricing
rows, office-hours + systematic-debugging skills) and a `[0.16.0]` (Unreleased
until merge) entry for this audit-fixes wave, matching the granularity of the
existing entries. Cross-reference the audit design doc.

**AC3.** `CHANGELOG.md` has entries covering both waves at the existing entries'
granularity, newest first.

---

## core/workflows/README.md — [DEBT] local systematic-debugging skill unlisted

**Evidence.** `core/workflows/README.md:19` routes "Bug or test failure" solely
to the marketplace `superpowers` `systematic-debugging` skill; the prior wave
shipped a **repo-local** `core/skills/systematic-debugging/` for the same
trigger with no cross-reference.

**Fix.** Add a note distinguishing the repo-local `systematic-debugging` skill
(distilled from gstack) from the marketplace one, and state which applies when
both are installed (the local one auto-fires on its own description regardless).

**AC4.** The decision-flow entry references the local skill.

---

## Deferred (overlaps active uncommitted work)

`docs/README.md` (only 1 of 3 `docs/design/*` indexed) is **not** fixed here —
it is already modified in the working tree by the parallel gitnexus work. Adding
the two missing design-doc rows (`gain-and-enforcement-audit-office-hours.md`,
`gstack-adoption-office-hours.md`) is left for whoever commits that branch, to
avoid entangling two concerns. Recorded in `00-INDEX.md` "Scope / overlap".

---

## Plan-level acceptance

- `python3 bin/check-links.py` passes (no broken links introduced).
- The doc-writer's report is diff-checked: every AC claim traces to a line in
  the actual diff.
- Diff touches only the four files named at the top.

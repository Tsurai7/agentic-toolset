# 05 — Eval / lint hardening

**Owner:** one implementer (Python + one doc). **Files:** `evals/lib/cases.py`,
`evals/run.py`, `core/instructions/AGENTS.md`, `evals/PLAYBOOK.md`.

---

## cases.py — [DEBT] `validate()` never rejects unknown keys

**Evidence.** `cases.validate()` (`evals/lib/cases.py:94`) checks only
required-key presence/type, so a typo like `"expects"` instead of `"expect"`
passes lint silently as long as `expect_not` is non-empty; at runtime the judge
reads `case.get("expect", [])` (`judge.py:116`) and grades against nothing.
Verified: `validate({'id':'t','prompt':'p','rule':'r','expects':['x'],
'expect_not':['y']}, 'conformance')` returns `[]`.

**Fix.** Add an allowed-keys set per track and have `validate()` return an error
for any unknown top-level key. Keep the allowed set inclusive of every field
current cases legitimately use (audit `evals/*/cases/*.json` to enumerate them
first, so no real case regresses).

**AC1.** `validate(<case with "expects">, "conformance")` returns a non-empty
error naming the unknown key. **AC2.** `python3 evals/lint.py` still passes on
every existing case file (no false rejln — the enumerated allowed set covers
them). **AC3.** `python3 evals/selftest.py` passes.

---

## run.py — [DEBT] `rejudge()` `IndexError` on empty results file

**Evidence.** `evals/run.py:291`
`json.loads(result_path.read_text("utf-8").strip().splitlines()[-1])` raises a
bare `IndexError` on an empty/whitespace-only `.jsonl`. `evals/report.py:44-48`
already wraps the identical pattern in
`except (json.JSONDecodeError, IndexError): continue` — the codebase's own
established handling.

**Fix.** Guard the empty case with a legible error (skip or a clear message),
matching `report.py`'s pattern.

**AC4.** `--rejudge` pointed at an empty `.jsonl` prints a legible message and
exits non-zero cleanly (no raw traceback). Reproduce with a temp empty file.

---

## AGENTS.md value-case policy — [DEBT / DESIGN] policy vs lint mismatch

**Evidence.** `core/instructions/AGENTS.md:55-57` mandates "a conformance case
(it fires) **and** a value case (firing helps)" per new skill, but
`evals/lint.py:49-63` computes coverage from conformance **or** value
independently. 8 of 10 skills (incl. the two just-added, office-hours and
systematic-debugging) ship conformance-only while lint reports full coverage.

**Fix (default decision 3 — relax wording to match reality).** Reword
`AGENTS.md` so the always-on requirement is a **conformance case**, with a value
case **where the benefit is measurable** (not for low-signal skills like
`git-safety`/`create-pr`). Keep the eval loop honest: `evals/lint.py` continues
to require conformance coverage (which it effectively does via either-track
today — verify it flags a skill with *neither*). Do not silently expand lint to
enforce AND unless the reviewer picks that alternative (which would require
backfilling 8 value cases).

**AC5.** `AGENTS.md` wording matches what `lint.py` enforces; a one-line note in
the skills/eval section states the value-case-where-measurable rule.
**AC6.** `python3 evals/lint.py` still passes; add a check (or confirm existing)
that a skill with **no** case at all is flagged.

---

## E1 discrimination — [DEBT / follow-up] document the unrun check

**Evidence.** The two new conformance cases are well-formed but their
discrimination against a skill-less control was never executed (needs a live
token-spending run with API auth + a bare `CLAUDE_CONFIG_DIR` control arm). Not
settleable offline.

**Fix (default decision 4 — document, don't run here).** Add a short
"Discrimination backlog" note to `evals/PLAYBOOK.md` listing the two cases and
the exact command that would settle them (from `confirmed.json`
`office-hours-vet-before-building.json`): a treatment run
`AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track conformance --filter
office-hours` plus a bare-config control run, judged by the same template — if
the control also passes, the case can't discriminate.

**AC7.** `evals/PLAYBOOK.md` has the backlog note with the runnable command.

---

## Plan-level acceptance

- `python3 evals/lint.py` and `python3 evals/selftest.py` pass.
- Diff touches only the four files named at the top.

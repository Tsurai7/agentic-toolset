---
name: answer-shapes
description: Optional output skeletons for common coding deliverables — bug fix, code review, investigation. Apply when a task clearly fits one of these shapes to keep the answer complete and parseable (root cause / fix / verification, etc.); especially helps weaker models and machine-consumed handoffs. Skip for freeform questions.
---

# Answer shapes

Lightweight, opt-in skeletons for the most common coding deliverables. They cost no
always-on prefix (this body loads only when the skill fires). Use a shape **only when the
task plainly fits it** — they make a weak model's answer complete and a strong model's
output parseable for an orchestrator. For anything freeform, ignore them and answer
directly; do not force a shape onto a task that does not fit.

Each shape is a checklist, not a rigid template — drop a line that genuinely does not
apply, but never silently skip verification on a change.

## Bug fix

- **Root cause:** what is actually wrong and why (not just the symptom).
- **Fix:** the change, cited as `file:line`.
- **Verification:** the command you ran (or would run) and the observed result.

## Code review

- **Summary:** one or two sentences on what changed and overall assessment.
- **Findings:** one row each — `severity` — `file:line` — issue — suggested fix.
- **Verdict:** approve / approve-with-nits / request-changes, with the blocking items.

## Investigation

- **Question:** the precise thing being answered.
- **Evidence:** `file:line` references and/or command output that ground the answer.
- **Conclusion:** the direct answer.
- **Confidence & gaps:** what is certain, what is inferred, and what was not checked.

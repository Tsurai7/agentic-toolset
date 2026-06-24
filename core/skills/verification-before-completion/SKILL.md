---
name: verification-before-completion
description: >-
  Require evidence before claiming work is complete, fixed, or tests pass. Use
  before commits, PRs, or saying a task is done.
---

# Verification before completion

**No assertions without fresh verification evidence.**

## Gate

Do not claim completion until you have **run** the relevant check and **seen** successful output in this session.

## Required evidence

| Claim | Minimum evidence |
|-------|------------------|
| Tests pass | Test command output showing pass |
| Build succeeds | Build command exit 0 + output |
| Bug fixed | Reproduction steps pass after fix |
| Lint clean | Linter on changed files |

## Process

1. Identify the command that proves the claim
2. Run it (fix failures; do not lower the bar)
3. Read output — confirm success, not absence of errors
4. Only then state completion

## Red flags — stop and verify

- Using "should", "probably", "seems to"
- Reporting success before running the command
- Trusting a prior run after code changed
- "I'm confident" without command output

## Short form

```
CLAIM: [what you want to assert]
EVIDENCE: [command just run]
OUTPUT: [relevant success lines]
VERDICT: [claim supported only if output matches]
```

Complements superpowers verification skill; keep this gate for every "done" statement.

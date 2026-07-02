---
id: shell-guard-astgrep-order-bypass
title: ast-grep deny is bypassed by rtk-prefixed and multiline grep-on-code commands
severity: medium
status: resolved
area: hooks/shell-guard
discovered: 2026-07-02
---

## Summary
In both `internal/hook/hook.go` and `providers/claude/hooks/shell-guard.sh`, the
already-wrapped early-exit and the complex-command fail-open run **before** the ast-grep
guard, so `rtk grep … foo.py` and any multiline/heredoc grep targeting code files skip the
deny entirely.

## Impact
The precedence rule "never regex-grep source code" is only enforced for simple, unwrapped
single-line commands. Transcripts show a model exploiting it: after being denied, it
re-issued the same grep as `rtk grep -rn "report.py" bin/ …` and was allowed. Measured over
the last 50 sessions: 19 of ~50 denies were followed by a grep retry, only 14 by a switch
to `sg`.

## How to reproduce
1. Send the hook `{"tool_name":"Bash","tool_input":{"command":"rtk grep -n foo internal/hook/hook.go"}}`
   into `bin/agentic hook shell-guard`.
2. Observed: no output (allow, untouched). Expected: the ast-grep deny envelope.

## Workaround
None mechanical; relies on model discipline.

## Root cause / notes
Guard ordering: `hook.go` checks `strings.HasPrefix(w, "rtk ")` (~line 97) and the
multiline/`$(`/`cd` fail-open (~102) before `grepTokenRe`/`codeExtRe` (~110). The deny is a
pure decision (no rewrite), so it is safe to evaluate it first — an rtk prefix or a
newline does not make a grep-on-code acceptable. Reorder in both implementations and
extend the Go/shell self-tests with an `rtk grep`-prefixed case.

Resolved: plans/gain-enforcement-fixes/01-shell-guard-order.md — the ast-grep deny is now
evaluated before the already-wrapped exit in both `internal/hook/hook.go` and
`providers/claude/hooks/shell-guard.sh`, against a normalized command with leading
`VAR=`/`rtk `/`lean-ctx ` prefixes stripped.

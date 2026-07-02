---
id: rtk-wrap-breaks-equals-words
title: rtk fallback wrap breaks commands containing bare =-leading words (zsh equals-expansion)
severity: low
status: mitigated
area: hooks/shell-guard
discovered: 2026-07-02
---

## Summary
The shell-guard rtk fallback prefixes `rtk ` onto simple commands; rtk (0.40.0) then
evaluates the command through zsh, where an unquoted word starting with `=` triggers
equals-expansion (`=cmd` → path lookup of `cmd`). A command like `echo ===` becomes
`rtk echo ===` and fails with `(eval):1: == not found`, exit 1.

## Impact
Any auto-wrapped command with a bare `=`-leading argument (separator banners like `echo
===`, comparisons passed as args) fails with a confusing error that looks like a shell
bug. Cousin of the archived `shell-hook-breaks-shell-variables.md` (leading `VAR=` case,
already guarded).

## How to reproduce
1. In a hooked Claude session run the Bash tool with `echo ===`.
2. Observed: exit 1, `(eval):1: == not found`. Expected: `===` printed.
3. Direct: `rtk echo ===` reproduces without the hook.

## Workaround
Quote the argument (`echo "==="`), or pre-prefix `rtk` yourself with quoting.

## Root cause / notes
zsh equals-expansion inside rtk's eval, not the hook JSON path. Narrowest fix on our side:
in the rtk fallback (Go + shell), pass through commands containing a whitespace-delimited
token that starts with `=`, mirroring the existing leading-assignment guard. An upstream
rtk fix (disable `equals` in its eval, or quote argv) would close it fully.

Mitigated: plans/gain-enforcement-fixes/02-rtk-equals-word-guard.md — the rtk fallback in
both `internal/hook/hook.go` and `providers/claude/hooks/shell-guard.sh` now passes
through commands containing a bare `=`-leading token instead of wrapping them. The
upstream rtk/zsh equals-expansion behavior itself is unchanged.

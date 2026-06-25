---
id: shell-hook-breaks-shell-variables
title: Shell hook breaks variable expansion (and sometimes cd) in Bash tool calls
severity: high
status: mitigated
area: shell-hook
discovered: 2026-06-25
---

## Summary
Under the active shell-guard / lean-ctx rewrite hook, shell variable expansion
(`$VAR`) inside a single Bash tool call is unreliable — variables frequently
expand to empty. `cd <dir> && <cmd>` is also inconsistent: it took effect for
some commands and was ignored for others. The net effect is that commands run
against the wrong path or the wrong repository with little warning.

## Impact
Commands silently execute against the primary working directory instead of the
intended target. Observed this session:

- `git -C "$MAIN" checkout ...` ran against the wrong repo because `$MAIN`
  expanded empty, briefly moving the other agent's branch and carrying its
  uncommitted work onto the wrong branch (recovered).
- `cd <worktree> && no-mistakes init` initialized the gate against the corporate
  repo `team-mtp/infra/boss-mr-infra-v2` (adding a `no-mistakes` git remote)
  instead of the intended `agentic-cfg` worktree (cleaned up with `eject` +
  remote removal).
- `MAIN=...; python3 "$G"` ran `python3 ""` and failed with "can't find
  '__main__'".

This is a wrong-target-execution hazard: recoverable, but easy to miss.

## How to reproduce
In a single Bash tool call:

```sh
FOO=/Users/me/somewhere
echo "$FOO"          # may print an empty line
git -C "$FOO" status # runs in the current cwd, not in $FOO
```

Expected: `$FOO` expands to the path. Observed: empty / lost, so path-targeted
flags silently fall back to the primary cwd.

## Workaround
Use **literal absolute paths** in every command; never rely on shell variables.
For git, prefer `git -C /literal/abs/path ...` (this works reliably with a
literal path). For scripts, invoke by absolute path
(`python3 /abs/path/script.py`) — the script's own directory still lands on
`sys.path`, so local imports resolve. Avoid `cd`-then-command; assume it may not
take effect for non-git tools.

## Root cause / notes
The PreToolUse Bash hook (shell-guard delegating to `lean-ctx hook rewrite` /
rtk) rewrites the command before execution; the rewrite appears to drop or
re-quote the assignment context so `$VAR` is unset when the real command runs.
Not fully diagnosed — the mitigation (literal paths) is reliable in practice.

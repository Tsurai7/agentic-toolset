---
name: terminal-rtk
description: >-
  Prefix shell commands with rtk on macOS to save tokens and context. Use for
  every terminal command you suggest or execute on the user's Mac.
---

# Terminal: rtk prefix

On **macOS**, native terminal commands run through token compression. Two layers
cooperate, enforced by the `shell-guard.sh` PreToolUse hook so it does not depend
on the agent remembering:

| Layer | Handles | Result |
|-------|---------|--------|
| lean-ctx | dev tools (`git`, `gh`, `npm`, `go`, `cargo`, `make`, `rg`, `ls`, `find`, …) | `lean-ctx -c "<cmd>"` |
| `rtk` | everything else lean-ctx leaves bare (`python3`, `node`, ad-hoc commands) | `rtk <cmd>` |

The hook applies exactly one wrapper per command and never double-wraps a command
that already starts with `lean-ctx ` or `rtk `.

## Rules

- When the lean-ctx MCP layer is connected, prefer the `ctx_shell` tool directly —
  it is first choice in the tool-precedence table. The hook is the backstop for
  when you reach for the native `Bash` tool anyway.
- For copy-paste commands you show the user on macOS, prefix `rtk` yourself
  (the hook only rewrites commands the agent actually executes).
- Never wrap an `rtk` command inside `ctx_shell`, or vice versa (double-wrapping).
- If the environment is not macOS, omit `rtk` unless the user says otherwise.

## Why

Both layers compress command output for the agent context window while preserving
useful signal. Before `shell-guard.sh`, this was only a soft instruction, so bare
commands such as `python3 evals/run.py` slipped through unprefixed; the hook closes
that gap.

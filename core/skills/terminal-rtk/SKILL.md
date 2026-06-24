---
name: terminal-rtk
description: >-
  Prefix shell commands with rtk on macOS to save tokens and context. Use for
  every terminal command you suggest or execute on the user's Mac.
---

# Terminal: rtk prefix

On **macOS**, prefix commands with **`rtk`**:

| Instead of | Use |
|------------|-----|
| `npm run build` | `rtk npm run build` |
| `cat src/main.ts` | `rtk cat src/main.ts` |
| `ls -la` | `rtk ls -la` |
| `git status` | `rtk git status` |

## Rules

- Apply to **every** terminal command you run or show for copy-paste on macOS
- Do not skip the prefix for "simple" commands
- If the environment is not macOS, omit `rtk` unless the user says otherwise

## Why

`rtk` compresses command output for the agent context window while preserving useful signal.

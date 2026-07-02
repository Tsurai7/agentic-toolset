---
id: gitnexus-home-registry-stale-nag
title: GitNexus home registry dir false-positives findGitNexusDir, causing stale-nag spam
severity: low
status: open
area: integrations/gitnexus
discovered: 2026-07-02
---

## Summary
The GitNexus hook file `~/.claude/hooks/gitnexus/gitnexus-hook.cjs` contains a `findGitNexusDir()` function that walks up the directory tree (≤5 levels from `cwd`) to locate a `.gitnexus` directory. The global registry directory `~/.gitnexus` (created by `gitnexus analyze` to store `registry.json`) matches this walk for every repository under `$HOME` at directory depth ≤4. This causes two problems: spurious "index is stale" nags after commits in never-indexed repos, and wasted `augment` CLI spawns during tool calls.

## Impact
(a) **False stale-nag:** PostToolUse hook after any successful `git commit|merge|rebase|cherry-pick|pull` in a repo that has never been indexed injects the message `GitNexus index is stale (last indexed: never). Run npx gitnexus analyze to update the knowledge graph.` — a false positive, since the repo has no index to be stale. Measured: every commit in a non-indexed repo under `$HOME`.

(b) **Wasted augment spawns:** PreToolUse hook on every Grep/Glob/grep-Bash call spawns the `augment` CLI (~80–140 ms latency per call in non-indexed repos, 210–380 ms in indexed repos) even when there is no local `.gitnexus` index to augment the results with.

## How to reproduce
1. Ensure you have a non-indexed repo under `$HOME` (e.g., a fresh checkout).
2. Run a git commit: `git commit -m "test"`.
3. Check the hook's JSON output (stdin to the hook with `hook_event_name` = `PostToolUse`, `tool_name` = `Bash`, `tool_input.command` = `git commit -m x`, `tool_output.exit_code` = 0, `cwd` = the non-indexed repo).
4. Observed: the hook's `additionalContext` includes `GitNexus index is stale (last indexed: never)…`. Expected: no nag, since the repo has no index.

## Workaround
None needed for indexed repos (the nag is legitimate there). The false nags appear only in non-indexed repos under `$HOME`.

## Root cause / notes
`findGitNexusDir()` in `gitnexus-hook.cjs` walks up from `cwd` to locate a `.gitnexus` directory without distinguishing between a **per-repo index** (with both `registry.json` and `meta.json`) and the **global registry directory** `~/.gitnexus` (containing only `registry.json`). A narrower search would skip the global registry dir — for example, by stopping the walk at `$HOME` or by checking for the presence of `meta.json` to confirm a real per-repo index.

**Upstream:** https://github.com/abhigyanpatwari/GitNexus, package `gitnexus`, observed on version 1.6.7, Node v20.12.2.

**Ownership:** The hook files (`gitnexus-hook.cjs` and `settings.json` entries) are self-installed by `gitnexus setup` (upstream), not by this repo. This repo does not patch them.

Measured 2026-07-02 on the primary machine.

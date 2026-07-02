# 02 — Hygiene: .gitignore the index dir + file the upstream stale-nag bug

**Rationale:** [DESIGN.md](DESIGN.md) Q1 finding 3 / Q4 wedge 3. Indexing a repo
creates an untracked `.gitnexus/` directory (this repo was indexed during the
investigation and `git status` would show it). Separately, upstream's self-installed
hook false-positives on the global registry dir.

## Change specification

### 1. `.gitignore`

Add a `.gitnexus/` entry (with a one-line comment in the file's existing comment
style, e.g. `# GitNexus per-repo knowledge-graph index (npx gitnexus analyze)`).
Verify placement matches the file's grouping conventions — read it first.

### 2. `issues/gitnexus-home-registry-stale-nag.md` (new)

Follow the exact structure of the existing issue files (read
`issues/rtk-wrap-breaks-equals-words.md` for the shape: title, Status, Component,
Filed, then sections). Content requirements:

- **Status:** open (upstream) — repo: https://github.com/abhigyanpatwari/GitNexus,
  package `gitnexus`, observed on 1.6.7.
- **Symptom:** `~/.claude/hooks/gitnexus/gitnexus-hook.cjs` `findGitNexusDir()` walks
  up ≤5 levels from `cwd` looking for a `.gitnexus` directory. The **global registry
  dir** `~/.gitnexus` (created by `gitnexus analyze` to hold `registry.json`) matches
  for every repo under `$HOME` at depth ≤4. Consequences, both measured 2026-07-02:
  (a) PostToolUse after any successful `git commit|merge|rebase|cherry-pick|pull` in
  a **never-indexed** repo injects `GitNexus index is stale (last indexed: never).
  Run npx gitnexus analyze …` — a false nag; (b) PreToolUse spawns the `augment` CLI
  (~80–140 ms) on every Grep/Glob/grep-Bash call in non-indexed repos, returning
  nothing.
- **Repro:** the two-line hook invocation with a PostToolUse JSON payload on stdin
  (take it from DESIGN.md's investigation or reconstruct: `hook_event_name`
  `PostToolUse`, `tool_name` `Bash`, `tool_input.command` `git commit -m x`,
  `tool_output.exit_code` 0, `cwd` = any non-indexed repo) and the observed JSON
  output with the "last indexed: never" additionalContext.
- **Expected:** the walk-up should ignore the registry dir (e.g. skip when the found
  dir contains `registry.json` but no `meta.json`, or stop the walk at `$HOME`).
- **Workaround:** none needed for indexed repos (the nag is legitimate there); noise
  only in non-indexed ones. Note that the hook files are upstream-owned
  (self-installed by `gitnexus setup`), so this repo does not patch them.

## Acceptance criteria (hard)

1. `git check-ignore -v .gitnexus/somefile` (from the repo root, after creating no
   real file — use `git check-ignore -v .gitnexus/x` which needs no file to exist)
   reports the new `.gitignore` rule.
2. `git status --porcelain` no longer lists `.gitnexus/` (the dir exists on disk from
   the investigation).
3. The new issue file exists, matches the structural conventions of the existing
   `issues/*.md` files (same heading/metadata pattern), and contains: the upstream
   repo URL, the measured latency numbers, a copy-pasteable repro, and an explicit
   note that the hook files are upstream-owned.
4. `bash bin/ci-check.sh` passes; `bash bin/prefix-budget.sh` byte total unchanged.
5. Diff touches only: `.gitignore`, `issues/gitnexus-home-registry-stale-nag.md`.

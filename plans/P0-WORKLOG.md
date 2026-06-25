# P0 work-log — "stop the bleeding"

Detailed record of **what** was changed in the P0 phase and **why** each choice
was made. Branch: `fix/p0-stop-the-bleeding` (off `master`). Companion to the
roadmap in [00-master-plan.md](00-master-plan.md).

Date: 2026-06-26.

---

## 0. Context and branching

**What:** Cut a `fix/p0-stop-the-bleeding` branch off `master` (not off the
checked-out `feature/value-evals-loop`).

**Why:** A pre-flight `git` check showed `master` was **11 commits ahead** of the
feature branch, including a newer `shell-guard.sh` and whole new subsystems
(`telemetry/`, `core/memory/`, `evals/metric/`, `issues/`). The five review docs
(01–05) had been written against the stale feature branch, so working there would
have re-introduced fixed bugs and missed existing work. `master` is checked out in
another worktree (`acfg-telemetry`), so the branch was created from the `master`
ref directly. Per git-safety, P0 work goes on a topic branch, never on `master`.

**Re-baseline corrections** (full list in [§7.1](00-master-plan.md#71-re-baseline-vs-master)):
- BUG-01 (multiline command corruption) was **already fixed** on `master` by
  `6f8b9f1` (multiline / `$(...)` / `cd` fail-open). BUG-04 became a deliberate
  fail-open.
- Token/cache **measurement already exists** (`telemetry/` + a cache-hit-rate
  gate), so doc 02's "Observability: Nascent" and doc 05's "nothing measures
  tokens" were overstated.
- PORT-01/02/03, BUG-10, BUG-03, BUG-06 and the `$VAR` hazard were all still real
  on `master` — those are what P0 fixes.

---

## 1. PORT-02 — settings hooks were clobbered (commit `1dc45df`)

**What:** Rewrote the `hooks` handling in
[providers/shared/merge-settings.py](../providers/shared/merge-settings.py) from a
wholesale `result["hooks"] = fragment["hooks"]` to a per-event deep-merge
(`merge_hooks`): for each event the repo manages, only *our* groups are dropped and
re-added; every user-added group, and every event the fragment doesn't mention, is
preserved.

**Why:** The old line discarded **all** pre-existing user hooks (any event) on
every install — a direct violation of the "don't clobber existing configs" goal.
"Ours" is detected by command identity: a group is replaceable only if every
command in it is managed (matches a fragment command, contains
`/providers/claude/hooks/`, or starts with `lean-ctx hook `). This recognizes our
entries even if the repo path moved or an older fragment registered an extra
lean-ctx subcommand, while never touching a group that contains a user command.

**How chosen:** Group-level (not whole-block) replacement is the smallest change
that preserves user hooks; finer per-command merging across matchers is deferred to
the Go rewrite (P1).

## 2. BUG-10 — `"$schema": null` (commit `1dc45df`)

**What:** Changed `result.setdefault("$schema", fragment.get("$schema"))` to only
set `$schema` when the fragment actually has one.

**Why:** On a fresh settings file with a fragment lacking `$schema`, the old code
wrote `"$schema": null`, which is invalid/noise. Latent today (the shipped fragment
has a `$schema`) but a real defect.

## 3. PORT-01 — `CLAUDE.md` was overwritten (commit `1dc45df`)

**What:** New helper
[providers/shared/merge-claude-md.py](../providers/shared/merge-claude-md.py) plus a
rewrite of `install_claude_md` in
[providers/claude/install.sh](../providers/claude/install.sh). The full instruction
block is now rendered to a repo-owned `~/.claude/agentic-cfg.generated.md`, and the
user's `~/.claude/CLAUDE.md` carries only a small managed block:

```
<!-- BEGIN agentic-cfg (managed) -->
@~/.claude/agentic-cfg.generated.md
<!-- END agentic-cfg (managed) -->
```

A legacy fully-generated `CLAUDE.md` (detected by the old generator signature) is
migrated in place to the managed block, so its inline content is not duplicated.
The `CLAUDE.md.stub` "do not edit" notice now points at the generated file.

**Why:** The old installer overwrote the entire `CLAUDE.md`, destroying any
hand-written user content (a `.bak` was kept, but the live global-memory file was
replaced). Claude Code's `@import` (confirmed via the claude-code-guide: relative /
absolute / `~` paths, depth 5, treated as always-on context) lets us keep our
content fully isolated in a file we own while leaving a 3-line footprint in the
user's file. This is decision **D5** — `@import` over inline managed blocks, chosen
because it isolates our content (overwrite-safe) and minimizes the footprint.

## 4. PORT-03 — gitnexus MCP never loaded (commit `e3af102`)

**What:** Added a `--register-claude-user` mode to
[providers/shared/merge-mcp.py](../providers/shared/merge-mcp.py) that resolves the
managed fragments (per-machine paths + placeholder substitution, reusing the
existing logic) and registers each server via
`claude mcp add-json <name> <json> --scope user` (removing first for idempotency).
`install_mcp` now calls this instead of writing `~/.claude/.mcp.json`. Cursor-only
fields like `autoApprove` are stripped; it is a no-op with a warning if the `claude`
CLI is absent.

**Why:** Confirmed empirically (decision **D3**): the repo wrote
`~/.claude/.mcp.json`, but **Claude Code reads user-scope MCP from `~/.claude.json`**
(verified live — gitnexus was configured yet not loaded in-session, while
hand-registered lean-ctx was). The `claude` CLI is the safe contract for editing
`~/.claude.json` (Claude Code's live state file with startup counters, project
history, etc.); a hand-rolled read-modify-write would risk a concurrency race.
`add-json` was chosen over `add` because it takes the resolved server JSON directly,
preserving `command`/`args`/`env`. The dead `~/.claude/.mcp.json` is left untouched
(non-destructive) rather than deleted.

## 5. BUG-03 / BUG-06 / `$VAR` hazard — shell-guard hardening (commit `9183378`)

**What:** Two surgical fixes in
[providers/claude/hooks/shell-guard.sh](../providers/claude/hooks/shell-guard.sh):
1. The ast-grep deny now tests the command **with quoted substrings removed**, so a
   code extension that only appears inside a search pattern no longer triggers a
   deny. Real code-file targets still deny.
2. The rtk fallback **passes through untouched** any command with a leading `VAR=`
   assignment, instead of prefixing a naive `rtk`.

Also updated [issues/shell-hook-breaks-shell-variables.md](../issues/shell-hook-breaks-shell-variables.md)
to `status: fixed` with the diagnosis.

**Why:** Characterized with an evidence probe against the live hook:
- `grep "foo.py" data.csv` was **denied** even though it targets a CSV — the `.py`
  was only in the search pattern (BUG-03). This false-deny fires on legitimate
  greps every session (it blocked the review agents' own commands).
- `FOO=/tmp; echo $FOO` was rewritten to `rtk FOO=/tmp; echo $FOO`, which scopes the
  assignment to rtk's subshell so `$FOO` is empty afterward — the documented
  wrong-target hazard (it had moved another agent's branch). Same root cause made
  `FOO=1 rtk …` become `rtk FOO=1 rtk …` (BUG-06).

The fix is deliberately minimal: only a **leading** assignment is unsafe for a
naive prefix (a mid-command `cmd && FOO=x other` runs `FOO=x other` correctly when
bare), and variable *use* like `echo "$HOME"` is safe and stays wrapped — so
compression coverage is preserved for the common case. The deeper, fully-typed hook
(real JSON parsing, no grep/sed) is the Go rewrite (P1); this is the interim
correctness fix.

---

## 6. Verification approach (why it is trustworthy)

Every change was verified before commit, and the static gate (`bin/ci-check.sh`,
which shellchecks the hook and lints/​self-tests the evals) was green after each:

- **merge-settings:** 14 unit assertions against the real fragment (fresh install,
  `$schema` null, preservation of user hooks/env/deny/allow, idempotency).
- **Full Claude installer:** 22 assertions running the real installer against a
  **fixture `$HOME`** (`HOME` overridden to `/tmp`, `CLAUDE_CONFIG_DIR` cleared) —
  a pre-existing `CLAUDE.md`, settings hooks, `env`, and a hand-added MCP server all
  survive; legacy migration does not duplicate; the run is idempotent; and a
  **safety net asserts the real `~/.claude.json` is byte-unchanged**.
- **PORT-03:** an isolated probe first confirmed `claude mcp add-json --scope user`
  writes to `$HOME/.claude.json` and errors on duplicates (hence remove-then-add).
- **shell-guard:** a 9-case assertive harness plus a **live-pipeline** check
  (`FOO=hello; echo "[$FOO]"` → `[hello]`, previously `[]`).

The hook was edited test-first (`bash -n` syntax check + harness) because it is the
**live** hook for the working session; a bad edit would have disrupted the session's
own Bash calls.

---

## 7. Decisions

D1–D6 are resolved in [00-master-plan.md §7](00-master-plan.md#7-decisions-resolved).
P0 implemented D3 (MCP path) and D5 (CLAUDE.md `@import` + hook deep-merge).

## 8. Not done / next

- **Not yet applied to the real machine.** These fixes are committed code; running
  `bin/install.sh --provider claude` applies them (registers gitnexus, migrates the
  real `CLAUDE.md` to `@import`). Held for owner approval since it mutates `~/.claude`.
- **P1:** the `agentic` Go CLI (front-load merge-mcp + hook), carrying P0 semantics
  forward as golden tests.
- **P2/P3:** CI + integration + Haiku/token evals on top of `telemetry/`; then
  instruction de-dup, the locked subagent, release hygiene.
- The fixture test scripts live in `/tmp` for now; P2's plan is to promote them into
  the repo as permanent golden/integration tests.

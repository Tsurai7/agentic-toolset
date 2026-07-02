# Plan 08 — Cursor side: merge don't clobber, clean up stale artifacts, eject

[Index](00-INDEX.md) · Wave B · Files: `providers/cursor/install.sh`,
`providers/shared/merge-mcp.py` (cursor-path only — plan 06 later touches the
claude registration loop; keep your diff confined to cursor/file-merge code
paths), `providers/cursor/mcp.overlay.json` (delete if vestigial).

## Context (findings)

1. **MAJOR.** `providers/cursor/install.sh` (~62–70) copies `hooks.json` over
   `~/.cursor/hooks.json` unconditionally (`run cp "$src" "$out"`);
   `backup_once` preserves only the pre-FIRST-install file. Any hook the user
   added by hand is silently destroyed on every install — unlike the Claude
   side's managed-group merging.
2. **MINOR.** Cursor MCP merge is add-only: integration fragments removed from
   the repo stay in `~/.cursor/mcp.json` forever; deleted rules leave dangling
   symlinks in `~/.cursor/rules/`; renamed principles leave orphan
   `principle-*.mdc` files. No eject exists for Cursor (Claude has
   `agentic eject`).
3. **SUGGESTION.** `providers/cursor/mcp.overlay.json` is a vestigial empty
   `{"mcpServers": {}}` — the merge already starts from that.

## Changes

1. **hooks.json merge**: replace the blind `cp` with a merge: parse existing
   `~/.cursor/hooks.json` (tolerate absent/empty), overwrite ONLY the keys the
   repo fragment defines (its hook entries), preserve unknown user keys/entries,
   write atomically via `providers/shared/safe_io.py` (import or invoke a small
   python helper — do not hand-roll another atomic writer). Back up the target
   with the same timestamped scheme the installer uses elsewhere, every run
   that changes content (not just once). If the fragment and existing content
   are identical, do nothing (idempotent, no backup churn).
2. **Managed-server bookkeeping for Cursor MCP**: `merge-mcp.py`'s cursor/file
   path records the set of repo-managed server names in a sidecar
   `~/.cursor/.agentic-managed.json` (list of names + schema version). On each
   merge: servers in the sidecar but no longer in fragments are REMOVED from
   `mcp.json`; user-added servers (never in the sidecar) are untouched. First
   run without a sidecar: bootstrap it from the current fragment set only (do
   not retro-claim existing entries).
3. **Symlink hygiene in install_rules / link_skills**: before linking, remove
   dangling symlinks inside `~/.cursor/rules/` and `~/.cursor/skills/` that
   point into any `agentic-cfg` checkout (test: symlink target unresolvable OR
   resolves under a path ending `/agentic-cfg/...`); print one line per removal.
4. **Cursor eject**: add `--eject` handling to `providers/cursor/install.sh`
   (wired from `bin/install.sh --provider cursor --eject` if the entry point
   parses flags there — follow how the Claude eject is invoked; if eject lives
   only in the Go CLI, add a shell `eject_cursor` function called via an env
   var/flag, keeping symmetry): removes repo symlinks (skills/rules), managed
   MCP servers (per sidecar), the repo-managed hooks.json keys, and the
   sidecar itself. Dry-run aware.
5. Delete `providers/cursor/mcp.overlay.json` if — verify first — nothing
   reads it except the merge default (grep for `overlay` in providers/ and
   bin/); update any comment that mentions it.

## Acceptance criteria

All against a TEMP fake `~/.cursor` (export `HOME=<tmp>` or the installer's
test override — check how `internal/installtest` fakes HOME; never touch the
real one in this plan):

1. Pre-seed `hooks.json` with a user hook key + run install twice: user key
   survives both runs byte-identical; repo keys present; second run makes no
   backup (idempotent). Show diffs.
2. Add a fake fragment server, install, remove the fragment, install again:
   server is gone from `mcp.json`; a hand-added server (edited into the target
   between runs) survives both installs. Show the sidecar content evolving.
3. Create a dangling rule symlink into a fake old clone path; install removes
   it and reports it; a user's non-agentic symlink/file in `~/.cursor/rules/`
   survives.
4. Eject: after a full install, eject leaves `~/.cursor` with zero
   agentic-managed artifacts (list the dir trees before/after) while the
   user hook key and hand-added server remain.
5. `DRY_RUN=1 bash bin/install.sh --provider cursor` prints the new steps
   without writing (verify no file mtime changes in the fake HOME).
6. `bash bin/ci-check.sh` exits 0; `shellcheck -S warning providers/cursor/install.sh` clean;
   `python3 evals/lint.py` unaffected.
7. `git status` touches only header files.

## Out of scope

Claude-side registration loop (plan 06). The cursor-rules-pointer path text
(plan 05). Real-machine application (plan 10 — note: plan 10 currently applies
the CLAUDE side; if you finish early, do NOT run the cursor install against the
real HOME — leave that to plan 10's operator).

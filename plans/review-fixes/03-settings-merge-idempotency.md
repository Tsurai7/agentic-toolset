# Plan 03 — settings merge: recognize managed lean-ctx groups by basename

[Index](00-INDEX.md) · Wave B · Files: `internal/settings/settings.go`,
`internal/settings/settings_test.go` (and the Python twin
`providers/shared/merge-settings.py` if it has the same gap — verify).

## Context (findings)

**MAJOR, reproduced.** `isManagedGroup` (`internal/settings/settings.go`
~lines 222–237) recognizes a hook group as repo-managed only when a command is
literally prefixed `lean-ctx hook ` (~line 231). A group whose command is
`/opt/homebrew/bin/lean-ctx hook rewrite` is treated as user-owned, so merge
keeps it AND appends the fragment's group → duplicate groups. This is the live
state of `~/.claude/settings.json` today: two `Bash|bash` groups both running
shell-guard.sh, plus a standalone absolute-path `lean-ctx hook rewrite` — every
Bash call spawns 4–5 hook processes. The same gap affects `Unmerge`/eject.

## Changes

1. In `internal/settings/settings.go`, make the managed-command check
   path-insensitive: a command counts as managed when, after taking the first
   whitespace-separated token's **basename**, it equals `lean-ctx` and the next
   token is `hook` (i.e. `…/lean-ctx hook <anything>`), OR it matches the
   existing repo-hook patterns (shell-guard.sh / edit-lint.sh entries — check
   whether those are matched by path suffix today; if they are matched by full
   `__AGENTIC_ROOT__`-expanded path, also compare by basename suffix
   `providers/claude/hooks/<name>.sh` so a moved clone still dedups).
2. Apply the same recognition in every place that classifies groups
   (`Merge`, `Unmerge`, eject path) — grep for the literal `"lean-ctx hook"`
   string in the package and unify into one helper, e.g.
   `isManagedCommand(cmd string) bool`.
3. Add table-driven tests in `internal/settings/settings_test.go`:
   - existing settings contain `/opt/homebrew/bin/lean-ctx hook rewrite` group
     → after Merge, exactly ONE group per managed matcher; the absolute-path
     standalone group is gone (replaced by the fragment's canonical set).
   - existing settings contain a duplicate shell-guard group (simulating
     today's live file) → Merge dedups to one.
   - a genuinely user-owned hook (e.g. `my-custom-hook.sh`) survives Merge
     unchanged.
   - Unmerge/eject removes path-qualified managed groups too.
4. Check `providers/shared/merge-settings.py` for the same literal-prefix
   logic; if present, mirror the basename fix there (the two implementations
   must agree — that is an existing repo invariant, see BUG-14 precedent).

## Acceptance criteria

1. `go test ./internal/settings/ -count=1 -v` — all pass, including the four new
   cases above (paste the new test names + PASS lines in your report).
2. Reproduction proof: feed a settings JSON mimicking the live duplicate state
   (two shell-guard groups + one `/opt/homebrew/bin/lean-ctx hook rewrite`
   group) through `bin/agentic merge-settings` (build with
   `go build -o bin/agentic ./cmd/agentic` first; use a temp HOME or the
   command's file arguments — read `cmd/agentic` to see how it takes paths;
   do NOT touch the real `~/.claude/settings.json`). Show before/after group
   counts per matcher: after = 1 group per managed matcher.
3. If `merge-settings.py` needed the fix: run its self-test path
   (`bash bin/ci-check.sh` merge-helpers section) — OK; plus a manual
   `python3 providers/shared/merge-settings.py` invocation on the same fixture
   produces the same result as the Go path (byte-identical hook groups).
4. `go vet ./...` and `golangci-lint run` — clean.
5. `git status` touches only the files named in the header (plus
   `providers/shared/merge-settings.py` if the twin fix applied).

## Out of scope

Cleaning the live `~/.claude/settings.json` — plan 10 does that by re-running
the installer once this fix makes the merge idempotent.

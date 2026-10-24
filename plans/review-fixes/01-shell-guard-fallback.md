# Plan 01 — shell-guard fallback: stop corrupting multi-line commands

[Index](00-INDEX.md) · Wave A · No file overlap with plan 04.

## Context (findings)

1. **CRITICAL, reproduced.** `providers/claude/hooks/shell-guard.sh` fallback path
   (used whenever `bin/agentic` is absent) extracts the Bash command from hook
   JSON with grep/sed and unescapes only `\"` and `\\` (`extract()`, ~lines
   28–37). A JSON `\n` therefore survives as the two literal characters `\n`;
   the "multi-line → fail open" guard at ~line 58 tests for a *real* newline
   (`*$'\n'*`) which can never occur in valid JSON, so it is dead code. Result:
   input `{"command":"echo a\necho b"}` is rewritten to
   `"command":"rtk echo a\\necho b"` → bash executes `rtk echo anecho b`.
   The Go port already fixed this class (BUG-01, `internal/hook/hook_test.go`).
2. **MAJOR.** The documented flow (`bin/install.sh --provider all`) never builds
   `bin/agentic` (only `bin/bootstrap.sh` does), so fresh machines run the broken
   fallback; and a previously built, stale `bin/agentic` silently shadows pulled
   fixes (`providers/claude/install.sh` prefers the binary with no staleness check).
3. **MINOR, reproduced.** The grep-token deny regex matches `grep` in argument
   position in both implementations (`shell-guard.sh` ~line 69,
   `internal/hook/hook.go` ~line 46): `git grep TODO main.py` is denied.
4. Dead code: `PowerShell|powershell` arm (~line 41) in a macOS-only hook.

## Changes

### 1. Fix `extract()` unescaping in `providers/claude/hooks/shell-guard.sh`

- After the existing `\"` / `\\` handling, also unescape `\n` → real newline,
  `\t` → tab, `\r` → CR (order matters: handle `\\` so `\\n` does not become a
  newline — mirror the Go implementation's approach in `internal/hook/hook.go`).
- Keep the fail-open guard: now that a real newline can appear, the existing
  `*$'\n'*` check becomes live — a multi-line command must be passed through
  UNMODIFIED (exit 0, no rewrite envelope), exactly like the Go port.
- If exact sed-based unescaping of `\\` vs `\n` cannot be made unambiguous in
  POSIX shell, an acceptable alternative: detect the two-char sequences `\n`,
  `\t`, `\r` in the *raw extracted* string and fail open (exit 0, no output)
  before any rewrite. Correct-but-conservative beats clever.

### 2. Fix grep-in-argument-position in BOTH implementations

- The deny should trigger only when `grep`/`rg`/`egrep`/`fgrep` is the command
  word (start of string, or after `|`, `;`, `&&`, `||`, `$(`, backtick),
  not anywhere in the string. Apply the same anchoring in
  `shell-guard.sh` and `internal/hook/hook.go`, and add/extend a Go test:
  `git grep TODO main.py` → allowed; `grep -r foo src/` → denied;
  `cat x | grep foo` → denied (still a real grep invocation).

### 3. Remove the dead PowerShell arm from `shell-guard.sh`.

### 4. Build `bin/agentic` from the installer

- In `bin/install.sh`, before dispatching to providers: if `command -v go`
  succeeds, run `go build -o bin/agentic ./cmd/agentic` (from `AGENTIC_ROOT`);
  on build failure or missing Go, print a single WARN line that the shell
  fallback will be used. Respect `DRY_RUN=1` (print, don't build).
- This also fixes the stale-binary problem: every install rebuilds.

### 5. Add a fallback-path selftest to `bin/ci-check.sh`

- New section "shell-guard fallback self-test" that runs
  `providers/claude/hooks/shell-guard.sh` with `AGENTIC_BIN=/nonexistent` (or
  however the script locates the binary — force the fallback path; if there is
  no env override today, add one, e.g. `SHELL_GUARD_NO_GO=1`) and asserts:
  a) single-line `{"command":"echo hi"}` → rewrite envelope containing `rtk echo hi`;
  b) multi-line `{"command":"echo a\necho b"}` → NO `updatedInput` in output (fail-open);
  c) `{"command":"git grep TODO main.py"}` → not denied;
  d) `{"command":"grep -r foo src/"}` → denied.
- Follow the existing style of the edit-lint self-test section in `ci-check.sh`.

## Acceptance criteria

1. `printf '{"tool_name":"Bash","tool_input":{"command":"echo a\\necho b"}}' | <force-fallback> providers/claude/hooks/shell-guard.sh`
   produces NO `updatedInput` (command passes through untouched). Show the raw output in your report.
2. Same invocation with `{"command":"echo hi"}` produces an envelope whose
   `updatedInput.command` is exactly `rtk echo hi`.
3. `{"command":"git grep TODO main.py"}` is NOT denied by either implementation;
   `go test ./internal/hook/ -run . -count=1` passes with the new/updated cases.
4. `bash bin/install.sh --dry-run` output includes the build (or build-skip WARN) line.
5. `bash bin/ci-check.sh` exits 0 and its output contains the new
   "shell-guard fallback" section with all checks OK.
6. `shellcheck -S warning providers/claude/hooks/shell-guard.sh` — clean.
7. `git status` touches only: `providers/claude/hooks/shell-guard.sh`,
   `internal/hook/hook.go`, `internal/hook/hook_test.go`, `bin/install.sh`,
   `bin/ci-check.sh`.

## Out of scope

Anchoring of hook *matchers* (plan 02), settings merge (plan 03), atomic writes
in the installer (plan 06).

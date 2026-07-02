# 02 — rtk fallback: pass through commands containing a bare `=`-leading token

**Problem** (audit finding 8, [issues/rtk-wrap-breaks-equals-words.md](../../issues/rtk-wrap-breaks-equals-words.md)):
the rtk fallback wraps simple commands as `rtk <cmd>`; rtk 0.40.0 evaluates the command
through zsh, where an unquoted word starting with `=` triggers equals-expansion
(`=cmd` → PATH lookup). `echo ===` becomes `rtk echo ===` and fails with
`(eval):1: == not found`, exit 1. Reproduced directly: `rtk echo ===` fails identically.

## Change specification

### `internal/hook/hook.go` — rtk fallback branch only

In `shellGuard`, immediately before `writeRewrite(stdout, "rtk "+cmd)` (i.e. in the same
block as the existing `leadingAssignRe` pass-through), add a pass-through when **any
whitespace-delimited token of the command starts with `=`**. Suggested: a package-level
`equalsTokenRe = regexp.MustCompile(`(^|\s)=`)` — the command has already fail-opened on
quotes-free complexity paths, but note `=` inside quotes is an acceptable false-positive
for a *pass-through* (the command just runs uncompressed; correctness beats compression,
matching the file's "correct-but-conservative beats clever" comment style).

This guard applies **only** to the rtk fallback (step 3). The ast-grep deny and the
lean-ctx delegate are unaffected.

### `providers/claude/hooks/shell-guard.sh` — mirror

In section `--- 3. rtk fallback ---`, next to the existing leading-assignment check, add
the equivalent pass-through (e.g. `case " $CMD" in *' ='*) exit 0;; esac` — note the
leading-space trick covers both a first token and mid-command tokens; keep it POSIX).

### Tests

- `internal/hook/hook_test.go`:
  - `echo ===` → **no output** (pass through, no rewrite).
  - `echo = separator` → **no output**.
  - `echo a=b` → rewritten to `rtk echo a=b` (token does not *start* with `=`).
  - `echo hi` → rewritten to `rtk echo hi` (baseline unchanged).
  - `FOO=1 echo hi` → no output (existing leading-assignment behavior — must not regress).
- `bin/ci-check.sh` fallback self-test: add `echo ===` → must **not** be rewritten.

### Issue bookkeeping

Set `status: mitigated` in `issues/rtk-wrap-breaks-equals-words.md` (the upstream rtk/zsh
behavior still exists; our wrapper no longer triggers it) and append a one-line note.

## Acceptance criteria (hard)

1. `printf '{"tool_name":"Bash","tool_input":{"command":"echo ==="}}' | ./bin/agentic hook shell-guard`
   prints **nothing** (no rewrite).
2. Same via `SHELL_GUARD_NO_GO=1 bash providers/claude/hooks/shell-guard.sh` — nothing.
3. End-to-end sanity: plain `echo ===` in a shell (no rtk prefix) prints `===` with
   exit 0 — i.e. after the fix the hook lets it run natively.
4. `printf '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}' | ./bin/agentic hook shell-guard`
   still prints an `updatedInput` rewrite to `rtk echo hi` (fallback not disabled).
5. `go test ./internal/hook/` and `bash bin/ci-check.sh` pass with the new cases.
6. `issues/rtk-wrap-breaks-equals-words.md` frontmatter says `status: mitigated`.
7. Diff touches only: `internal/hook/hook.go`, `internal/hook/hook_test.go`,
   `providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`, the issue file.

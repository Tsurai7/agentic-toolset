# 01 — Shell-guard: evaluate the ast-grep deny before the already-wrapped exit

**Problem** (audit finding 7, [issues/shell-guard-astgrep-order-bypass.md](../../issues/shell-guard-astgrep-order-bypass.md)):
in both the Go hook (`internal/hook/hook.go`, `shellGuard`) and the shell fallback
(`providers/claude/hooks/shell-guard.sh`), the "already wrapped — never double-wrap"
early exit runs **before** the ast-grep guard. `rtk grep -n foo x.go` is therefore
allowed, and transcripts show a model exploiting exactly this after being denied.

## Change specification

### `internal/hook/hook.go` — new decision order in `shellGuard`

1. Parse / tool-name / empty-command checks — unchanged.
2. Complex-command fail-open (`<<`, newline, `$(`, backtick, `cd` chains) — unchanged,
   stays **first** among the guards. Multiline grep-on-code remains fail-open by design
   (see DESIGN.md Part 2 — false-positive risk inside heredocs).
3. **ast-grep deny — moved up.** Evaluate `grepTokenRe` + `codeExtRe` (quoted-substring
   stripping unchanged) against a *normalized* command: the original command with any
   leading `VAR=` assignments **and** any leading `rtk ` / `lean-ctx ` wrapper prefixes
   stripped (strip repeatedly until fixpoint, so `FOO=1 rtk grep …` normalizes to
   `grep …`). Deny envelope and `astGrepReason` text unchanged.
4. Already-wrapped exit (`rtk ` / `lean-ctx ` after assignment stripping) — unchanged
   logic, now runs *after* the deny.
5. lean-ctx delegate, then rtk fallback — unchanged.

Implementation note: add a small helper (e.g. `stripWrappers(s string) string`) next to
`stripLeadingAssignments`; do not inline the loop twice.

### `providers/claude/hooks/shell-guard.sh` — mirror the same order

Move section `--- 1. ast-grep guard ---` so it runs **before** the
`# Already wrapped — never double-wrap.` case, keeping it *after* the complex-command
fail-open case. Apply the guard's two regex tests to a normalized copy of `$CMD` with
leading `rtk `/`lean-ctx ` prefixes stripped (a simple `while` over
`case "$NORM" in rtk\ *|lean-ctx\ *)` is fine; POSIX-compatible, no bashisms beyond what
the file already uses). The already-wrapped case itself keeps operating on the original
`$CMD`.

### Tests

- `internal/hook/hook_test.go` — add table cases:
  - `rtk grep -n foo internal/hook/hook.go` → **deny** envelope.
  - `lean-ctx grep -rn foo src/main.go` → **deny**.
  - `FOO=1 rtk grep TODO cmd/agentic/main.go` → **deny**.
  - `rtk grep "foo.py" data.csv` → **allow, untouched** (code ext only inside quotes).
  - `rtk ls -la` → **allow, untouched** (already-wrapped exit still prevents double-wrap).
  - `git grep TODO main.py` → **allow** (grep not in command position — existing
    behavior, must not regress).
- `bin/ci-check.sh` shell-guard fallback self-test (`SHELL_GUARD_NO_GO=1` block around
  line 120): add one case — `rtk grep -r foo src/main.go` must be **denied**; and one —
  `rtk ls` must **not** be rewritten. Follow the existing `sg_out` helper pattern and the
  existing stubbed-PATH setup; do not restructure the block.

### Issue bookkeeping

Set `status: resolved` in `issues/shell-guard-astgrep-order-bypass.md` frontmatter and
append a one-line resolution note (commit/plan reference). Do not move the file.

## Acceptance criteria (hard)

1. `printf '{"tool_name":"Bash","tool_input":{"command":"rtk grep -n foo internal/hook/hook.go"}}' | ./bin/agentic hook shell-guard`
   prints a JSON envelope containing `"permissionDecision":"deny"`.
2. The same input through
   `SHELL_GUARD_NO_GO=1 bash providers/claude/hooks/shell-guard.sh` also prints the deny
   envelope.
3. `printf '{"tool_name":"Bash","tool_input":{"command":"rtk ls -la"}}' | ./bin/agentic hook shell-guard`
   prints **nothing** (allow, no rewrite, no double wrap).
4. `go test ./internal/hook/` passes, including all new cases above.
5. `bash bin/ci-check.sh` passes, including the two new fallback self-test cases and all
   pre-existing ones (notably: multiline command still not rewritten; `git grep TODO
   main.py` still not denied).
6. `issues/shell-guard-astgrep-order-bypass.md` frontmatter says `status: resolved`.
7. Diff touches only: `internal/hook/hook.go`, `internal/hook/hook_test.go`,
   `providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`, the issue file.

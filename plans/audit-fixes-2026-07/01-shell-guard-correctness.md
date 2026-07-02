# 01 — Shell-guard classifier correctness

**Owner:** one implementer (all files below are exclusive to this plan).
**Files:** `internal/hook/hook.go`, `internal/hook/hook_test.go`,
`providers/claude/hooks/shell-guard.sh`, `bin/ci-check.sh`,
`issues/shell-guard-astgrep-order-bypass.md`,
`issues/rtk-wrap-breaks-equals-words.md`.

The Go path (`shellGuard` execs `bin/agentic`) and the shell fallback must
agree. The prior wave diverged them. Every fix here is verified on **both**
paths: the Go binary (`go build -o <tmp>/agentic ./cmd/agentic`) and the shell
fallback (`SHELL_GUARD_NO_GO=1 bash providers/claude/hooks/shell-guard.sh`),
with a stub `rtk` on PATH and no `lean-ctx`, mirroring `bin/ci-check.sh`'s
self-test harness.

---

## A1 — [BUG, high] `Classify()` denies before the complex-command fail-open

**Evidence.** `internal/hook/hook.go:112` evaluates the ast-grep deny; the
complex fail-open is at `:125`. The shell has complex fail-open at
`shell-guard.sh:75-77` (and the `\n/\t/\r` bail at `:64-66`) **before** the deny
at `:98`. Plan 01 of the prior wave specified the fail-open "stays **first**",
and `DESIGN.md` Part 2 documents multiline/heredoc grep-on-code as fail-open by
design. The current Go order denies `grep TODO main.go\necho b`,
`grep TODO main.go <<EOF…`, `cd src && grep TODO main.go`,
`grep TODO main.go $(pwd)`, and the false positive
`grep bug notes.txt <<EOF\nsee main.go\nEOF` (grep targets `notes.txt`; `.go`
only in the heredoc body). `gain --adoption` (`gain.go:309`) inherits the wrong
classification.

**Fix.** In `Classify()`, move the complex-command fail-open block
(currently `hook.go:125-129`) **above** the deny block (`:112-114`), so the
order is: empty → complex-fail-open → deny(normalized) → already-wrapped →
assign → equals → wrap. Keep the deny above already-wrapped (that part of the
prior wave was correct — it makes `rtk grep foo.go` deny instead of passing).
Update the `Classify` doc comment (`hook.go:97-100`) and the package doc
(`hook.go:6`, "Behavior mirrors the fixed shell hook") to state the order
truthfully.

**AC1.** These commands print nothing (fail open) on **both** paths:
```
grep TODO main.go\necho b          # multiline
grep TODO main.go <<EOF\nx\nEOF     # heredoc
cd src && grep TODO main.go         # cd chain
grep TODO main.go $(pwd)            # command substitution
grep bug notes.txt <<EOF\nsee main.go\nEOF   # heredoc-body false positive
```
**AC2.** These still **deny** on both paths (no regression):
```
grep TODO main.go
rtk grep -n foo internal/hook/hook.go
grep -r --include=*.go TODO .
```
**AC3.** Add a Go table case per AC1 line to `hook_test.go` asserting
`DecisionFailOpenComplex`, and a `bin/ci-check.sh` fallback self-test case for a
complex+grep-on-code command (`cd src && grep TODO main.go` → not denied).
**AC4.** `go test ./internal/hook/ -count=1` and `bash bin/ci-check.sh` pass.

---

## A2 + A4 — [BUG, high] shell fallback doesn't normalize like Go

**Evidence.** The Go path strips leading `VAR=` assignments and wrapper
prefixes to fixpoint (`stripWrappers`, `hook.go:196-210`) and TrimLefts leading
whitespace (`stripLeadingAssignments`, `:183-191`) before the already-wrapped
check. The shell `NORM` loop (`shell-guard.sh:86-92`) strips only `rtk `/
`lean-ctx ` prefixes; the already-wrapped case (`:108-110`) tests raw `$CMD`.
Consequences on the fallback path:
- `FOO=1 rtk grep TODO cmd/agentic/main.go` → Go denies, shell **passes**
  (`hook_test.go:68` pins the Go deny).
- `FOO=bar grep TODO main.go` → Go denies, shell **passes**.
- `  rtk ls` → shell rewrites to `rtk  rtk ls` (double-wrap, violating the
  file's own line-15 no-double-wrap invariant).
- `  rtk grep -r foo main.go` (leading whitespace) → shell **allows + double
  wraps**, bypassing the deny this wave shipped.

**Fix.** Make the shell fallback mirror `stripWrappers`: extend the `NORM` loop
to also strip a leading `[A-Za-z_][A-Za-z0-9_]*=<word>` assignment token and
leading whitespace, and apply the same normalization to the already-wrapped
case (test the normalized string, not raw `$CMD`). One shared normalization
step feeding both the deny check and the already-wrapped check.

**AC5.** On the shell fallback path:
```
FOO=1 rtk grep TODO cmd/agentic/main.go   → deny (matches Go)
FOO=bar grep TODO main.go                 → deny (matches Go)
  rtk ls                                  → prints nothing (already-wrapped, no double wrap)
  rtk grep -r foo main.go                 → deny
```
Each must produce the identical verdict to the Go binary on the same input.
**AC6.** Add these four as `bin/ci-check.sh` fallback self-test cases.

---

## A3 — [BUG, high] `codeExtRe` matches a code extension mid-filename

**Evidence.** `hook.go:45` `codeExtRe` trailing `(\b|['"]|$)` matches inside a
longer name: `main.go.orig`, `main.go.txt`, `src/util.py.bak`, `config.php.dist`
all **deny** on both paths (the `\b` fires at the `.` after `.go`). These are
realistic backup/suffixed **text** files that must pass. Same pattern in the
shell at `shell-guard.sh:99`.

**Fix.** Require the extension to end the filename token. Replace the trailing
group with a set that ends the token but still catches shell metacharacters that
legitimately terminate a code path (so `grep foo main.go|head` and
`…main.go;…` still deny): use `([\s'"|;&)]|$)` in `codeExtRe` and the equivalent
`([[:space:]'"|;&)]|$)` in the shell pattern. Do **not** use `([\s'"]|$)` alone —
it would stop denying the unspaced-pipe form.

**AC7.** On both paths: `grep foo main.go.orig`, `grep TODO main.go.txt`,
`rg pat src/util.py.bak` → **pass** (rtk-wrapped, not denied); while
`grep foo main.go`, `grep foo main.go|head`, `grep foo main.go;ls` → still
**deny**. **AC8.** Regression cases for `main.go.orig` (pass) and
`main.go|head` (deny) in `hook_test.go` and one `ci-check.sh` case.

---

## A6 — [RISK, high] equals/assign guard vs lean-ctx delegate ordering diverges

**Evidence.** Go short-circuits assign/equals/already-wrapped *before* the
lean-ctx delegate (`hook.go:163` returns for those decisions; delegate at
`:172`). The shell runs the delegate first (`shell-guard.sh:115`), then its
assign (`:131`) and equals (`:139`) guards. So for a command lean-ctx would
rewrite, the two paths disagree: `git log --grep hi ===` → Go passes through,
shell emits a lean-ctx rewrite. Critically, that shell rewrite is itself broken:
`lean-ctx -c 'echo ==='` → `zsh:1: == not found` (exit 1) — the same
equals-expansion bug the prior wave fixed for `rtk`. Prior wave plan 02's spec
("the lean-ctx delegate is unaffected") is therefore unsafe for the equals case.

**Fix (default decision 2).** Align the shell to the Go order: move the assign
guard and the equals guard **above** the lean-ctx delegate in
`shell-guard.sh` (so an equals/assign command fails open before either wrapper
sees it). Add a one-line note to `issues/rtk-wrap-breaks-equals-words.md`
recording that the guard now also shields the lean-ctx delegate (the earlier
"rtk fallback only" framing was incomplete).

**AC9.** On both paths, with a real or stub `lean-ctx` that rewrites `git`:
`git log --grep hi ===` and `FOO=1 git status` → print nothing (fail open) on
both paths, identical verdict. **AC10.** `git status` (no equals, no assign) →
still rewritten identically on both paths (no over-broad fail-open).

---

## A7 — [RISK, low] a Go panic fails closed (blocks every Bash call)

**Evidence.** `shell-guard.sh:24` `exec`s `bin/agentic`, propagating its exit
code. An unrecovered Go panic exits 2; Claude Code treats hook exit 2 as a
**blocking** error (denies the tool call). No `recover()` exists anywhere
(`cmd/agentic/main.go:23`). This inverts the script's fail-open contract for the
one crash mode that matters.

**Fix.** Add `defer func(){ recover() }()` returning 0 in `hook.Main`
(`internal/hook/hook.go`), so any panic in the hook path fails open (exit 0)
rather than blocking. Keep it scoped to the hook dispatch — do not blanket the
whole binary.

**AC11.** A test that forces a panic inside the hook path (e.g. inject a
panicking `leanCtxRewrite` in a test) asserts the process/return is 0, not 2.

---

## A8 — [RISK, medium] failing `cd` in `__SG_ROOT` aborts the hook silently

**Evidence.** `shell-guard.sh:16` `set -euo pipefail`; `:22`
`__SG_ROOT="$(cd … && pwd)"`. If that `cd` fails (repo moved/deleted while a
hook is in flight), `set -e` aborts with no stdout/stderr/JSON — instead of
falling through to the shell fallback the `2>/dev/null` and the `${__SG_ROOT:-}`
guard at `:23` were written for.

**Fix.** Append `|| true` to the `__SG_ROOT` assignment (the pattern already
used at `:116` for the lean-ctx `OUT` assignment), so a failing `cd` degrades to
an empty `__SG_ROOT` and the fallback runs.

**AC12.** With `cd` forced to fail (broken `cd` function or in-flight `rm` of
the repo), the hook exits 0 with a normal fallback envelope, not a silent exit 1
— reproduce as in the audit (`repro` documented in `confirmed.json` finding
`shell-guard.sh:22`).

---

## A5 — [RISK, high] deny is trivially evaded by carriers / quoting (document)

**Evidence.** `command grep`, `\grep`, `/usr/bin/grep`, `env grep`,
`xargs grep`, `(grep …)`, `rg -t go`, `rg -g '*.go'`, `grep TODO "main.go"`,
`--include="*.go"`, `grep TODO main.\go` all evade `GrepTokenRe`
(`hook.go:55`, anchored at line-start/after-operator) or the quote-strip, on
**both** paths. The issue transcript shows models retry denied greps with new
shapes.

**Fix (default decision 1).** Document, do not expand. Add a "Known
limitations" section to `issues/shell-guard-astgrep-order-bypass.md` listing the
carrier/quoted-target/flag shapes as accepted gaps of a best-effort nudge (the
guard redirects the default reach, it is not a boundary), and a one-line code
comment near `GrepTokenRe` pointing at that section. **Do not** broaden the
regex — closing quoted-target re-introduces the BUG-03 tension (must still allow
a code-ext inside the *search pattern*). *Optional, only if the reviewer opts
in:* close the zero-FP carrier subset (`command `/`env ` prefix, leading `\`,
absolute path) — deferred by default.

**AC13.** The issue file has a "Known limitations" section enumerating the
shapes; `bin/ci-check.sh` and tests are unchanged for this item (documentation
only). No behavior change asserted.

---

## ci-check.sh mktemp cleanup — [DEBT] (folded here; this plan owns the file)

**Evidence.** `bin/ci-check.sh:124` `sg_stub="$(mktemp -d)"` is cleaned only by an
explicit `rm -rf` at `:171`, skipped on interrupt/early-exit. This plan already
edits `bin/ci-check.sh` for the new self-test cases, so it owns the fix.

**Fix.** Add `trap 'rm -rf "$sg_stub"' EXIT` right after the `mktemp -d`.
**AC14.** The trap is present; `bash bin/ci-check.sh` still exits 0.

---

## Plan-level acceptance

- `go test ./internal/hook/ -count=1`, `bash bin/ci-check.sh`,
  `golangci-lint run` all green.
- Go binary and shell fallback produce **identical verdicts** across the full
  AC matrix above (a small script piping each command through both paths and
  diffing is the proof artifact — capture its output).
- Diff touches only the six files named at the top.

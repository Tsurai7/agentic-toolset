# 01 — `agentic update` / `agentic version` subcommands

**Rationale:** [DESIGN.md](DESIGN.md) Q4 wedge 1. The `agentic-cfg` name already
reaches this binary via `agentic link` (main.go `linkCmd`), and `defaultRoot()`
already resolves the checkout from the binary path through symlinks — so the
subcommands are the only missing piece of `agentic-cfg update`.

## Change specification

### 1. `internal/selfupdate/selfupdate.go` (new package)

Follow the conventions of the sibling packages (`internal/gain`, `internal/hook`):
plain functions, `io.Writer` injection for output, no globals, stdlib only.

Exported surface (main.go passes the root it computed with its existing
`defaultRoot()`):

- `func Update(w io.Writer, root string) error` —
  1. Validate `root`: `filepath.Join(root, ".git")` exists and
     `filepath.Join(root, "bin", "install.sh")` exists; otherwise a clear error
     ("not an agentic-cfg checkout: …").
  2. Capture `before := describe(root)` (see below) and the short HEAD.
  3. Run `git -C root pull --ff-only`, streaming combined output to `w`. On a
     non-zero exit return an error that includes git's own output (a diverged
     branch or a conflicting dirty file must surface verbatim, not be rephrased).
  4. Run `bash bin/install.sh --provider all` with `Dir: root`, streaming to `w`
     (this rebuilds `bin/agentic` — the installer already does that; do not
     duplicate a build step).
  5. Capture `after := describe(root)`; print a final summary line:
     `agentic-cfg updated: <before> -> <after>` or, when the pull said already up
     to date, `agentic-cfg already up to date (<after>); config re-applied.` Then a
     one-line reminder that running Claude/Cursor sessions keep the prefix they
     started with; new sessions pick up the update.
- `func Version(w io.Writer, root string) error` — prints exactly two lines:
  `agentic-cfg <describe>  (commit <shortHead>, <committer date YYYY-MM-DD>)` and
  `root: <root>`. Errors if `root/.git` is missing.
- `describe(root string) string` (unexported): `git -C root describe --tags
  --always --dirty`; on git error fall back to the short HEAD; never panics.

Process execution: `os/exec`, always with explicit `-C root` or `Dir: root`; combine
stdout+stderr when streaming so the user sees git/installer output in order.

### 2. `cmd/agentic/main.go`

- `run()` switch: add `case "update"` and `case "version"` dispatching to small
  wrappers in main.go that follow the existing pattern (`flag.NewFlagSet`, a
  `--root` flag defaulting to `defaultRoot()`, return 0/1/2 like `statusCmd`).
- `usage()`: add the two lines in the existing alignment/style, e.g.
  `update [--root DIR]` — `pull latest (ff-only), rebuild, re-apply to all providers`;
  `version [--root DIR]` — `show checkout version (git describe) and repo root`.

### 3. `internal/selfupdate/selfupdate_test.go` (new)

Temp-git fixtures (`t.TempDir()`, real `git` — available in CI). Helper that builds
a fixture checkout: `git init` + config user.name/email + a `bin/install.sh` stub
(`#!/bin/bash`, records `"$@"` into `install-args.txt` in the repo root, prints
`STUB INSTALL`) made executable + a commit; where a remote is needed, `git clone
--bare` it as `origin` and wire `branch.<default>.remote/merge` (or clone from the
bare — whichever the implementer finds cleaner; do not assume the default branch is
named `master` — read it with `git symbolic-ref --short HEAD`).

Required cases:

1. `TestVersionTaggedAndUntagged` — untagged fixture: output contains the short
   hash; after `git tag v9.9.9`: output contains `v9.9.9`. Both contain `root:`.
2. `TestUpdateFastForwards` — origin gains one commit (make it via a second clone or
   by committing in the bare's worktree-free way from another clone); `Update` on
   the first clone succeeds, HEAD equals origin's new HEAD, `install-args.txt`
   contains `--provider all`, and the summary line contains `->`.
3. `TestUpdateAlreadyUpToDate` — no origin movement; `Update` succeeds, summary
   contains `already up to date`, stub installer still ran.
4. `TestUpdateRefusesDiverged` — local commit + different origin commit; `Update`
   returns an error whose text includes git's ff-only refusal, HEAD is unchanged,
   and the stub installer did NOT run (no `install-args.txt`).
5. `TestUpdateRejectsNonCheckout` — a plain temp dir (no .git): error mentions
   "not an agentic-cfg checkout".

### Constraints

- stdlib only; no new module deps (`go.mod` untouched).
- `gofumpt`/`goimports` clean; `golangci-lint run` clean — CI's strict lint gate
  (revive) rejects shadowed builtins and unused params; keep it tight.
- Do not touch `internal/lifecycle` (status stays as-is).

## Acceptance criteria (hard)

1. `go test ./... -count=1` passes including the five new tests;
   `go test ./internal/selfupdate -count=1 -v` output captured in the report.
2. `golangci-lint run` → 0 issues (run it explicitly — local ci-check does not).
3. `go build -o bin/agentic ./cmd/agentic` succeeds; `./bin/agentic version` on this
   real checkout prints a hash-or-describe line + `root: /Users/tsurai/Documents/GitHub/agentic-cfg`.
4. `./bin/agentic help` (usage) lists `update` and `version`.
5. Do NOT run `./bin/agentic update` on the real checkout — that is the verifier's
   E2E step after plan 02 lands (install.sh ordering); unit fixtures cover the logic.
6. Diff touches only: `internal/selfupdate/selfupdate.go`,
   `internal/selfupdate/selfupdate_test.go`, `cmd/agentic/main.go`.
7. `bash bin/prefix-budget.sh` → 8754 bytes unchanged.

# 03 — Install pipeline: Go internals

**Owner:** one implementer. **Files:** `internal/settings/settings.go` (+test),
`internal/mcpmerge/mcpmerge.go` (+test), `internal/claudemd/claudemd.go`
(+test), `internal/jsonorder/jsonorder.go` (+test), `internal/lifecycle/lifecycle.go`
(+test), `cmd/agentic/main.go`.

**Safety.** Never run inject/eject/merge against the real `$HOME`. Every live
repro uses `HOME=$(mktemp -d)` and a temp-built binary. A **stub `claude`** shim
first on `PATH` (logging its argv + `$HOME`) is required for the C5 repro so the
real CLI/config is never touched.

---

## C3 — [RISK, medium] any read error treated as "file absent" → silent clobber

**Evidence.** `settings.go:25` `if b, err := os.ReadFile(outPath); err == nil`
falls through to an empty map on **any** read error (incl. EACCES), then
overwrites via the temp+rename writer — dropping the user's data with exit 0.
Same pattern at `mcpmerge.go:271` and `claudemd.go:123`. `Unmerge`
(`settings.go:52-58`) correctly propagates non-ENOENT errors. Exposure is
broad: `agentic inject` has no settings backup, and the shell installer's
`backup_once` only protects the **first** install, so every repeat install (the
documented norm) reaches the merge.

**Fix.** Mirror `Unmerge` in all three read sites: return the read error unless
`os.IsNotExist(err)`. An unreadable existing config becomes a hard error that
leaves the file untouched, not a silent replace.

**AC1.** Repro: seed `settings.json = {"env":{"USER_DATA":"precious"}}`,
`chmod 000`, run `agentic merge-settings frag.json settings.json` → **exit
non-zero**, file **unchanged** (`USER_DATA` still present). Same for
`merge-mcp` and `merge-claude-md`. **AC2.** New unit test per package asserting
an unreadable existing file yields an error and no write. **AC3.** `os.IsNotExist`
path still works (absent file → clean create).

---

## C5 — [RISK, medium] `--home` sandbox still drives the real global `claude` CLI

**Evidence.** `lifecycle.go:208-214` (Eject) and `:159-165` (Inject) gate the
MCP step only on `SkipMCP`/`DryRun`, never on `o.Home`. `mcpmerge.go:501`
`exec`s `claude mcp remove <name> --scope user` with the inherited (real) env.
So `agentic eject --home <sandbox>` (without `--skip-mcp`) deregisters
`gitnexus`/`lean-ctx` from the **real** `~/.claude.json` while every file step
targets the sandbox. `README.md:32` documents no interaction; the flag help
(`main.go:113`) even admits the CLI is global.

**Fix.** In `injectEject` (`cmd/agentic/main.go:111-125`), auto-set `SkipMCP`
when `--home` is provided and differs from the real home
(`os.UserHomeDir()`), logging a clear "MCP step skipped: --home is a sandbox;
pass --with-mcp to override" line. (Adding an explicit `--with-mcp` opt-in is
optional; the safe default is to skip.) Note the interaction in `README.md:32`.

**AC4.** Repro with a logging `claude` stub first on PATH:
`agentic eject --home <sandbox>` (no `--skip-mcp`) → the stub log is **empty**
(no `mcp remove` invoked) and the command reports the skip. `--with-mcp` (if
implemented) or an explicit same-real-home run still drives the CLI.
**AC5.** New `lifecycle`/`main` test asserting `--home != realHome` implies the
MCP step is skipped.

---

## C6-go — [RISK, medium] atomic writers de-link a symlinked user config

**Evidence.** `jsonorder.go:224` `os.Rename(tmpName, path)` and
`claudemd.go:112` replace a **symlinked** config (dotfiles/stow pattern) with a
regular file — the merge reads through the link, the rename de-links it, leaving
the dotfiles-repo copy stale. Reproduced live: a symlinked
`settings.json`/`CLAUDE.md` becomes a regular file after `merge-settings` /
`merge-claude-md`, dotfiles target unchanged.

**Fix.** Resolve the destination with `filepath.EvalSymlinks` before creating
the temp file (create the temp in the *resolved* target's dir and rename onto
the resolved path), so the rename lands on the link target and the symlink
survives. Guard for the not-yet-existing case (EvalSymlinks errors on a missing
path → fall back to the literal path). The Python side (`safe_io.py`) is fixed
in plan 04.

**AC6.** Repro: `live/settings.json` → symlink to `dotfiles/x.json`; after
`agentic merge-settings frag live/settings.json`, `live/settings.json` is
**still a symlink**, and `dotfiles/x.json` now contains the merged content.
Same for `CLAUDE.md`. **AC7.** New test covering the symlinked-destination case.
**AC8.** Non-symlinked path unchanged (regression guard).

---

## GeneratedMD parity — [DEBT] Go inject vs shell install differ by 2 blank lines

**Evidence.** `lifecycle.go:76`/`:89` write `"\n\n## Principles…"` /
`"\n\n## User rules…"` after content already ending in `\n`, while
`install.sh:105-106/113-114` use `echo ""` (one newline). The two documented
entry points produce byte-different `agentic-cfg.generated.md`, so alternating
them rewrites the file every time. Each is individually idempotent.

**Fix.** Change the two `WriteString` calls in `GeneratedMD` to a single leading
`\n` (matching `echo ""`). Add a byte-parity assertion between `GeneratedMD`'s
output and the shell-written file to `internal/installtest`.

**AC9.** New installtest asserts the Go-injected and shell-installed
`agentic-cfg.generated.md` are **byte-identical** for the same repo.

---

## main.go usage line — [DOCS] `gain` help says "cost saved"

**Evidence.** `cmd/agentic/main.go:274` still describes `gain` as
"…cache hit rate, cost saved" and omits `--adoption`/`--by-model`/`--gate`. The
binary renamed that readout to "cache avoided" in the prior wave.

**Fix.** Update the usage string to the current phrasing and list the flags.
(Code-adjacent, kept here rather than in the docs bucket.)

**AC10.** `agentic` (no args) usage shows the `gain` line with "cache avoided"
and the `--adoption` flag.

---

## Plan-level acceptance

- `go test ./... -count=1`, `golangci-lint run` green.
- Each repro above captured before→after.
- Diff touches only the files named at the top.

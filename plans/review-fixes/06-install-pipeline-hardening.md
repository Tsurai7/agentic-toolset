# Plan 06 — install pipeline: atomicity, transactionality, weak tier, small fixes

[Index](00-INDEX.md) · Wave C · Files: `providers/claude/install.sh`,
`internal/lifecycle/lifecycle.go` (+test), `internal/jsonorder/jsonorder.go`
(+test), `providers/shared/merge-mcp.py`, `providers/shared/merge-settings.py`,
`internal/settings/` or fragment handling for weak tier, `bin/ci-check.sh`,
`bin/doctor.sh`. Runs AFTER plans 01 (install.sh build step) and 08 (merge-mcp
cursor changes) are merged into the working tree.

## Context (findings)

1. **MAJOR.** The one file every session imports,
   `~/.claude/agentic-cfg.generated.md`, is written non-atomically by BOTH
   writers: shell (`providers/claude/install.sh` ~line 95, truncating redirect
   `{ … } >"$generated"`) and Go (`internal/lifecycle/lifecycle.go` ~line 124,
   `os.WriteFile`). An interrupt leaves a truncated prefix silently degrading
   every future session — the exact BUG-12 class fixed everywhere else.
2. **MAJOR.** MCP registration is remove-then-add per server
   (`providers/shared/merge-mcp.py` ~149–161, `internal/mcpmerge/mcpmerge.go`
   ~319–322). If `add-json` fails, the server is left UNREGISTERED, and the
   Python path `return 1`s out of the loop, leaving every later server
   unregistered too.
3. **MAJOR.** `AGENTIC_TIER=weak` only *skips adding* lean-ctx
   (`providers/claude/install.sh` ~110–113). A previously registered lean-ctx
   server, its 12 `mcp__lean-ctx__*` allow entries, and its hook groups all
   survive — weak-tier sessions keep the full ctx_* payload the tier exists to shed.
4. **MINOR.** `sed "s#__AGENTIC_ROOT__#${AGENTIC_ROOT}#g"` (~lines 74, 127)
   breaks on paths containing `#` or `&`.
5. **MINOR.** `internal/jsonorder/jsonorder.go` `WriteFile` (~198–211) never
   fsyncs and leaves the renamed file at the temp file's 0600 mode — every
   merge silently chmods `~/.claude/settings.json` to 0600 (`safe_io.py` does
   fsync + the Python side preserves behavior; the docstring claims parity).
6. **MINOR.** `providers/shared/merge-settings.py` (~90) crashes with a raw
   `AttributeError` on `"hooks": null` in existing settings (Go tolerates it).
7. **MINOR.** `bin/ci-check.sh` (~98, ~123) discards go-test and swe-selftest
   output (`>/dev/null 2>&1`) — a red CI shows `FAIL` with zero diagnostics.
8. **MINOR.** `bin/doctor.sh`: (~22) symlink check concatenates a dir with an
   absolute readlink target (`/Users/x/.claude//Users/…`); (~50)
   `grep -q '"gitnexus"' ~/.claude.json` can match outside user-scope
   `mcpServers` (false OK); (~74) hardcoded `/opt/homebrew/bin/npx` fallback.

## Changes

1. **Atomic generated.md** — shell path: write to `"${generated}.tmp.$$"` then
   `mv -f` (keep the existing backup logic untouched); Go path: reuse the
   existing atomic-write helper (`internal/claudemd.atomicWrite` or
   `jsonorder.WriteFile` pattern) in `lifecycle.Inject`. Add/extend a lifecycle
   test that the target is either old or complete mid-failure (simulate by
   asserting tmp-then-rename is used — e.g. write hook or check no partial file
   on injected error, matching however claudemd tests do it).
2. **Transactional-ish MCP registration** — in BOTH implementations:
   capture the current server JSON (`claude mcp get <name>` or from the parsed
   target) BEFORE remove; on add failure, attempt re-add of the captured JSON
   (restore), record the failure, CONTINUE with remaining servers; exit nonzero
   at the end listing failed servers. install.sh already backs up target files —
   verify `~/.claude.json` is included in that backup; if not, back it up
   before the registration loop.
3. **Weak tier actually removes lean-ctx** — when `AGENTIC_TIER=weak`:
   a) if lean-ctx is registered, `claude mcp remove lean-ctx` (both impls);
   b) hooks: render the settings fragment WITHOUT the lean-ctx entries and let
   the managed-group merge (fixed in plan 03) replace/remove them;
   c) permissions: managed allow entries (`mcp__lean-ctx__*`) must be REMOVED
   when absent from the fragment — implement "managed allow set" semantics in
   both `merge-settings.py` and the Go settings package: entries matching
   `mcp__lean-ctx__*` are owned by the repo; on merge, drop owned entries not
   present in the incoming fragment; never touch user-added entries.
   Update the header comment in `providers/claude/install.sh` (~7–11) to match
   reality.
4. **sed escaping** — replace the sed substitution with a form safe for
   arbitrary paths: either escape `#`, `&`, `\` in `AGENTIC_ROOT` first, or use
   `python3 - "$src" "$AGENTIC_ROOT"` with `str.replace`. Keep behavior
   identical for normal paths.
5. **jsonorder.WriteFile** — fsync the temp file before rename (and fsync the
   dir if the existing helpers do); chmod the temp file to the target's prior
   mode (or 0644 default when the target didn't exist) before rename. Unit
   test: pre-existing 0644 file keeps 0644 after WriteFile.
6. **merge-settings.py null tolerance** — treat `"hooks": null` (and null
   `permissions`) as `{}` like the Go port; extend the merge-helpers self-test
   in `bin/ci-check.sh` with this fixture.
7. **ci-check output** — capture go-test/swe-selftest output to a temp var/file;
   print it ONLY on failure (keep success output as today's one-line OK).
8. **doctor.sh** — fix the three items in finding 8: resolve symlinks with
   `readlink` handling absolute targets (`case "$target" in /*) …`); check
   gitnexus registration via `claude mcp get gitnexus` (or jq on the
   `.mcpServers` key specifically) instead of a whole-file grep; drop the
   hardcoded npx fallback (the `command -v` check suffices).
9. **Go parity for plan 08's cursor sidecar** (added 2026-07-01 after plan 08
   landed): plan 08 implemented managed-server bookkeeping
   (`~/.cursor/.agentic-managed.json` — sidecar records repo-managed server
   names; servers in the sidecar but no longer in fragments are removed;
   first run bootstraps the sidecar without retro-claiming; user-added servers
   untouched; the `mcp.overlay.json` read was dropped and the file deleted) in
   `providers/shared/merge-mcp.py` ONLY. Since plan 01 makes every install
   build `bin/agentic`, the Go path (`internal/mcpmerge/mcpmerge.go`) shadows
   the Python one and lacks this logic. Port the sidecar behavior to the Go
   cursor/file-merge path 1:1 (read plan 08's python implementation as the
   spec), remove any Go-side read of the deleted `mcp.overlay.json`, and
   extend the existing Go↔Python parity test (`TestMcpParityWithPython`) to
   cover: sidecar bootstrap, stale-server removal, hand-added server survival.

## Acceptance criteria

1. `grep -n '>"$generated"' providers/claude/install.sh` → no truncating direct
   write; dry-run (`bash bin/install.sh --dry-run`) unchanged in what it prints.
2. `go test ./internal/lifecycle/ ./internal/jsonorder/ ./internal/settings/ ./internal/mcpmerge/ -count=1` — pass, including new tests: atomic inject, mode-preservation, managed-allow removal, weak-tier fragment merge.
3. Weak-tier proof (no live machine writes): using a temp HOME/config fixture
   (mirror how `internal/installtest` does it), run the merge with
   `AGENTIC_TIER=weak` against a settings.json that already contains lean-ctx
   hooks + the 12 allow entries + a registered lean-ctx server; show after:
   no lean-ctx hook groups, no `mcp__lean-ctx__*` allow entries, server
   removed; user-added allow entries and user hooks survive byte-identical.
4. Registration failure drill: simulate `add-json` failure for server A
   (e.g. point the loop at a stub `claude` script that fails once) — server A
   is restored or reported, servers B+ still processed, exit code nonzero,
   output names A. Show the transcript.
5. `python3 providers/shared/merge-settings.py` on a fixture with
   `"hooks": null` exits 0; `bash bin/ci-check.sh` merge-helpers section
   includes the new fixture and passes.
6. Break a Go test temporarily (locally, revert after) to show `bin/ci-check.sh`
   now prints the failing output; restore and show full green.
7. `AGENTIC_ROOT` containing `&` smoke: render the stub through the new
   substitution with a temp path like `/tmp/a&b/agentic-cfg` and show the token
   replaced literally.
8. `bash bin/doctor.sh` and `bash bin/doctor.sh --deep` run clean on this machine.
9. `golangci-lint run` clean; `git status` touches only header files.
10. Go↔Python cursor parity: `go test ./internal/mcpmerge/ -run TestMcpParity -count=1 -v`
    passes with the extended sidecar cases; a fake-HOME drill through
    `bin/agentic merge-mcp` (Go path) reproduces plan 08's AC 2 result
    (fragment removed → server removed; hand-added server survives; sidecar
    evolves) byte-identically with the Python path.

## Out of scope

Cursor-side merge/eject (plan 08). Live-machine application (plan 10).
`__PATH__` baking — deferred (see index).

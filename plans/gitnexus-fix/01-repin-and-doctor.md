# 01 — Re-pin gitnexus to a runtime-compatible version + doctor MCP start check

**Rationale:** [DESIGN.md](DESIGN.md) Q1/Q4 — `gitnexus@1.6.8` requires Node ≥22
(`engines` field), the machine baseline is Node 20.12.2, so the registered MCP server
has crashed on startup since the pin landed (2026-06-24) and `doctor.sh --deep` never
noticed because it only greps the pin string. Re-pin to 1.6.7 (verified to start and
complete an MCP `initialize` handshake on Node 20) and make doctor actually start the
server.

## Change specification

### 1. `integrations/gitnexus/mcp.stdio.json`

Replace `"gitnexus@1.6.8"` with `"gitnexus@1.6.7"` in `args`. Nothing else changes
(placeholders `__NPX__` / `__PATH__` / `__NODE_PATH__` stay).

### 2. `integrations/gitnexus/README.md`

Add a short "Version pin" section stating: pinned to `1.6.7` because releases
`1.6.8+` declare `engines.node >=22.0.0` and crash on this machine's Node 20.12.2
(`SyntaxError: The requested module 'commander' does not provide an export named
'Command'`); unpin path = upgrade machine Node to ≥22, bump the pin in
`mcp.stdio.json` **and** every doc that spells the version, re-run
`bin/install.sh`, then `bin/doctor.sh --deep`. Keep the existing sections.

### 3. `bin/mcp-start-check.py` (new, stdlib-only, executable not required)

A small helper that proves a stdio MCP server actually starts:

- Usage: `python3 bin/mcp-start-check.py <config.json> <server-name> [timeout-sec]`
  where `<config.json>` has the `mcpServers.<server-name>` shape used by
  `~/.claude.json` (`command`, `args`, optional `env` merged over `os.environ`).
- Behavior: spawn the command, write a JSON-RPC `initialize` request (protocolVersion
  `2024-11-05`) to stdin, read stdout lines until a response with `"id": 1` arrives
  or the deadline (default 30 s) passes, then kill the process.
- Success: response contains `result.serverInfo`; print
  `OK <name> <serverInfo.name> <serverInfo.version>` and exit 0.
- Failure: print the first ~3 lines of captured stderr (that is where the Node
  SyntaxError shows up) plus a one-line reason (`timeout` / `process exited rc=N` /
  `bad response`) and exit 1.
- No third-party imports; use `subprocess`, `json`, `threading` or `select`, `time`.

### 4. `bin/doctor.sh` — deep section

After the existing pin check inside `if [[ "$DEEP" -eq 1 ]]`, add an MCP runtime
check:

- If `${HOME}/.claude.json` exists and contains a `gitnexus` server (the earlier
  scoped-python check already computes this — do not duplicate its logic, a plain
  re-check is fine), run
  `python3 "${AGENTIC_ROOT}/bin/mcp-start-check.py" "${HOME}/.claude.json" gitnexus 30`.
- On success → `ok "gitnexus MCP server starts (…)"` including the version the
  helper printed; on failure → `fail` with the helper's reason and the hint
  `re-run bin/install.sh; see integrations/gitnexus/README.md (version pin)`.
- `fail`, not `warn`: a registered-but-dead server is precisely the silent outage
  this wave is fixing. Skip the check (single `warn`) when `~/.claude.json` has no
  gitnexus entry (the earlier section already `fail`s that case).

### 5. `SETUP.md`

Wherever it says `npx gitnexus analyze` (two places per current grep: the "GitNexus
needs no install" note and the indexing steps), use the pinned form
`npx -y gitnexus@1.6.7 analyze` and add one sentence: the version is pinned repo-wide
(see `integrations/gitnexus/README.md` for why and how to unpin); an unpinned `npx
gitnexus …` resolves `@latest`, which requires Node ≥22 and fails on Node 20.

### 6. `CHANGELOG.md`

One entry at the top in the file's existing style: re-pinned gitnexus 1.6.8 → 1.6.7
(1.6.8 requires Node ≥22; server was silently failing to start since 2026-06-24) and
added an MCP start/handshake check to `doctor.sh --deep`.

## Acceptance criteria (hard)

1. `grep -r 'gitnexus@' integrations/ SETUP.md bin/` shows only `gitnexus@1.6.7`
   (no `1.6.8`, no unpinned `gitnexus mcp`/`gitnexus analyze` invocations remain in
   those files).
2. `python3 bin/mcp-start-check.py /Users/tsurai/.claude.json gitnexus 30` exits 0
   and prints the server version **after** `bash bin/install.sh --provider all` has
   re-registered the server (run install first; the pre-existing registration is
   1.6.8 and must fail the check before reinstall — demonstrate both, failure then
   success, in the report).
3. `bash bin/doctor.sh --deep` passes, and its output contains the new
   `gitnexus MCP server starts` OK line.
4. `bash bin/ci-check.sh` passes; `bash bin/prefix-budget.sh` byte total unchanged.
5. Diff touches only: `integrations/gitnexus/mcp.stdio.json`,
   `integrations/gitnexus/README.md`, `bin/mcp-start-check.py`, `bin/doctor.sh`,
   `SETUP.md`, `CHANGELOG.md`.
6. `bin/mcp-start-check.py` imports stdlib only (verify: no `import` outside the
   standard library).

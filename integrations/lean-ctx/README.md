# lean-ctx integration

[lean-ctx](https://github.com/yvgude/lean-ctx) is a context-engineering layer:
`ctx_*` MCP tools (compressed reads, search, shell) plus hooks that redirect
native Read/Grep/Shell to the compressed equivalents.

Making it portable takes three pieces — all installed by `bin/install.sh --provider cursor`:

| Piece | Where | Notes |
|-------|-------|-------|
| The rule | `core/rules/lean-ctx.mdc` → `~/.cursor/rules/` | Tells the agent to prefer `ctx_*` tools |
| The MCP server | `integrations/lean-ctx/mcp.stdio.json` → merged into `mcp.json` | `ctx_*` tools live here |
| The hooks | `providers/cursor/hooks.json` → `~/.cursor/hooks.json` | `observe` / `rewrite` / `redirect` enforcement |

## Prerequisite: install the binary

The MCP server and hooks both call the `lean-ctx` binary, which is **not** vendored
here. Install it once per machine (Homebrew tap):

```bash
brew install yvgude/lean-ctx/lean-ctx
# if prompted about an untrusted tap:
brew trust yvgude/lean-ctx
```

## Configuration

Placeholders in `mcp.stdio.json` are filled from `secrets/.env` (or sensible
defaults) by `providers/shared/merge-mcp.py`:

| Placeholder | Default | Override in `secrets/.env` |
|-------------|---------|-----------------------------|
| `__LEAN_CTX__` | `/opt/homebrew/bin/lean-ctx` | `LEAN_CTX=` |
| `__LEAN_CTX_DATA_DIR__` | `~/.lean-ctx` | `LEAN_CTX_DATA_DIR=` |

## Claude

lean-ctx is wired for both Cursor and Claude Code:
- **Cursor:** Rule + MCP server + hooks (see above).
- **Claude Code:** MCP server registered via `~/.claude.json` (user scope, via the `claude` CLI) 
  plus hooks + permissions merged into `~/.claude/settings.json`.

## Context cost

The lean-ctx server injects a tool-mapping instruction block into every session. Use 
`AGENTIC_TIER=weak` at install time to install without lean-ctx (now truly removing it — 
the server, its allow entries in permissions, and the related hook all disappear).

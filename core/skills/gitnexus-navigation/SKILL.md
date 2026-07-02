---
name: gitnexus-navigation
description: >-
  Use GitNexus graph-RAG for structural code navigation and impact analysis in Go
  and .NET codebases. Use for refactors, interface changes, and dependency tracing
  instead of grep or full-file reads when GitNexus is available.
---

# GitNexus navigation

You are connected to **GitNexus** via MCP in Go / .NET codebases.

## Use GitNexus for

- Finding where a struct field or class property is used
- How one function interacts with dependencies (fetch function node + edges)
- Blast radius before changing an interface signature
- Implicit Go interface implementations and C# polymorphism

## Prefer GitNexus over

- Raw `grep` or text search for structural "who implements / who calls"
- Reading entire large files to understand one symbol
- Guessing which files break after a signature change

## If repo not indexed

```bash
npx -y gitnexus@1.6.7 analyze
```

Run from the repository root (or use MCP analyze tool if available).
`npx -y gitnexus@1.6.7 status` shows whether the current repo is indexed —
queries against a never-indexed repo return nothing useful, so check or index
first.

## Workflow

1. **Reference / impact** — Before editing an interface or shared type
2. **Query polymorphism** — Interface implementations, inheritance
3. **Fetch node** — Single function/class with immediate out-edges only

## When not GitNexus

- **Code matching a syntactic pattern** → `ast-grep`, not regex grep (see skill `ast-grep`)
- Exact string literals, log messages, config keys → `ctx_search` / `grep`
- Needle queries for a known file path or unique identifier

## CLI fallback (no MCP tools in session)

When `mcp__gitnexus__*` tools are not available, the same graph is queryable via CLI
(output is JSON on stdout):

- `npx -y gitnexus@1.6.7 context <SymbolName> --repo <repo-name>` — 360° view
  (callers, callees, flows); `--repo` is required once more than one repo is indexed.
- `npx -y gitnexus@1.6.7 query "<concept>" --repo <repo-name>` — execution flows.

## MCP

GitNexus is configured in `integrations/gitnexus/` and installed by
`bin/install.sh`: registered user-scope for Claude in `~/.claude.json` (via the
`claude` CLI) and merged into `~/.cursor/mcp.json` for Cursor. The version is
pinned (`gitnexus@1.6.7` — see `integrations/gitnexus/README.md` for why and the
unpin path).

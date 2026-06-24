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
npx gitnexus analyze
```

Run from the repository root (or use MCP analyze tool if available).

## Workflow

1. **Reference / impact** — Before editing an interface or shared type
2. **Query polymorphism** — Interface implementations, inheritance
3. **Fetch node** — Single function/class with immediate out-edges only

## When not GitNexus

- **Code matching a syntactic pattern** → `ast-grep`, not regex grep (see skill `ast-grep`)
- Exact string literals, log messages, config keys → `ctx_search` / `grep`
- Needle queries for a known file path or unique identifier

## MCP

GitNexus is configured in `integrations/gitnexus/` and synced to `~/.cursor/mcp.json` and `~/.claude/.mcp.json` via `bin/install.sh`.

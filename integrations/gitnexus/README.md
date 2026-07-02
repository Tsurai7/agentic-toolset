# GitNexus integration

[GitNexus](https://www.npmjs.com/package/gitnexus) provides graph-RAG MCP tools for structural code navigation in Go and .NET repos.

## Setup

1. Ensure `npx` is available (see `secrets/.env.example`).
2. Run `bin/install.sh` to merge into Cursor / Claude MCP configs.
3. Index a repo: `npx -y gitnexus@1.6.7 analyze` from the repository root.

## MCP definition

`mcp.stdio.json` is merged by `providers/shared/merge-mcp.py`. Placeholders `__NPX__`, `__PATH__`, `__NODE_PATH__` are replaced from `secrets/.env` during install.

## Version pin

Pinned to `1.6.7` because releases `1.6.8+` declare `engines.node >=22.0.0` and crash on this machine's Node 20.12.2 (`SyntaxError: The requested module 'commander' does not provide an export named 'Command'`). Unpin path: upgrade the machine's Node to ≥22, bump the pin in `mcp.stdio.json` **and** every doc that spells the version, re-run `bin/install.sh`, then `bin/doctor.sh --deep`.

## Skill

See `core/skills/gitnexus-navigation/SKILL.md` for when to use graph tools vs grep.

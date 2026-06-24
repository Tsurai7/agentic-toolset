# GitNexus integration

[GitNexus](https://www.npmjs.com/package/gitnexus) provides graph-RAG MCP tools for structural code navigation in Go and .NET repos.

## Setup

1. Ensure `npx` is available (see `secrets/.env.example`).
2. Run `bin/install.sh` to merge into Cursor / Claude MCP configs.
3. Index a repo: `npx gitnexus analyze` from the repository root.

## MCP definition

`mcp.stdio.json` is merged by `providers/shared/merge-mcp.py`. Placeholders `__NPX__`, `__PATH__`, `__NODE_PATH__` are replaced from `secrets/.env` during install.

## Skill

See `core/skills/gitnexus-navigation/SKILL.md` for when to use graph tools vs grep.

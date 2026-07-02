# GitNexus integration

[GitNexus](https://www.npmjs.com/package/gitnexus) provides graph-RAG MCP tools for structural code navigation in Go and .NET repos.

## Setup

1. Ensure `npx` is available (see `secrets/.env.example`).
2. Run `bin/install.sh` to merge into Cursor / Claude MCP configs.
3. Index a repo: `npx -y gitnexus@1.6.8 analyze --skip-agents-md --skip-skills`
   from the repository root. Plain `analyze` (no flags) additionally writes a
   `<!-- gitnexus:start -->` section into root `AGENTS.md`/`CLAUDE.md` and
   generates six skill files under `.claude/skills/gitnexus/`; the skip flags
   suppress both, since this repo's `gitnexus-navigation` skill is the single
   source of truth and the auto-injected section costs ~700 tokens/session with
   MUST-directives that conflict with the tool-precedence gate. `.gitnexusrc`
   (as of 1.6.8) cannot persist these flags — pass them on every `analyze`. If a
   repo was already analyzed without the flags, delete the generated artifacts
   (identifiable by the `<!-- gitnexus:start -->` markers and the
   `.claude/skills/gitnexus/` directory).

## MCP definition

`mcp.stdio.json` is merged by `providers/shared/merge-mcp.py`. Placeholders `__NPX__`, `__PATH__`, `__NODE_PATH__` are replaced from `secrets/.env` during install.

## Version pin

Pinned to the latest stable release, `1.6.8`. It declares `engines.node >=22.0.0`,
satisfied by Homebrew Node (`brew install node`, currently v26 — resolves ahead of
any older system Node on PATH). Bump procedure: update the pin in `mcp.stdio.json`,
`SETUP.md`, and the `gitnexus-navigation` skill, re-run `bin/install.sh`, then
`bin/doctor.sh --deep`. Watch for a corrupt npx cache as a separate failure mode
(a stale `~/.npm/_npx/<hash>` dir can resolve `commander` without its named
exports even on a Node version that satisfies `engines`) — the doctor start
check's stderr names the offending path; remedy is `rm -rf` on that directory.

## Skill

See `core/skills/gitnexus-navigation/SKILL.md` for when to use graph tools vs grep.

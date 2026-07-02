# 03 — gitnexus-navigation skill: truth pass (MCP claim, pinned CLI fallback, index gate)

**Rationale:** [DESIGN.md](DESIGN.md) Q4 wedge 4. The skill's final "MCP" section
claims the config is "synced to `~/.cursor/mcp.json` and `~/.claude/.mcp.json`" —
the Claude half is wrong (Claude Code reads user-scope servers from `~/.claude.json`;
`bin/doctor.sh` documents this as PORT-03). And the A/B test (DESIGN.md Q3) showed
the winning agent worked through the **CLI**, which the skill never mentions — that
fallback is what keeps the skill actionable when MCP tools are absent from a session.

## Change specification

Edit `core/skills/gitnexus-navigation/SKILL.md` only. Keep the frontmatter
`description` **byte-identical** (it is the auto-discovery trigger; the eval
`structural-impact-gitnexus` depends on the skill's behavior, not on these edits —
`python3 evals/lint.py` must stay green). Keep the file ≤75 lines.

1. **Fix the MCP section:** configured in `integrations/gitnexus/`, installed by
   `bin/install.sh` — registered user-scope for Claude in `~/.claude.json` (via the
   `claude` CLI) and merged into `~/.cursor/mcp.json` for Cursor. Version is pinned
   (`gitnexus@1.6.7` — see `integrations/gitnexus/README.md` for why and the unpin
   path).
2. **Index gate (edit the "If repo not indexed" section):** the pinned command form
   `npx -y gitnexus@1.6.7 analyze` (run from the repo root); add that
   `npx -y gitnexus@1.6.7 status` shows whether the current repo is indexed, and
   that queries against a never-indexed repo return nothing useful — index first.
3. **New short section "CLI fallback (no MCP tools in session)":** when
   `mcp__gitnexus__*` tools are not available, the same graph is queryable via CLI:
   - `npx -y gitnexus@1.6.7 context <SymbolName> --repo <repo-name>` — 360° view
     (callers, callees, flows); `--repo` is required once more than one repo is
     indexed.
   - `npx -y gitnexus@1.6.7 query "<concept>" --repo <repo-name>` — execution flows.
   Note output is JSON on stdout.

## Acceptance criteria (hard)

1. `core/skills/gitnexus-navigation/SKILL.md`: frontmatter `description` block is
   byte-identical to before; file ≤75 lines; the string `~/.claude/.mcp.json` no
   longer appears; `~/.claude.json` and `gitnexus@1.6.7` do appear.
2. The literal command lines `npx -y gitnexus@1.6.7 context` and
   `npx -y gitnexus@1.6.7 query` appear in a CLI-fallback section.
3. `python3 evals/lint.py` passes with the same covered-skills count as before this
   plan.
4. `bash bin/ci-check.sh` passes; `bash bin/prefix-budget.sh` byte total unchanged
   (skills are not in the always-on prefix — the check is a guard against touching
   the wrong file).
5. Diff touches only `core/skills/gitnexus-navigation/SKILL.md`.
6. Every factual claim added is verifiable in-repo (`integrations/gitnexus/`,
   `bin/doctor.sh` PORT-03 comment) — no invented paths or flags: verify `--repo`,
   `status`, `context`, `query` against
   `node /Users/tsurai/.npm/_npx/5e786f48223a616c/node_modules/gitnexus/dist/cli/index.js --help`
   output before writing them.

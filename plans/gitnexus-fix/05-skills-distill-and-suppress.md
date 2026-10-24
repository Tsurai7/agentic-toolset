# 05 — Distill upstream skills into gitnexus-navigation; suppress per-repo auto-injection

**Rationale:** plain `gitnexus analyze` (1.6.8) injects three things into every analyzed
repo by default: six generic skills under `.claude/skills/gitnexus/` (~610 lines),
and a `<!-- gitnexus:start -->` section into root `AGENTS.md` **and** `CLAUDE.md`
(~2.9 KB ≈ 700 tokens auto-loaded into every session in that repo). The section's
directives conflict with this config ("MUST run impact analysis before editing any
symbol" / "MUST run detect_changes before committing" vs. the right-size-the-tooling
gate), and the skills duplicate the MCP schemas and our `gitnexus-navigation`.
Upstream regenerates all of it on each `analyze`, so vendoring would create a second
source of truth. Verified: both `--skip-skills` and `--skip-agents-md` flags exist;
`.gitnexusrc` (as of 1.6.8) persists only `default-branch`, not skip options.
Decision (operator-approved): our skill stays the single source of truth; take the
genuinely-new tool guidance from upstream's text; document the suppression flags as
the canonical invocation. The A/B win (DESIGN.md Q3) was achieved *without* the
upstream skills — but its winning agent also never touched `impact`/`detect_changes`,
the strongest graph tools; that is the gap this distillation closes.

## Change specification

### 1. `core/skills/gitnexus-navigation/SKILL.md`

Read the six generated skills first for source material (main tree:
`/Users/tsurai/Documents/GitHub/agentic-cfg/.claude/skills/gitnexus/*/SKILL.md` —
NOT part of this worktree; read-only reference). Then edit our skill:

- **Frontmatter `description`** (this is the auto-trigger — the ONE intentional
  frontmatter change of this plan): keep the current two sentences, extend with
  upstream's concrete trigger phrasings so impact-style questions fire it, e.g.
  covering "is it safe to change X / what will break / what depends on this".
  Keep it ≤4 lines of YAML text.
- **Add a "High-value graph tools" section** (compact, ~10 lines) covering, with
  one line each: `impact` (blast radius with risk level, `direction: "upstream"` for
  who-depends-on-this — run before signature changes), `detect_changes` (maps
  uncommitted git diff to affected symbols/flows — useful before large commits),
  `rename` (graph-coordinated multi-file rename), `cypher` (raw graph queries when
  canned tools don't fit). Frame as judgment calls per the right-size gate — explicitly
  NOT "always run before any edit".
- **Add one line** to the existing workflow/MCP part: per-repo auto-injection
  (AGENTS.md/CLAUDE.md section + `.claude/skills/gitnexus/`) is suppressed in this
  config — index with the canonical command below; this skill is the single source
  of truth.
- **Update every `analyze` invocation** in the file to the canonical form:
  `npx -y gitnexus@1.6.8 analyze --skip-agents-md --skip-skills`.
- File stays **≤80 lines** (was ≤75; +5 granted for the new section — condense
  elsewhere if needed; do not cut the CLI-fallback or index-gate content from plan 03/04).

### 2. `SETUP.md`

Both `analyze` commands get the two skip flags, plus ONE added sentence explaining
why (single source of truth; upstream section costs ~700 tokens/session and its
MUST-directives conflict with the tool-precedence gate).

### 3. `integrations/gitnexus/README.md`

In the Setup steps, make step 3 the canonical flagged command; add a short
"Auto-injection" note: what plain `analyze` writes (the three surfaces), why we
suppress, that `.gitnexusrc` cannot persist these flags as of 1.6.8 (checked), and
that generated artifacts in an already-analyzed repo should be deleted (the
`<!-- gitnexus:start -->` markers make them identifiable).

### 4. `CHANGELOG.md`

New `[0.15.1]` entry above `[0.15.0]`, existing style: distilled upstream GitNexus
skill guidance (impact/detect_changes/rename/cypher) into `gitnexus-navigation`;
canonical analyze invocation now suppresses per-repo skill/AGENTS.md injection.

## Acceptance criteria (hard)

1. `core/skills/gitnexus-navigation/SKILL.md` ≤80 lines; contains `impact`,
   `detect_changes`, `rename`, `cypher`, and `--skip-agents-md --skip-skills`;
   frontmatter description mentions safe-to-change/what-breaks phrasing.
2. Every `analyze` invocation in SKILL.md, SETUP.md, and
   `integrations/gitnexus/README.md` carries both skip flags
   (`grep -n 'analyze' <files>` shows no unflagged invocation; the README "why"
   note may mention plain `analyze` in prose, not as a command line).
3. `python3 evals/lint.py` → still `22 cases, 10 skills covered.`
4. `bash bin/ci-check.sh` passes; `bash bin/prefix-budget.sh` → 8754 bytes unchanged.
5. Diff touches only: `core/skills/gitnexus-navigation/SKILL.md`, `SETUP.md`,
   `integrations/gitnexus/README.md`, `CHANGELOG.md` (plus this plan file and the
   INDEX row, committed by the orchestrator).
6. Every tool name/flag written into the skill is verified against the real CLI/MCP
   surface (`npx -y gitnexus@1.6.8 --help`, the MCP tools list in DESIGN.md Q6, or
   the generated skills' own text) — no invented parameters.

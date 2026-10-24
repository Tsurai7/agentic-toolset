# Plan 01 — Isolated full-config render + arms axis + duration

Part of [`00-INDEX.md`](00-INDEX.md). Work in THIS worktree
(`/Users/tsurai/Documents/GitHub/agentic-cfg-bench`), branch `feat/benchmarks-impact`.

**File scope (touch nothing else):**
- `evals/lib/render_config.py`
- `evals/swe_bench.py`
- `evals/selftest.py` (only if it asserts render_config/swe_bench behavior that your
  change extends — add, don't rewrite)

Do NOT commit. Do NOT run any command that spends API tokens (no `claude -p`
invocations; `--selftest` paths must stay zero-token). NEVER touch the real
`~/.claude` — everything renders into temp/test dirs.

## Change 1 — `render_full_variant()` in `evals/lib/render_config.py`

New function:

```python
def render_full_variant(dest: Path, exclude: frozenset[str] = frozenset()) -> dict:
    """Render TODAY'S complete config into an isolated CLAUDE_CONFIG_DIR, minus the
    named exclusions. Returns {"config_dir": str, "mcp_config": str|None} — the
    caller passes config_dir via CLAUDE_CONFIG_DIR and mcp_config via
    `claude --mcp-config` (see change 2). Valid exclude tokens: "lean-ctx",
    "gitnexus", "shell-guard". Unknown tokens -> ValueError (fail loud, not open).
    """
```

Behavior (mirror `providers/claude/install.sh` semantics, but into `dest`, never
symlinking to or reading the live `~/.claude` except `.credentials.json` reuse):

1. **CLAUDE.md** — the full generated prefix content written DIRECTLY as
   `dest/CLAUDE.md` (no `@import`): stub (`providers/claude/CLAUDE.md.stub`, with
   `__AGENTIC_ROOT__` replaced by THIS worktree's repo root) + `core/instructions/
   AGENTS.md` + `\n\n## Principles (always-on)\n` + each `core/principles/*.md`
   (skip `README.md`) + `\n\n## User rules\n` + each `core/instructions/user-rules/
   *.md` (skip `cursor-rules-pointer.md`, add `### <basename>` headers) — byte-for-
   byte the same assembly order as `install.sh:install_claude_md`.
2. **settings.json** — `providers/claude/settings.hooks.json` with `__AGENTIC_ROOT__`
   resolved to this repo root; if `"shell-guard"` in exclude → drop the hook group
   whose matcher is `^Bash$`; if `"lean-ctx"` in exclude → drop the group whose
   command contains `lean-ctx hook redirect` AND every `permissions.allow` entry
   starting `mcp__lean-ctx__`.
3. **skills** and **agents** — symlink `dest/skills -> <repo>/core/skills` and
   `dest/agents -> <repo>/core/agents` (same as the installer).
4. **credentials** — reuse the existing `_write_credentials`/Keychain path exactly as
   `render_bare_control` does.
5. **MCP** — build a `claude --mcp-config`-compatible JSON (`{"mcpServers": {...}}`)
   from the repo's MCP fragments (`integrations/lean-ctx/mcp*.json`,
   `integrations/gitnexus/mcp*.json` — discover the actual fragment paths the same
   way `providers/shared/merge-mcp.py:collect_fragments()` does; reuse/import that
   helper rather than re-implementing if feasible), minus excluded servers. Resolve
   any `__AGENTIC_ROOT__`/`__PATH__`-style placeholders the fragments carry the same
   way the merge tool does. Write to `dest/mcp-config.json`; return its path. If
   every server is excluded, return `None` for `mcp_config`.

Note on fidelity: the isolated arm intentionally differs from the live machine in
exactly one way — MCP servers come via `--mcp-config` instead of `~/.claude.json`
user scope. State this in the function docstring.

## Change 2 — `--arms` axis in `evals/swe_bench.py`

- New flag `--arms bare,full,no-leanctx,no-gitnexus,no-shellguard` (comma list;
  default UNSET → legacy two-arm behavior unchanged, byte-identical output paths).
- Arm construction map: `bare` → `render_bare_control`; `full` →
  `render_full_variant(exclude=∅)`; `no-leanctx` → `exclude={"lean-ctx"}`;
  `no-gitnexus` → `exclude={"gitnexus"}`; `no-shellguard` → `exclude={"shell-guard"}`.
  Each arm's env = `{"CLAUDE_CONFIG_DIR": <dir>}`; when the arm has an
  `mcp_config`, append `--mcp-config <path>` (plus the strictness flag if the
  installed `claude --help` shows one — check `claude -p --help` output text at
  runtime once and cache; if no such flag exists, document that ambient user-scope
  servers may ALSO load and how you verified whether they do — see AC 6).
- In arms mode each cell record is per `(model, task, arm)` with **absolute**
  medians (no on/off ratio baked in): extend the median keys with `duration_ms`.
  Keep per-rep raw dumps and errored-rep exclusion exactly as the existing
  `measure_cell` does (reuse it — parametrize rather than fork).
- `--out` JSONL: arms-mode records carry `"arm": <name>` and `"schema": "arms-v1"`.
- Human output: per (model, task) print a small table of arms × {duration_s,
  repriced_tokens, tool_calls, turns, cost, correct} with per-rep spread for the
  ratio-critical fields.

## Change 3 — selftest coverage (zero-token)

Extend `swe_bench.py --selftest` (and `evals/selftest.py` if that's where render
assertions live) with:

1. `render_full_variant(tmp)` → `CLAUDE.md` non-empty and contains both the stub
   marker text and "## Principles (always-on)"; `settings.json` parses and contains
   the `^Bash$` group; `skills`/`agents` symlinks point into this repo; mcp-config
   JSON parses and names both `lean-ctx` and `gitnexus`.
2. `exclude={"shell-guard"}` → no `^Bash$` group, other groups intact.
   `exclude={"lean-ctx"}` → no redirect group, no `mcp__lean-ctx__*` allows, mcp
   config lacks lean-ctx but keeps gitnexus. `exclude={"gitnexus"}` → mirror image.
3. Unknown exclude token raises.
4. Arms-mode argv construction: `--mcp-config` present exactly when the arm has one;
   `duration_ms` included in the arms-mode median keys.
5. Legacy mode regression: with `--arms` unset, the argv/median keys are unchanged
   (assert against the current values, not re-derived constants).

## Acceptance criteria

1. `python3 evals/swe_bench.py --selftest` exits 0 with the new assertions listed in
   its output (show the section).
2. `python3 evals/selftest.py` and `python3 evals/lint.py` exit 0.
3. `bash bin/ci-check.sh` exits 0 in this worktree.
4. Zero-token proof: your whole session ran no `claude -p` (state it; the verifier
   will scan your transcript's Bash calls).
5. `git status --porcelain` in this worktree shows only the three in-scope files.
6. The `--mcp-config` strictness question is ANSWERED in your report (which flag
   exists in the installed CLI's help text, and what you implemented); do not guess.
   You may run `claude --help` / `claude -p --help` (no API cost) to check.
7. Every new function has a docstring stating the ambient-vs-isolated fidelity note
   (change 1) and the fail-loud exclude contract.

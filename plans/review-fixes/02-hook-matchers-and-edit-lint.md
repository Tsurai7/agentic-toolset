# Plan 02 — anchor hook matchers; fix edit-lint side effects

[Index](00-INDEX.md) · Wave B · Files: `providers/claude/settings.hooks.json`,
`providers/claude/hooks/edit-lint.sh`, `providers/claude/hooks/edit-lint.test.sh`.

## Context (findings)

1. **CRITICAL.** Claude Code hook matchers are regexes tested against the tool
   name, and the repo fragment `providers/claude/settings.hooks.json` uses
   unanchored alternations. The `lean-ctx hook redirect` entry (matcher
   `Read|read|ReadFile|read_file|View|view|Grep|grep|Search|search|ListFiles|list_files|ListDirectory|list_directory`)
   substring-matches unrelated tools: `WebSearch`/`ToolSearch` (contain
   `Search`), `mcp__Claude_Preview__preview_click` (contains `view`),
   `mcp__*__read_file_content` (contains `read_file`), `read_clipboard`
   (contains `read`). Verified: `lean-ctx hook redirect` emits
   `{"permissionDecision":"allow"}` for EVERY input — so matched
   action-capable tools get silently auto-approved (permission bypass).
2. **MAJOR, reproduced.** `edit-lint.sh` (~line 41) uses
   `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$FILE"` — the env var does
   NOT stop explicit `py_compile`; a `__pycache__/*.pyc` is created in the
   user's repo on every Python edit, dirtying `git status`.
3. **MINOR.** `edit-lint.test.sh` (~line 18) feeds `file_path` at the top level
   of the JSON payload, but real PostToolUse payloads nest it under
   `tool_input` — the fixture doesn't test the real shape.

## Changes

### 1. Anchor every matcher in `providers/claude/settings.hooks.json`

This fragment targets Claude Code only (it merges into `~/.claude/settings.json`),
so lowercase/Cursor-style aliases are dead weight. Replace:

- `"Bash|bash"` → `"^Bash$"`
- the redirect matcher → `"^(Read|Grep|Glob)$"`
- `"Edit|Write|MultiEdit"` → `"^(Edit|Write|MultiEdit)$"`
- Leave the `.*` matchers on PostToolUse/PreCompact/SessionStart/SessionEnd/
  Stop/UserPromptSubmit `lean-ctx hook observe` entries as-is (observe is
  verified silent; `.*` is intentional there).

Rationale note to add as a one-line comment is NOT possible in JSON — instead
record the rationale in the plan's report. The redirect hook force-allows
whatever it matches, so its matcher must list read-only tools ONLY.

### 2. Replace `py_compile` with `ast.parse` in `edit-lint.sh`

- Use: `python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' "$FILE"`
  (stderr → same error-reporting path as today; keep the 3-line output cap).
- Remove the now-false comment claiming `PYTHONDONTWRITEBYTECODE` prevents bytecode.

### 3. Fix the test fixture payload shape

- In `edit-lint.test.sh`, nest `file_path` under `tool_input`
  (`{"tool_name":"Edit","tool_input":{"file_path":"..."}}`) to mirror real
  PostToolUse payloads. If `edit-lint.sh` currently reads only the top-level
  field, fix it to read `tool_input.file_path` (with the old top-level location
  as fallback) — check how the Go binary path parses it and stay consistent.

## Acceptance criteria

1. `jq -r '.hooks.PreToolUse[].matcher, .hooks.PostToolUse[].matcher' providers/claude/settings.hooks.json`
   shows only `^Bash$`, `^(Read|Grep|Glob)$`, `.*`, `^(Edit|Write|MultiEdit)$`.
2. `python3 - <<'EOF'` probe: for each of `WebSearch`, `ToolSearch`,
   `preview_click`, `read_clipboard`, `NotebookRead`, assert none matches any
   non-`.*` matcher regex from the fragment (`re.search`). Include the probe
   output in your report.
3. After an edit-lint run over a temp `.py` file in a temp dir:
   `find <tempdir> -name '__pycache__' -o -name '*.pyc'` returns nothing, and a
   deliberately broken `.py` edit still produces the lint warning (exit
   semantics unchanged). Broken `.go`/`.js`/`.sh` fixtures still flagged:
   `bash providers/claude/hooks/edit-lint.test.sh` exits 0.
4. `bash bin/ci-check.sh` exits 0 (its edit-lint self-test section still OK).
5. `shellcheck -S warning providers/claude/hooks/edit-lint.sh providers/claude/hooks/edit-lint.test.sh` — clean.
6. `git status` touches only the three files named in the header.

## Out of scope

The live `~/.claude/settings.json` still contains the OLD matchers after this
plan — plan 10 re-runs the installer to propagate. The `lean-ctx` binary's
always-allow behavior itself is external (not fixable here); anchoring confines it.

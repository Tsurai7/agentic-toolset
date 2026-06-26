#!/usr/bin/env bash
# Repo-owned PostToolUse hook for Edit|Write|MultiEdit. After an edit lands, it runs a
# fast syntax/parse check on the touched file and, ONLY on a clear parse failure,
# injects a short note so the agent fixes the breakage before moving on. This prevents
# the broken-edit -> failed-run -> re-edit round-trips that cost weak models the most
# (plans/06-overhead-and-uplift.md, W4). It adds nothing to the always-on prefix.
#
# Bulletproof fail-open: a non-edit tool, a missing/empty file_path, an unknown
# extension, an absent checker, or a passing check all exit silently with no output. It
# never blocks an edit (PostToolUse runs after the write) — at most it adds context.
# Deliberately NOT `set -e`: a non-zero checker must not abort before we emit the note.
set -uo pipefail

INPUT=$(cat)

extract() {
  # First "key": "value" string, unescaping \" and \\ ; missing key -> empty.
  printf '%s' "$INPUT" \
    | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" \
    | head -1 \
    | sed "s/^\"$1\"[[:space:]]*:[[:space:]]*\"//;s/\"$//;s/\\\\\"/\"/g;s/\\\\\\\\/\\\\/g" \
    || true
}

TOOL=$(extract tool_name)
case "$TOOL" in
  Edit|Write|MultiEdit) ;;
  *) exit 0 ;;
esac

FILE=$(extract file_path)
[ -n "$FILE" ] && [ -f "$FILE" ] || exit 0

# Claude Code passes an absolute file_path, so a leading-dash-as-flag is not a real
# concern; `--` guards the checkers that accept it as belt-and-suspenders (py_compile
# does not accept `--`, but the absolute-path invariant covers it).
err=""
case "$FILE" in
  *.py)
    command -v python3 >/dev/null 2>&1 || exit 0
    err=$(PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile "$FILE" 2>&1) || true
    ;;
  *.go)
    command -v gofmt >/dev/null 2>&1 || exit 0
    err=$(gofmt -e -- "$FILE" 2>&1 >/dev/null) || true
    ;;
  *.js | *.jsx | *.cjs | *.mjs)
    command -v node >/dev/null 2>&1 || exit 0
    err=$(node --check -- "$FILE" 2>&1) || true
    ;;
  *)
    exit 0
    ;;
esac

[ -z "$err" ] && exit 0

# A parse error was found — inject a concise note (PostToolUse cannot block the edit).
# Strip the whole C0 control range: JSON forbids unescaped U+0000–U+001F, and a broken
# source line echoed by the checker can contain more than just newlines/tabs.
MSG="Syntax check failed for ${FILE} after this edit: $(printf '%s' "$err" | head -3 | tr '\000-\037' ' '). Fix it before continuing."
JSON_MSG=$(printf '%s' "$MSG" | sed 's/\\/\\\\/g;s/"/\\"/g')
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}' "$JSON_MSG"

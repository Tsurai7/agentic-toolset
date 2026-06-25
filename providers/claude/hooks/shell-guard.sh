#!/usr/bin/env bash
# Repo-owned PreToolUse Bash hook. Enforces the shell + code-search precedence
# rules mechanically, so they no longer depend on model discipline alone:
#
#   1. ast-grep guard — deny a `grep`/`rg`/`egrep`/`fgrep` invocation that
#      explicitly targets source files (by code-file extension), pointing the
#      agent at `sg` instead. Plain-text/log greps pass through untouched.
#   2. lean-ctx delegate — hand the command to `lean-ctx hook rewrite`. If
#      lean-ctx decides to wrap it (e.g. `git …` -> `lean-ctx -c "git …"`),
#      honor that verbatim.
#   3. rtk fallback — for anything lean-ctx leaves bare (e.g. `python3 …`),
#      prefix `rtk` so no native command escapes token compression.
#
# Exactly one of these fires per command, so there is no double-wrapping.
set -euo pipefail

INPUT=$(cat)

extract() {
  # $1 = JSON key. Pulls the first "key": "value" string, tolerating optional
  # whitespace around the colon, and unescaping \" and \\. A missing key yields
  # an empty string rather than failing the pipeline (which set -e would abort).
  printf '%s' "$INPUT" \
    | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" \
    | head -1 \
    | sed "s/^\"$1\"[[:space:]]*:[[:space:]]*\"//;s/\"$//;s/\\\\\"/\"/g;s/\\\\\\\\/\\\\/g" \
    || true
}

TOOL=$(extract tool_name)
case "$TOOL" in
  Bash|bash|PowerShell|powershell) ;;
  *) exit 0 ;;
esac

CMD=$(extract command)
[ -z "$CMD" ] && exit 0

# Already wrapped — never double-wrap.
case "$CMD" in
  lean-ctx\ *|rtk\ *) exit 0 ;;
esac

# Heredoc / here-string — the body cannot be safely re-quoted inside
# `lean-ctx -c '…'` or after an `rtk` prefix, so run the command untouched.
case "$CMD" in
  *'<<'*) exit 0 ;;
esac

# --- 1. ast-grep guard -------------------------------------------------------
# Deny only when grep/rg clearly targets code (a code-file extension appears as
# a glob, an --include, or a path arg). Text/log greps fall through.
CODE_EXT='go|cs|py|js|jsx|ts|tsx|java|kt|rb|rs|c|h|cc|cpp|hpp|php|swift|scala|sql|vue'
if printf '%s' "$CMD" | grep -qE '(^|[|&;]| )(grep|egrep|fgrep|rg)( |$)' \
   && printf '%s' "$CMD" | grep -qE "\.($CODE_EXT)(\b|['\"]|$)"; then
  REASON="Use ast-grep for structural code search: sg -p '<pattern>' -l <lang>. Plain grep is only for non-code text/logs (see the ast-grep + tool-precedence rules)."
  JSON_REASON=$(printf '%s' "$REASON" | sed 's/\\/\\\\/g;s/"/\\"/g')
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$JSON_REASON"
  exit 0
fi

# --- 2. lean-ctx delegate ----------------------------------------------------
# lean-ctx emits an "allow" envelope even when it does NOT rewrite, so honor its
# output only when it actually rewrote the command (an updatedInput is present).
if command -v lean-ctx >/dev/null 2>&1; then
  OUT=$(printf '%s' "$INPUT" | lean-ctx hook rewrite 2>/dev/null || true)
  if printf '%s' "$OUT" | grep -q '"updated[_]*[Ii]nput"'; then
    printf '%s' "$OUT"
    exit 0
  fi
fi

# --- 3. rtk fallback ---------------------------------------------------------
command -v rtk >/dev/null 2>&1 || exit 0
REWRITE="rtk $CMD"
JSON_CMD=$(printf '%s' "$REWRITE" | sed 's/\\/\\\\/g;s/"/\\"/g')
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"%s"}}}' "$JSON_CMD"

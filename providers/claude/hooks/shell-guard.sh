#!/usr/bin/env bash
# Repo-owned PreToolUse Bash hook. Enforces the code-search precedence rule
# mechanically, so it does not depend on model discipline alone: deny a
# `grep`/`rg`/`egrep`/`fgrep` invocation that explicitly targets source files
# (by code-file extension), pointing the agent at `sg` instead. Every other
# command passes through untouched.
#
# Complex commands (heredoc/multiline/cd-chain/command-substitution) fail open
# before the deny, because their grep target cannot be attributed reliably.
set -euo pipefail

# Prefer the Go binary when it has been built — it does real JSON parsing and is
# faster. Fall back to the shell implementation below otherwise. exec preserves
# stdin (the unread hook JSON) and stdout. SHELL_GUARD_NO_GO=1 forces the shell
# fallback regardless (used by bin/ci-check.sh's fallback self-test).
__SG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)" || true
if [ -z "${SHELL_GUARD_NO_GO:-}" ] && [ -n "${__SG_ROOT:-}" ] && [ -x "${__SG_ROOT}/bin/agentic" ]; then
  exec "${__SG_ROOT}/bin/agentic" hook shell-guard
fi

INPUT=$(cat)

extract_raw() {
  # $1 = JSON key. Pulls the first "key": "value" string, still JSON-escaped
  # (no unescaping). A missing key yields an empty string rather than failing
  # the pipeline (which set -e would abort).
  printf '%s' "$INPUT" \
    | grep -oE "\"$1\"[[:space:]]*:[[:space:]]*\"([^\"\\\\]|\\\\.)*\"" \
    | head -1 \
    | sed "s/^\"$1\"[[:space:]]*:[[:space:]]*\"//;s/\"$//" \
    || true
}

extract() {
  # $1 = JSON key. Pulls the first "key": "value" string, tolerating optional
  # whitespace around the colon, and unescaping \" and \\. A missing key yields
  # an empty string rather than failing the pipeline (which set -e would abort).
  extract_raw "$1" | sed 's/\\"/"/g;s/\\\\/\\/g'
}

TOOL=$(extract tool_name)
case "$TOOL" in
  Bash|bash) ;;
  *) exit 0 ;;
esac

RAW_CMD=$(extract_raw command)
[ -z "$RAW_CMD" ] && exit 0

# A JSON \n, \t, or \r in the raw escaped value would decode to a real
# newline/tab/CR — a multi-line or otherwise complex command that must fail
# open (run untouched), never get rewritten (BUG-01: the naive sed unescape
# below leaves these as two literal characters, so the downstream multi-line
# check never sees a real newline and silently mangles the command). Whether
# \\n is a real escape or an escaped backslash followed by a literal n is
# ambiguous to disentangle correctly in POSIX sed, so bail conservatively on
# either — correct-but-conservative beats clever.
case "$RAW_CMD" in
  *'\n'* | *'\t'* | *'\r'*) exit 0 ;;
esac

CMD=$(extract command)
[ -z "$CMD" ] && exit 0

# Complex commands cannot be reliably attributed to a single grep target, so run
# them untouched (fail-open). Covers heredocs, multi-line scripts, `cd` chains,
# and command substitution.
case "$CMD" in
  *'<<'* | *$'\n'* | 'cd '* | *'&& cd '* | *'; cd '* | *'$('* | *'`'*) exit 0 ;;
esac

# --- 1. ast-grep guard -------------------------------------------------------
# Deny only when grep/rg clearly targets code (a code-file extension appears as
# a glob, an --include, or a path arg). Text/log greps fall through. Evaluated
# against a normalized copy of $CMD (leading whitespace, a leading VAR=
# assignment token, and rtk wrapper prefixes stripped to fixpoint) so
# `rtk grep … foo.go` or `FOO=1 grep … foo.go` cannot bypass the deny, mirroring
# Go's stripWrappers.
STRIPPED="$CMD"
while :; do
  PREV="$STRIPPED"
  [[ "$STRIPPED" =~ ^[[:space:]]+(.*)$ ]] && STRIPPED="${BASH_REMATCH[1]}"
  if [[ "$STRIPPED" =~ ^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+(.*)$ ]]; then
    STRIPPED="${BASH_REMATCH[1]}"
  fi
  [ "$STRIPPED" = "$PREV" ] && break
done
NORM="$STRIPPED"
while :; do
  PREV="$NORM"
  case "$NORM" in
    rtk\ *) NORM=${NORM#rtk } ;;
  esac
  [ "$NORM" = "$PREV" ] && break
done
CODE_EXT='go|cs|py|js|jsx|ts|tsx|java|kt|rb|rs|c|h|cc|cpp|hpp|php|swift|scala|sql|vue'
# Test with quoted substrings removed, so a code extension that appears only inside
# the search pattern (e.g. grep "foo.py" data.csv) is not mistaken for a code-file
# target (BUG-03); only an unquoted .ext argument triggers the deny.
UNQUOTED=$(printf '%s' "$NORM" | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g')
if printf '%s' "$NORM" | grep -qE '(^|[|;`]|&&|\|\||\$\()[[:space:]]*(grep|egrep|fgrep|rg)([[:space:]]|$)' \
   && printf '%s' "$UNQUOTED" | grep -qE "\.($CODE_EXT)([[:space:]'\"|;&)]|$)"; then
  REASON="Use ast-grep for structural code search: sg -p '<pattern>' -l <lang>. For a literal string in code, use the native Grep tool instead of shell grep."
  JSON_REASON=$(printf '%s' "$REASON" | sed 's/\\/\\\\/g;s/"/\\"/g')
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$JSON_REASON"
  exit 0
fi

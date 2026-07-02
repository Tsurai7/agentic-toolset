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
#   3. rtk fallback — for simple commands lean-ctx leaves bare (e.g. `python3 …`),
#      prefix `rtk` for token compression. A command a bare prefix would mangle
#      (a leading `VAR=` assignment) passes through untouched instead.
#
# At most one of these fires per command, so there is no double-wrapping.
set -euo pipefail

# Prefer the Go binary when it has been built — it does real JSON parsing and is
# faster. Fall back to the shell implementation below otherwise. exec preserves
# stdin (the unread hook JSON) and stdout. SHELL_GUARD_NO_GO=1 forces the shell
# fallback regardless (used by bin/ci-check.sh's fallback self-test).
__SG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." 2>/dev/null && pwd)"
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

# Complex commands cannot be safely re-quoted inside `lean-ctx -c '…'` or after an
# `rtk` prefix without changing their meaning, so run them untouched (fail-open)
# rather than mangle them. Covers heredocs, multi-line scripts, `cd` chains (whose
# working directory must be preserved), and command substitution.
case "$CMD" in
  *'<<'* | *$'\n'* | 'cd '* | *'&& cd '* | *'; cd '* | *'$('* | *'`'*) exit 0 ;;
esac

# --- 1. ast-grep guard -------------------------------------------------------
# Deny only when grep/rg clearly targets code (a code-file extension appears as
# a glob, an --include, or a path arg). Text/log greps fall through. Evaluated
# against a normalized copy of $CMD (leading rtk/lean-ctx wrapper prefixes
# stripped) so an already-wrapped `rtk grep … foo.go` cannot bypass the deny by
# skipping straight to the already-wrapped exit below.
NORM="$CMD"
while :; do
  case "$NORM" in
    rtk\ *) NORM=${NORM#rtk } ;;
    lean-ctx\ *) NORM=${NORM#lean-ctx } ;;
    *) break ;;
  esac
done
CODE_EXT='go|cs|py|js|jsx|ts|tsx|java|kt|rb|rs|c|h|cc|cpp|hpp|php|swift|scala|sql|vue'
# Test with quoted substrings removed, so a code extension that appears only inside
# the search pattern (e.g. grep "foo.py" data.csv) is not mistaken for a code-file
# target (BUG-03); only an unquoted .ext argument triggers the deny.
UNQUOTED=$(printf '%s' "$NORM" | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g')
if printf '%s' "$NORM" | grep -qE '(^|[|;`]|&&|\|\||\$\()[[:space:]]*(grep|egrep|fgrep|rg)([[:space:]]|$)' \
   && printf '%s' "$UNQUOTED" | grep -qE "\.($CODE_EXT)(\b|['\"]|$)"; then
  REASON="Use ast-grep for structural code search: sg -p '<pattern>' -l <lang>. Plain grep is only for non-code text/logs (see the ast-grep + tool-precedence rules)."
  JSON_REASON=$(printf '%s' "$REASON" | sed 's/\\/\\\\/g;s/"/\\"/g')
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$JSON_REASON"
  exit 0
fi

# Already wrapped — never double-wrap. Runs after the deny above so a
# pre-wrapped grep-on-code command cannot skip the guard.
case "$CMD" in
  lean-ctx\ *|rtk\ *) exit 0 ;;
esac

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
# A naive `rtk <cmd>` prefix only wraps the first segment, so a leading variable
# assignment (`FOO=x …`) would be scoped to rtk's subshell and lost from the rest
# of the command — a wrong-target hazard (see issues/shell-hook-breaks-shell-
# variables.md). lean-ctx safely wraps whole commands above; here, pass such a
# command through untouched rather than mangle it (this also avoids re-wrapping
# an already-wrapped `FOO=1 rtk …`).
command -v rtk >/dev/null 2>&1 || exit 0
if [[ "$CMD" =~ ^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*= ]]; then
  exit 0
fi
# A bare `=`-leading token triggers zsh equals-expansion inside rtk's eval
# (issues/rtk-wrap-breaks-equals-words.md); pass such a command through
# untouched rather than mangle it. `=` inside quotes is an acceptable
# false-positive here — correctness beats compression. The leading-space
# trick covers both a first token and mid-command tokens.
case " $CMD" in
  *' ='*) exit 0 ;;
esac
REWRITE="rtk $CMD"
JSON_CMD=$(printf '%s' "$REWRITE" | sed 's/\\/\\\\/g;s/"/\\"/g')
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"%s"}}}' "$JSON_CMD"

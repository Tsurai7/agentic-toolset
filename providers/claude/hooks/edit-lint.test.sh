#!/usr/bin/env bash
# Self-test for edit-lint.sh — the PostToolUse hook that flags a broken edit before
# the failed-run round-trip. Feeds the hook crafted PostToolUse JSON and asserts it
# injects a note on a parse failure and stays silent otherwise. Wired into ci-check.sh.
set -uo pipefail

HOOK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/edit-lint.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fails=0
checks=0

# Feed the hook one PostToolUse event and assert its stdout. $1 = file, $2 = tool,
# $3 = note|silent, $4 = label. "note" must contain "Syntax check failed"; "silent"
# must be empty.
run_case() {
  local file="$1" tool="$2" expect="$3" label="$4" out
  out="$(printf '{"tool_name":"%s","file_path":"%s"}' "$tool" "$file" | bash "$HOOK")"
  checks=$((checks + 1))
  case "$expect" in
    note)
      if printf '%s' "$out" | grep -q "Syntax check failed"; then
        printf '  ok  %s -> note\n' "$label"
      else
        printf '  FAIL %s: expected a syntax-failure note, got: %s\n' "$label" "${out:-<empty>}"; fails=1
      fi ;;
    silent)
      if [ -z "$out" ]; then
        printf '  ok  %s -> silent\n' "$label"
      else
        printf '  FAIL %s: expected no output, got: %s\n' "$label" "$out"; fails=1
      fi ;;
  esac
}

# --- shell: the gap this test was written to close ---
printf 'if [ -n "$x"\nthen echo hi\n'            > "$TMP/broken.sh"   # missing ]/fi
printf '#!/usr/bin/env bash\nset -e\necho ok\n'  > "$TMP/good.sh"
run_case "$TMP/broken.sh" Write note   "broken .sh"
run_case "$TMP/good.sh"   Write silent "valid .sh"

# --- regression guard: existing checked types keep working ---
printf 'def f(:\n'                > "$TMP/broken.py"                  # syntax error
printf 'def f():\n    return 1\n' > "$TMP/good.py"
run_case "$TMP/broken.py" Edit note   "broken .py"
run_case "$TMP/good.py"   Edit silent "valid .py"

if command -v gofmt >/dev/null 2>&1; then
  printf 'func main() {\n'        > "$TMP/broken.go"                  # unbalanced brace
  run_case "$TMP/broken.go" Write note "broken .go"
fi

# --- fail-open invariants ---
run_case "$TMP/nope.sh"   Write silent "missing file"                # file does not exist
run_case "$TMP/broken.sh" Read  silent "non-edit tool"               # Read is not Edit/Write

if [ "$fails" -eq 0 ]; then
  printf 'edit-lint selftest OK — %s checks.\n' "$checks"; exit 0
fi
printf 'edit-lint selftest FAILED.\n'; exit 1

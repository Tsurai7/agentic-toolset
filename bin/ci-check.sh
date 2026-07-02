#!/usr/bin/env bash
# Static checks for the agentic config repo. Runs locally and in CI.
set -uo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$AGENTIC_ROOT" || exit 1
FAIL=0

ok()   { printf '  OK   %s\n' "$*"; }
warn() { printf '  WARN %s\n' "$*"; }
err()  { printf '  FAIL %s\n' "$*"; FAIL=1; }

echo "== shell syntax (bash -n) =="
while IFS= read -r f; do
  if bash -n "$f" 2>/dev/null; then ok "$f"; else err "$f has syntax errors"; fi
done < <(find . -name '*.sh' -not -path './.git/*')
echo ""

echo "== shellcheck =="
if command -v shellcheck >/dev/null 2>&1; then
  while IFS= read -r f; do
    if shellcheck -S warning "$f"; then ok "$f"; else err "$f failed shellcheck"; fi
  done < <(find . -name '*.sh' -not -path './.git/*')
else
  warn "shellcheck not installed — skipping"
fi
echo ""

echo "== JSON validity =="
while IFS= read -r f; do
  if python3 -m json.tool "$f" >/dev/null 2>&1; then ok "$f"; else err "$f is invalid JSON"; fi
done < <(find . -name '*.json' -not -path './.git/*')
echo ""

echo "== YAML validity =="
if python3 -c 'import yaml' 2>/dev/null; then
  while IFS= read -r f; do
    if python3 -c 'import sys,yaml; yaml.safe_load(open(sys.argv[1]))' "$f" 2>/dev/null; then
      ok "$f"
    else
      err "$f is invalid YAML"
    fi
  done < <(find . \( -name '*.yaml' -o -name '*.yml' \) -not -path './.git/*')
else
  warn "PyYAML not installed — skipping YAML parse"
fi
echo ""

echo "== SKILL.md frontmatter =="
while IFS= read -r f; do
  if head -1 "$f" | grep -q '^---$' \
     && grep -q '^name:' "$f" \
     && grep -q '^description:' "$f"; then
    ok "$f"
  else
    err "$f missing frontmatter name/description"
  fi
done < <(find core/skills -name 'SKILL.md')
echo ""

echo "== agent definitions =="
# NB: agent descriptions must be plain single-line unquoted YAML — the sed
# extraction below (and Claude Code's own loader) assumes that shape.
while IFS= read -r f; do
  base="$(basename "$f" .md)"
  name_val="$(grep -m1 '^name:' "$f" | sed 's/^name:[[:space:]]*//')"
  desc_val="$(grep -m1 '^description:' "$f" | sed 's/^description:[[:space:]]*//')"
  model_val="$(grep -m1 '^model:' "$f" | sed 's/^model:[[:space:]]*//')"
  if head -1 "$f" | grep -q '^---$' && [[ -n "$name_val" && -n "$desc_val" ]]; then
    ok "$f frontmatter"
  else
    err "$f missing frontmatter name/description"
  fi
  if [[ "$name_val" == "$base" ]]; then ok "$f name matches filename"; else err "$f name '$name_val' != filename '$base'"; fi
  words=$(printf '%s\n' "$desc_val" | wc -w | tr -d ' ')
  if [[ "$words" -le 25 ]]; then ok "$f description ${words}w (cap 25)"; else err "$f description ${words}w exceeds 25-word cap"; fi
  case "$model_val" in
    haiku|sonnet|opus|fable|inherit) ok "$f model '$model_val'" ;;
    *) err "$f model '$model_val' not in {haiku,sonnet,opus,fable,inherit}" ;;
  esac
  if grep -q '^tools:' "$f"; then ok "$f tools allowlist present"; else err "$f tools allowlist missing"; fi
done < <(find core/agents -name '*.md' 2>/dev/null)
echo ""

echo "== skill reference links =="
while IFS= read -r f; do
  dir="$(dirname "$f")"
  # Referenced reference files must exist relative to the skill dir
  while IFS= read -r ref; do
    [[ -z "$ref" ]] && continue
    if [[ -f "${dir}/${ref}" ]]; then
      ok "$f -> $ref"
    else
      err "$f references missing ${ref}"
    fi
  done < <(grep -oE 'references/[A-Za-z0-9._-]+\.md' "$f" | sort -u)
done < <(find core/skills -name 'SKILL.md')
echo ""

echo "== markdown links (relative) =="
if python3 "$(dirname "$0")/check-links.py"; then ok "markdown links resolve"; else err "broken markdown links (run bin/check-links.py)"; fi
echo ""

echo "== evals lint (schema, ids, coverage) =="
if python3 evals/lint.py; then ok "eval cases lint"; else err "evals/lint.py failed"; fi
echo ""

echo "== evals self-test (harness logic) =="
if python3 evals/selftest.py; then ok "harness logic"; else err "evals/selftest.py failed"; fi
echo ""

echo "== merge helpers self-test (atomic write) =="
if python3 providers/shared/selftest.py; then ok "merge helpers"; else err "providers/shared/selftest.py failed"; fi
echo ""

echo "== edit-lint hook self-test (flags broken edits) =="
if bash providers/claude/hooks/edit-lint.test.sh >/dev/null 2>&1; then ok "edit-lint flags broken py/go/js/sh edits"; else err "providers/claude/hooks/edit-lint.test.sh failed"; fi
echo ""

echo "== shell-guard fallback self-test (SHELL_GUARD_NO_GO=1) =="
sg_out() { SHELL_GUARD_NO_GO=1 bash providers/claude/hooks/shell-guard.sh <<<"$1"; }
if out=$(sg_out '{"tool_name":"Bash","tool_input":{"command":"echo hi"}}') \
   && [[ "$out" == *'"command":"rtk echo hi"'* ]]; then
  ok "single-line command rewritten with rtk"
else
  err "shell-guard fallback: single-line command not rewritten as expected"
fi
if out=$(sg_out '{"tool_name":"Bash","tool_input":{"command":"echo a\necho b"}}') \
   && [[ "$out" != *updatedInput* ]]; then
  ok "multi-line command fails open (no updatedInput)"
else
  err "shell-guard fallback: multi-line command was rewritten instead of failing open"
fi
if out=$(sg_out '{"tool_name":"Bash","tool_input":{"command":"git grep TODO main.py"}}') \
   && [[ "$out" != *'"permissionDecision":"deny"'* ]]; then
  ok "git grep TODO main.py not denied (grep-token anchored to command position)"
else
  err "shell-guard fallback: git grep TODO main.py was denied"
fi
if out=$(sg_out '{"tool_name":"Bash","tool_input":{"command":"grep -r foo src/main.go"}}') \
   && [[ "$out" == *'"permissionDecision":"deny"'* ]]; then
  ok "grep targeting a code file is denied"
else
  err "shell-guard fallback: grep -r foo src/main.go was not denied"
fi
echo ""

echo "== swe benchmark self-test (task checks; needs Go) =="
if command -v go >/dev/null 2>&1; then
  if out="$(python3 evals/swe_bench.py --selftest 2>&1)"; then
    ok "swe_bench tasks discriminate"
  else
    err "evals/swe_bench.py --selftest failed"
    printf '%s\n' "$out"
  fi
else
  warn "go not installed — skipping swe_bench selftest"
fi
echo ""

echo "== evals parse (dry run) =="
if python3 evals/run.py --track all >/dev/null 2>&1; then ok "eval cases parse"; else err "evals/run.py dry run failed"; fi
echo ""

echo "== memory hygiene (seeds) =="
# Lints the version-controlled seeds only. The --live path needs ~/.claude
# transcripts and must not run in CI.
if python3 core/memory/lint.py >/dev/null 2>&1; then ok "memory seeds lint"; else err "core/memory/lint.py failed"; fi
echo ""

echo "== always-on prefix budget =="
if bash "$(dirname "$0")/prefix-budget.sh" >/dev/null 2>&1; then ok "prefix budget"; else err "always-on prefix over budget (run bin/prefix-budget.sh)"; fi
echo ""

echo "== Go (fmt, vet, test, build) =="
if command -v go >/dev/null 2>&1; then
  unformatted="$(gofmt -l cmd internal 2>/dev/null)"
  if [[ -n "$unformatted" ]]; then err "gofmt needed: ${unformatted//$'\n'/ }"; else ok "gofmt"; fi
  if go vet ./... >/dev/null 2>&1; then ok "go vet"; else err "go vet failed"; fi
  if out="$(go test ./... 2>&1)"; then ok "go test"; else err "go test failed"; printf '%s\n' "$out"; fi
  if go build -o bin/agentic ./cmd/agentic >/dev/null 2>&1; then ok "go build"; else err "go build failed"; fi
else
  warn "go not installed — skipping Go checks"
fi
echo ""

if [[ "$FAIL" -eq 0 ]]; then
  echo "All static checks passed."
  exit 0
fi
echo "Static checks failed."
exit 1

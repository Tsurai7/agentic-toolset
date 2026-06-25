#!/usr/bin/env bash
# Static checks for the agentic config repo. Runs locally and in CI.
set -uo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$AGENTIC_ROOT"
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
  done < <(find . -name '*.yaml' -o -name '*.yml' | grep -v '.git/')
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

echo "== evals lint (schema, ids, coverage) =="
if python3 evals/lint.py; then ok "eval cases lint"; else err "evals/lint.py failed"; fi
echo ""

echo "== evals self-test (harness logic) =="
if python3 evals/selftest.py; then ok "harness logic"; else err "evals/selftest.py failed"; fi
echo ""

echo "== evals parse (dry run) =="
if python3 evals/run.py --track all >/dev/null 2>&1; then ok "eval cases parse"; else err "evals/run.py dry run failed"; fi
echo ""

echo "== memory hygiene (seeds) =="
# Lints the version-controlled seeds only. The --live path needs ~/.claude
# transcripts and must not run in CI.
if python3 core/memory/lint.py >/dev/null 2>&1; then ok "memory seeds lint"; else err "core/memory/lint.py failed"; fi
echo ""

echo "== Go (fmt, vet, test, build) =="
if command -v go >/dev/null 2>&1; then
  unformatted="$(gofmt -l cmd internal 2>/dev/null)"
  if [[ -n "$unformatted" ]]; then err "gofmt needed: ${unformatted//$'\n'/ }"; else ok "gofmt"; fi
  if go vet ./... >/dev/null 2>&1; then ok "go vet"; else err "go vet failed"; fi
  if go test ./... >/dev/null 2>&1; then ok "go test"; else err "go test failed"; fi
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

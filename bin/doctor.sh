#!/usr/bin/env bash
# Health check for agentic install
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
DEEP=0
[[ "${1:-}" == "--deep" ]] && DEEP=1

ok() { printf '  OK  %s\n' "$*"; }
warn() { printf '  WARN %s\n' "$*"; }
fail() { printf '  FAIL %s\n' "$*"; FAIL=1; }

check_link() {
  local path="$1" expected="$2"
  if [[ -L "$path" ]]; then
    local dest
    dest="$(readlink "$path")"
    if [[ "$dest" == "$expected" ]] || [[ "$(cd "$(dirname "$path")" && pwd)/$(readlink "$path")" == "$expected" ]]; then
      ok "symlink $path -> $dest"
    else
      warn "symlink $path -> $dest (expected $expected)"
    fi
  elif [[ -d "$path" ]]; then
    warn "$path is a directory, not symlink to $expected"
  else
    fail "missing $path (run bin/install.sh)"
  fi
}

echo "agentic doctor — $AGENTIC_ROOT"
echo ""

echo "Skills"
check_link "${HOME}/.cursor/skills" "${AGENTIC_ROOT}/core/skills"
check_link "${HOME}/.claude/skills" "${AGENTIC_ROOT}/core/skills"
echo ""

echo "MCP configs"
for f in "${HOME}/.cursor/mcp.json" "${HOME}/.claude/.mcp.json"; do
  if [[ -f "$f" ]]; then
  if grep -q '"gitnexus"' "$f" 2>/dev/null; then
      ok "$f contains gitnexus"
    else
      fail "$f missing gitnexus server"
    fi
  else
    fail "missing $f"
  fi
done
echo ""

echo "Claude memory"
if [[ -f "${HOME}/.claude/CLAUDE.md" ]]; then
  if grep -q "agentic" "${HOME}/.claude/CLAUDE.md"; then
    ok "~/.claude/CLAUDE.md references agentic"
  else
    warn "~/.claude/CLAUDE.md exists but may be stale"
  fi
else
  fail "missing ~/.claude/CLAUDE.md"
fi
echo ""

echo "Binaries"
NPX="${NPX:-/opt/homebrew/bin/npx}"
if [[ -x "$NPX" ]] || command -v npx >/dev/null 2>&1; then
  ok "npx available"
else
  fail "npx not found — set NPX in secrets/.env"
fi
if command -v python3 >/dev/null 2>&1; then
  ok "python3 available"
else
  fail "python3 required for merge-mcp.py"
fi
echo ""

echo "Skills inventory"
count=0
for skill in "${AGENTIC_ROOT}/core/skills"/*/SKILL.md; do
  [[ -f "$skill" ]] || continue
  count=$((count + 1))
done
ok "found $count skill(s) in core/skills"
echo ""

echo "Secrets"
if [[ -f "${AGENTIC_ROOT}/secrets/.env" ]]; then
  ok "secrets/.env present"
else
  warn "secrets/.env missing — copy from secrets/.env.example"
fi
echo ""

echo "Marketplace plugins (manual)"
echo "  Enable per catalog/plugins.yaml in Cursor / Claude marketplaces."
echo ""

if [[ "$DEEP" -eq 1 ]]; then
  echo "Deep checks"
  pinned="$(grep -o 'gitnexus@[^"]*' "${AGENTIC_ROOT}/integrations/gitnexus/mcp.stdio.json" 2>/dev/null || true)"
  if [[ "$pinned" == *"@latest" ]]; then
    warn "gitnexus is unpinned ($pinned) — pin a version for reproducible installs"
  elif [[ -n "$pinned" ]]; then
    ok "gitnexus pinned: $pinned"
  fi
  for f in "${HOME}/.cursor/mcp.json" "${HOME}/.claude/.mcp.json"; do
    [[ -f "$f" ]] || continue
    if python3 -m json.tool "$f" >/dev/null 2>&1; then
      ok "$f is valid JSON"
    else
      fail "$f is invalid JSON"
    fi
  done
  LEAN_CTX="${LEAN_CTX:-/opt/homebrew/bin/lean-ctx}"
  if [[ -x "$LEAN_CTX" ]] || command -v lean-ctx >/dev/null 2>&1; then
    ok "lean-ctx binary available"
  else
    warn "lean-ctx not found — brew install yvgude/lean-ctx/lean-ctx"
  fi
  if command -v ast-grep >/dev/null 2>&1; then
    ok "ast-grep binary available"
  else
    warn "ast-grep not found — brew install ast-grep"
  fi
  echo ""
fi

if [[ "$FAIL" -eq 0 ]]; then
  echo "All checks passed."
  exit 0
fi
echo "Some checks failed."
exit 1

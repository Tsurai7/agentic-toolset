#!/usr/bin/env bash
# Health check for agentic install
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
WARNED=0
DEEP=0
[[ "${1:-}" == "--deep" ]] && DEEP=1

ok() { printf '  OK  %s\n' "$*"; }
# warn() counts: a run with warnings must not report "All checks passed" (that was
# dishonest — a broken skills symlink only warns, yet the summary claimed success).
warn() { printf '  WARN %s\n' "$*"; WARNED=$((WARNED + 1)); }
fail() { printf '  FAIL %s\n' "$*"; FAIL=1; }

check_link() {
  local path="$1" expected="$2"
  if [[ -L "$path" ]]; then
    local dest resolved
    dest="$(readlink "$path")"
    # readlink's target may be absolute (e.g. `ln -sfn /abs/path ...`) or
    # relative to $path's directory; concatenating a dir with an absolute
    # target produces a malformed doubled path, so branch on it explicitly.
    case "$dest" in
      /*) resolved="$dest" ;;
      *) resolved="$(cd "$(dirname "$path")" && pwd)/$dest" ;;
    esac
    if [[ "$resolved" == "$expected" ]]; then
      ok "symlink $path -> $dest"
    else
      warn "symlink $path -> $dest (expected $expected)"
    fi
  elif [[ -d "$path" ]]; then
    warn "$path is a directory, not symlink to $expected"
  elif [[ -e "$path" ]]; then
    warn "$path exists but is not a symlink (expected -> $expected)"
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
# Cursor reads ~/.cursor/mcp.json. Claude Code reads user-scope MCP servers from
# ~/.claude.json (registered via the `claude` CLI), NOT ~/.claude/.mcp.json (PORT-03),
# so that is the file to check for the Claude side.
for f in "${HOME}/.cursor/mcp.json" "${HOME}/.claude.json"; do
  if [[ -f "$f" ]]; then
    ok "$f present"
  else
    fail "missing $f"
  fi
done
echo ""

echo "Claude memory"
if [[ -f "${HOME}/.claude/CLAUDE.md" ]]; then
  if grep -q "agentic" "${HOME}/.claude/CLAUDE.md"; then
    ok "CLAUDE.md (~/.claude) references agentic"
  else
    warn "CLAUDE.md (~/.claude) exists but may be stale"
  fi
else
  fail "missing ~/.claude/CLAUDE.md"
fi
echo ""

echo "Binaries"
# agentic-cfg PATH entry point (symlink created by linkInto during `bin/agentic link`).
# linkInto always writes absolute targets, so we can assume readlink yields an absolute path.
if cmd_path="$(command -v agentic-cfg 2>/dev/null)"; then
  if [[ -L "$cmd_path" ]]; then
    resolved="$(readlink "$cmd_path")"
    if [[ "$resolved" == "${AGENTIC_ROOT}/bin/agentic" ]]; then
      ok "agentic-cfg on PATH -> ${AGENTIC_ROOT}/bin/agentic"
    else
      warn "agentic-cfg on PATH but resolves to $resolved (expected ${AGENTIC_ROOT}/bin/agentic)"
    fi
  else
    warn "agentic-cfg found at $cmd_path but is not a symlink"
  fi
else
  warn "agentic-cfg not on PATH — run bin/install.sh (or bin/agentic link)"
fi
# NPX (if set) is a full path merge-mcp resolves itself; only a hardcoded
# fallback here (that path may not exist on this machine) is dropped —
# `command -v npx` on PATH is the actual signal.
if [[ -x "${NPX:-}" ]] || command -v npx >/dev/null 2>&1; then
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
if [[ "$count" -eq 0 ]]; then
  fail "no skills found in core/skills (broken checkout?)"
else
  ok "found $count skill(s) in core/skills"
fi
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
  if [[ -f "${HOME}/.claude.json" ]] && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if "codebase-memory-mcp" in d.get("mcpServers", {}) else 1)' "${HOME}/.claude.json" 2>/dev/null; then
    if start_out="$(python3 "${AGENTIC_ROOT}/bin/mcp-start-check.py" "${HOME}/.claude.json" codebase-memory-mcp 30 2>&1)"; then
      ok "codebase-memory-mcp MCP server starts (${start_out})"
    else
      fail "codebase-memory-mcp MCP server failed to start: ${start_out}"
    fi
  else
    warn "no codebase-memory-mcp entry in ${HOME}/.claude.json — graph code navigation unavailable"
  fi
  for f in "${HOME}/.cursor/mcp.json" "${HOME}/.claude.json"; do
    [[ -f "$f" ]] || continue
    if python3 -m json.tool "$f" >/dev/null 2>&1; then
      ok "$f is valid JSON"
    else
      fail "$f is invalid JSON"
    fi
  done
  if command -v ast-grep >/dev/null 2>&1; then
    ok "ast-grep binary available"
  else
    warn "ast-grep not found — brew install ast-grep"
  fi
  if command -v no-mistakes >/dev/null 2>&1; then
    ok "no-mistakes binary available"
  else
    warn "no-mistakes not found — see integrations/no-mistakes/README.md"
  fi
  echo ""
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "Some checks failed."
  exit 1
fi
if [[ "$WARNED" -ne 0 ]]; then
  echo "Passed with $WARNED warning(s) — review the WARN lines above."
  exit 0
fi
echo "All checks passed."
exit 0

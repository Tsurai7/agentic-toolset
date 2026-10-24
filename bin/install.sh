#!/usr/bin/env bash
# Install agentic config to Cursor and/or Claude
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROVIDER="all"
DRY_RUN=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--provider cursor|claude|all] [--dry-run]

Sync skills, MCP, and instructions from:
  $AGENTIC_ROOT

EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      PROVIDER="${2:?}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

export DRY_RUN
export AGENTIC_ROOT

# secrets/.env is parsed by exactly one parser — the merge tools (internal/mcpmerge
# LoadEnv / providers/shared/merge-mcp.py load_env), which read it directly. We no
# longer `source` it here: a second (bash) parser disagreed with the merge parser on
# shell-special values, so which one "won" was order-dependent (BUG-14). Nothing in
# the install flow reads those vars except the merge tools. If you need a var in this
# script's own environment, export it in your shell before running install.

# Build bin/agentic from this checkout before dispatching to providers, so a fresh
# machine gets the real JSON-parsing hook (not the shell fallback) and a pulled fix
# never sits behind a stale, previously-built binary (every install rebuilds).
echo ""
if command -v go >/dev/null 2>&1; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would run: go build -o bin/agentic ./cmd/agentic"
  elif ! (cd "$AGENTIC_ROOT" && go build -o bin/agentic ./cmd/agentic); then
    echo "WARN: go build failed — hooks will use the shell fallback" >&2
  fi
else
  echo "WARN: go not found — skipping bin/agentic build; hooks will use the shell fallback" >&2
fi

install_cursor() {
  bash "${AGENTIC_ROOT}/providers/cursor/install.sh"
}

install_claude() {
  bash "${AGENTIC_ROOT}/providers/claude/install.sh"
}

case "$PROVIDER" in
  cursor) install_cursor ;;
  claude) install_claude ;;
  all)
    install_cursor
    install_claude
    ;;
  *)
    echo "Invalid --provider: $PROVIDER" >&2
    exit 1
    ;;
esac

# Link agentic + agentic-cfg onto PATH (~/.local/bin) for convenient access.
echo ""
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] would run: bin/agentic link"
elif [[ -x "${AGENTIC_ROOT}/bin/agentic" ]]; then
  "${AGENTIC_ROOT}/bin/agentic" link
else
  echo "WARN: bin/agentic missing — skipping PATH link (go build failed?)" >&2
fi

# Distribute cross-project memory seeds into active projects (merge-by-name,
# never clobbers local facts). Honors --dry-run.
echo ""
echo "Syncing cross-project memory seeds..."
if [[ "$DRY_RUN" -eq 1 ]]; then
  python3 "${AGENTIC_ROOT}/core/memory/sync.py"
else
  python3 "${AGENTIC_ROOT}/core/memory/sync.py" --apply
fi

echo ""
echo "Install complete. Restart Cursor / Claude Code to pick up MCP and skills."
echo "Optional: add Cursor User Rule per core/instructions/user-rules/cursor-rules-pointer.md"

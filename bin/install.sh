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

# Load secrets if present
if [[ -f "${AGENTIC_ROOT}/secrets/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${AGENTIC_ROOT}/secrets/.env"
  set +a
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

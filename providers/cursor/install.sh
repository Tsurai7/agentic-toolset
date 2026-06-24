#!/usr/bin/env bash
# Sync agentic config to Cursor (~/.cursor)
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"

log() { printf '[cursor] %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] $*"
  else
    "$@"
  fi
}

link_skills() {
  local target="${HOME}/.cursor/skills"
  local source="${AGENTIC_ROOT}/core/skills"
  if [[ -L "$target" ]]; then
    run rm "$target"
  elif [[ -d "$target" ]]; then
    log "backup existing $target"
    if [[ "$DRY_RUN" != "1" ]]; then
      mv "$target" "${target}.bak.$(date +%s)"
    fi
  fi
  run ln -sfn "$source" "$target"
  log "skills: $target -> $source"
}

install_mcp() {
  local out="${HOME}/.cursor/mcp.json"
  if [[ -f "$out" && "$DRY_RUN" != "1" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
    log "backed up existing mcp.json"
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] merge-mcp -> $out"
  else
    python3 "${AGENTIC_ROOT}/providers/shared/merge-mcp.py" "$AGENTIC_ROOT" "$out"
  fi
}

install_rules() {
  local rules_src="${AGENTIC_ROOT}/core/rules"
  local rules_dst="${HOME}/.cursor/rules"
  if [[ ! -d "$rules_src" ]] || [[ -z "$(ls -A "$rules_src" 2>/dev/null || true)" ]]; then
    return 0
  fi
  run mkdir -p "$rules_dst"
  for f in "$rules_src"/*.mdc; do
    [[ -f "$f" ]] || continue
    run ln -sfn "$f" "${rules_dst}/$(basename "$f")"
  done
  log "rules: linked from $rules_src"
}

link_skills
install_mcp
install_rules
log "done"

#!/usr/bin/env bash
# Sync agentic config to Claude (~/.claude)
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"

log() { printf '[claude] %s\n' "$*"; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] $*"
  else
    "$@"
  fi
}

link_skills() {
  local target="${HOME}/.claude/skills"
  local source="${AGENTIC_ROOT}/core/skills"
  run mkdir -p "${HOME}/.claude"
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

install_claude_md() {
  local out="${HOME}/.claude/CLAUDE.md"
  local stub="${AGENTIC_ROOT}/providers/claude/CLAUDE.md.stub"
  local agents="${AGENTIC_ROOT}/core/instructions/AGENTS.md"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] write $out from stub + AGENTS.md"
    return 0
  fi
  if [[ -f "$out" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
  fi
  {
    cat "$stub"
    cat "$agents"
    echo ""
    echo "## User rules"
    for f in "${AGENTIC_ROOT}/core/instructions/user-rules"/*.md; do
      [[ -f "$f" ]] || continue
      echo ""
      echo "### $(basename "$f" .md)"
      cat "$f"
    done
  } >"$out"
  log "wrote $out"
}

install_mcp() {
  local out="${HOME}/.claude/.mcp.json"
  run mkdir -p "${HOME}/.claude"
  if [[ -f "$out" && "$DRY_RUN" != "1" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] merge-mcp -> $out"
  else
    python3 "${AGENTIC_ROOT}/providers/shared/merge-mcp.py" "$AGENTIC_ROOT" "$out"
  fi
}

install_settings_template() {
  local template="${AGENTIC_ROOT}/providers/claude/settings.json.template"
  local out="${HOME}/.claude/settings.json"
  if [[ -f "$out" ]]; then
    log "settings.json exists — skip (edit manually or use settings.local.json)"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] copy settings template -> $out"
  else
    run cp "$template" "$out"
    log "created $out from template"
  fi
}

link_skills
install_claude_md
install_mcp
install_settings_template
log "done"

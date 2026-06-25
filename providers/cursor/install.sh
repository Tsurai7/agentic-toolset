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

AGENTIC_BIN="${AGENTIC_ROOT}/bin/agentic"
# Prefer the built Go binary; fall back to the Python scripts during transition.
run_tool() {
  local sub="$1"; shift
  if [[ -x "$AGENTIC_BIN" ]]; then
    "$AGENTIC_BIN" "$sub" "$@"
  else
    python3 "${AGENTIC_ROOT}/providers/shared/${sub}.py" "$@"
  fi
}

link_skills() {
  local target="${HOME}/.cursor/skills"
  local source="${AGENTIC_ROOT}/core/skills"
  run mkdir -p "${HOME}/.cursor"
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
    run_tool merge-mcp "$AGENTIC_ROOT" "$out"
  fi
}

install_hooks() {
  local src="${AGENTIC_ROOT}/providers/cursor/hooks.json"
  local out="${HOME}/.cursor/hooks.json"
  [[ -f "$src" ]] || return 0
  run mkdir -p "${HOME}/.cursor"
  if [[ -f "$out" && "$DRY_RUN" != "1" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
    log "backed up existing hooks.json"
  fi
  run cp "$src" "$out"
  log "hooks: $out"
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

install_principles() {
  local src="${AGENTIC_ROOT}/core/principles"
  local dst="${HOME}/.cursor/rules"
  [[ -d "$src" ]] || return 0
  run mkdir -p "$dst"
  for f in "$src"/*.md; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == "README.md" ]] && continue
    local name out
    name="$(basename "$f" .md)"
    out="${dst}/principle-${name}.mdc"
    if [[ "$DRY_RUN" == "1" ]]; then
      log "[dry-run] render principle $name -> $out"
      continue
    fi
    {
      printf -- '---\n'
      printf 'description: "Always-on principle: %s"\n' "$name"
      printf 'alwaysApply: true\n'
      printf -- '---\n\n'
      cat "$f"
    } >"$out"
    log "principle: $out"
  done
}

link_skills
install_mcp
install_rules
install_hooks
install_principles
log "done"

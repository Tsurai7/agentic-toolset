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
  local generated="${HOME}/.claude/agentic-cfg.generated.md"
  local stub="${AGENTIC_ROOT}/providers/claude/CLAUDE.md.stub"
  local agents="${AGENTIC_ROOT}/core/instructions/AGENTS.md"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] write $generated from stub + AGENTS.md; ensure @import block in $out"
    return 0
  fi
  run mkdir -p "${HOME}/.claude"
  # The full instruction block lives in a repo-owned generated file we overwrite
  # freely; CLAUDE.md only carries a small managed @import block (PORT-01) so any
  # hand-written user content in CLAUDE.md survives installs.
  {
    sed "s#__AGENTIC_ROOT__#${AGENTIC_ROOT}#g" "$stub"
    cat "$agents"
    echo ""
    echo "## Principles (always-on)"
    for f in "${AGENTIC_ROOT}/core/principles"/*.md; do
      [[ -f "$f" ]] || continue
      [[ "$(basename "$f")" == "README.md" ]] && continue
      echo ""
      cat "$f"
    done
    echo ""
    echo "## User rules"
    for f in "${AGENTIC_ROOT}/core/instructions/user-rules"/*.md; do
      [[ -f "$f" ]] || continue
      # cursor-rules-pointer is Cursor-setup meta, not runtime guidance for a Claude
      # session — keep it out of the always-on Claude prefix (still linked from AGENTS.md).
      [[ "$(basename "$f")" == "cursor-rules-pointer.md" ]] && continue
      echo ""
      echo "### $(basename "$f" .md)"
      cat "$f"
    done
  } >"$generated"
  if [[ -f "$out" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
  fi
  run_tool merge-claude-md "$generated" "$out"
  log "wrote $generated; ensured @import in $out (root: ${AGENTIC_ROOT})"
}

install_mcp() {
  # Claude Code reads user-scope MCP servers from ~/.claude.json (managed via the
  # `claude` CLI), NOT ~/.claude/.mcp.json. Register through the CLI so servers
  # like gitnexus actually load (PORT-03).
  run mkdir -p "${HOME}/.claude"
  DRY_RUN="$DRY_RUN" run_tool merge-mcp "$AGENTIC_ROOT" --register-claude-user
}

install_settings() {
  local fragment="${AGENTIC_ROOT}/providers/claude/settings.hooks.json"
  local out="${HOME}/.claude/settings.json"
  run mkdir -p "${HOME}/.claude"
  # Repo-owned hook scripts must be executable to fire as PreToolUse commands.
  run chmod +x "${AGENTIC_ROOT}/providers/claude/hooks/"*.sh
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] merge hooks + permissions -> $out (preserving env)"
    return 0
  fi
  if [[ -f "$out" ]]; then
    cp "$out" "${out}.bak.$(date +%s)"
  fi
  # Resolve __AGENTIC_ROOT__ to the absolute repo path before merging, so hook
  # commands point at the repo-owned scripts regardless of install location.
  local resolved
  resolved="$(mktemp)"
  sed "s#__AGENTIC_ROOT__#${AGENTIC_ROOT}#g" "$fragment" >"$resolved"
  run_tool merge-settings "$resolved" "$out"
  rm -f "$resolved"
}

link_skills
install_claude_md
install_mcp
install_settings
log "done"

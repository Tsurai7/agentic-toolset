#!/usr/bin/env bash
# Sync agentic config to Claude (~/.claude)
set -euo pipefail

AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DRY_RUN="${DRY_RUN:-0}"
# Tier selects how much of the orientation layer to install. "strong" (default) is the
# full toolset. "weak" omits the lean-ctx Read/Grep redirect hook and the lean-ctx MCP
# server — measured to cut a weak model's per-task overhead from ~5x to <=1x by stopping
# the orientation dance on trivial tasks (plans/impl-overhead/05-minimal-tier-profile.md).
AGENTIC_TIER="${AGENTIC_TIER:-strong}"

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

backup_once() {
  # One-time backup: preserve the user's original file once, then never again, so
  # repeated installs (the docs say to run install after every pull) don't accrete
  # *.bak.<timestamp> files in $HOME (BUG-17). The original is kept at $1.bak.
  local f="$1"
  if [[ -f "$f" && ! -f "${f}.bak" ]]; then
    cp "$f" "${f}.bak"
    log "backed up $f -> ${f}.bak (one-time)"
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
  backup_once "$out"
  run_tool merge-claude-md "$generated" "$out"
  log "wrote $generated; ensured @import in $out (root: ${AGENTIC_ROOT})"
}

install_mcp() {
  # Claude Code reads user-scope MCP servers from ~/.claude.json (managed via the
  # `claude` CLI), NOT ~/.claude/.mcp.json. Register through the CLI so servers
  # like gitnexus actually load (PORT-03).
  run mkdir -p "${HOME}/.claude"
  # Weak tier: don't register the lean-ctx MCP server (its ctx_* tools + "always use
  # lean-ctx" instructions drive the orientation dance that over-tools weak models).
  local exclude=""
  [[ "$AGENTIC_TIER" == "weak" ]] && exclude="lean-ctx"
  DRY_RUN="$DRY_RUN" AGENTIC_MCP_EXCLUDE="$exclude" run_tool merge-mcp "$AGENTIC_ROOT" --register-claude-user
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
  backup_once "$out"
  # Resolve __AGENTIC_ROOT__ to the absolute repo path before merging, so hook
  # commands point at the repo-owned scripts regardless of install location.
  local resolved
  resolved="$(mktemp)"
  sed "s#__AGENTIC_ROOT__#${AGENTIC_ROOT}#g" "$fragment" >"$resolved"
  # Weak tier: drop the lean-ctx Read/Grep redirect hook (the turn-multiplier on
  # trivial tasks). shell-guard, edit-lint, and the observe hooks stay.
  if [[ "$AGENTIC_TIER" == "weak" ]]; then
    python3 - "$resolved" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
pre = s.get("hooks", {}).get("PreToolUse", [])
s["hooks"]["PreToolUse"] = [
    g for g in pre
    if not any("lean-ctx hook redirect" in h.get("command", "") for h in g.get("hooks", []))
]
json.dump(s, open(p, "w"), indent=2)
PY
  fi
  run_tool merge-settings "$resolved" "$out"
  rm -f "$resolved"
}

link_skills
install_claude_md
install_mcp
install_settings
log "done (tier: ${AGENTIC_TIER})"

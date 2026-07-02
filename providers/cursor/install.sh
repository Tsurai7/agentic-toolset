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

backup_once() {
  # One-time backup: preserve the user's original file once, then never again, so
  # repeated installs don't accrete *.bak.<timestamp> files in $HOME (BUG-17).
  local f="$1"
  if [[ -f "$f" && ! -f "${f}.bak" ]]; then
    cp "$f" "${f}.bak"
    log "backed up $f -> ${f}.bak (one-time)"
  fi
}

# is_stale_agentic_symlink prints "yes" if $1 is a symlink whose target is
# unresolvable OR resolves under a path ending "/agentic-cfg/..." (i.e. it
# points into some agentic-cfg checkout, possibly a moved/deleted one).
is_stale_agentic_symlink() {
  local link="$1" resolved
  [[ -L "$link" ]] || return 1
  if resolved="$(readlink -f "$link" 2>/dev/null)" && [[ -e "$resolved" ]]; then
    [[ "$resolved" == */agentic-cfg/* ]] && { echo yes; return 0; }
    return 1
  fi
  echo yes
}

# clean_dangling_symlinks removes stale agentic-cfg symlinks found directly
# inside $1 (one level), leaving any user's own file/symlink untouched.
clean_dangling_symlinks() {
  local dir="$1" f
  [[ -d "$dir" ]] || return 0
  for f in "$dir"/*; do
    [[ -e "$f" || -L "$f" ]] || continue
    if [[ "$(is_stale_agentic_symlink "$f")" == "yes" ]]; then
      run rm "$f"
      log "removed stale symlink: $f"
    fi
  done
}

link_skills() {
  local target="${HOME}/.cursor/skills"
  local source="${AGENTIC_ROOT}/core/skills"
  run mkdir -p "${HOME}/.cursor"
  # $target is normally a single symlink to $source; if it is ever a real dir
  # (e.g. from a hand rollback), clear any stale agentic-cfg symlinks inside it.
  clean_dangling_symlinks "$target"
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
  if [[ "$DRY_RUN" != "1" ]]; then backup_once "$out"; fi
  # merge-mcp respects DRY_RUN: under it, the tool prints the would-be mcp.json
  # (the actual merge preview) and writes nothing.
  run_tool merge-mcp "$AGENTIC_ROOT" "$out"
}

install_hooks() {
  local src="${AGENTIC_ROOT}/providers/cursor/hooks.json"
  local out="${HOME}/.cursor/hooks.json"
  [[ -f "$src" ]] || return 0
  run mkdir -p "${HOME}/.cursor"
  # Merge (not clobber): overwrite only the hook event keys the repo fragment
  # defines, preserving any event/key a user added by hand (BUG per plan 08).
  # Atomic write via safe_io; timestamped backup only when content changes.
  if [[ "$DRY_RUN" == "1" ]]; then
    log "[dry-run] merge hooks -> $out (preserving unknown user keys)"
    return 0
  fi
  PYTHONPATH="${AGENTIC_ROOT}/providers/shared" python3 - "$src" "$out" <<'PY'
import json
import os
import sys
import time

sys.path.insert(0, os.environ["PYTHONPATH"])
from safe_io import atomic_write_text  # noqa: E402

src_path, out_path = sys.argv[1], sys.argv[2]
fragment = json.loads(open(src_path, encoding="utf-8").read())

existing: dict = {}
if os.path.isfile(out_path):
    try:
        existing = json.loads(open(out_path, encoding="utf-8").read()) or {}
    except json.JSONDecodeError:
        existing = {}

before = json.dumps(existing, indent=2, sort_keys=True)

merged = dict(existing)
merged["version"] = fragment.get("version", merged.get("version", 1))
existing_hooks = dict(existing.get("hooks", {}) or {})
existing_hooks.update(fragment.get("hooks", {}))
merged["hooks"] = existing_hooks

after = json.dumps(merged, indent=2, sort_keys=True)
if after == before and os.path.isfile(out_path):
    print(f"hooks: {out_path} already up to date (no backup)")
else:
    if os.path.isfile(out_path):
        backup = f"{out_path}.bak.{int(time.time())}"
        os.rename(out_path, backup)
        print(f"backed up {out_path} -> {backup}")
    atomic_write_text(out_path, json.dumps(merged, indent=2) + "\n")
    print(f"hooks: {out_path}")
PY
}

install_rules() {
  local rules_src="${AGENTIC_ROOT}/core/rules"
  local rules_dst="${HOME}/.cursor/rules"
  clean_dangling_symlinks "$rules_dst"
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

# eject_cursor reverses install: repo-managed skills/rules symlinks, the
# principle-*.mdc files install_principles renders, managed MCP servers (per
# the merge-mcp sidecar), the repo-managed hooks.json keys, and the sidecar
# itself. User content (hand-added symlinks, hooks, MCP servers) is untouched.
# There is no `agentic eject` equivalent for Cursor in the Go CLI (it only
# covers Claude), so this is invoked directly: `bash providers/cursor/install.sh --eject`.
eject_cursor() {
  local skills_target="${HOME}/.cursor/skills"
  local skills_source="${AGENTIC_ROOT}/core/skills"
  if [[ -L "$skills_target" ]] && [[ "$(readlink "$skills_target")" == "$skills_source" ]]; then
    run rm "$skills_target"
    log "removed skills symlink: $skills_target"
  fi

  local rules_dst="${HOME}/.cursor/rules"
  local rules_source="${AGENTIC_ROOT}/core/rules"
  if [[ -d "$rules_dst" ]]; then
    local f target
    for f in "$rules_dst"/*.mdc; do
      [[ -L "$f" ]] || continue
      # install_rules links via `ln -sfn "$f" ...` without canonicalizing, so
      # compare against the same raw (non-realpath'd) form here.
      target="$(readlink "$f" 2>/dev/null || true)"
      if [[ "$target" == "$rules_source"/* ]]; then
        run rm "$f"
        log "removed rule symlink: $f"
      fi
    done
    local src name
    src="${AGENTIC_ROOT}/core/principles"
    if [[ -d "$src" ]]; then
      for f in "$src"/*.md; do
        [[ -f "$f" ]] || continue
        name="$(basename "$f" .md)"
        if [[ -f "${rules_dst}/principle-${name}.mdc" ]]; then
          run rm "${rules_dst}/principle-${name}.mdc"
          log "removed rendered principle: ${rules_dst}/principle-${name}.mdc"
        fi
      done
    fi
  fi

  local mcp_out="${HOME}/.cursor/mcp.json"
  local sidecar="${HOME}/.cursor/.agentic-managed.json"
  if [[ -f "$sidecar" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "[dry-run] remove managed MCP servers from $mcp_out per $sidecar"
    else
      PYTHONPATH="${AGENTIC_ROOT}/providers/shared" python3 - "$mcp_out" "$sidecar" <<'PY'
import json
import os
import sys

sys.path.insert(0, os.environ["PYTHONPATH"])
from safe_io import atomic_write_text  # noqa: E402

mcp_path, sidecar_path = sys.argv[1], sys.argv[2]
managed = json.loads(open(sidecar_path, encoding="utf-8").read()).get("servers", [])
if os.path.isfile(mcp_path):
    data = json.loads(open(mcp_path, encoding="utf-8").read())
    servers = data.get("mcpServers", {})
    for name in managed:
        servers.pop(name, None)
    atomic_write_text(mcp_path, json.dumps(data, indent=2) + "\n")
    print(f"removed {len(managed)} managed MCP server(s) from {mcp_path}")
PY
    fi
    run rm "$sidecar"
    log "removed sidecar: $sidecar"
  fi

  local hooks_out="${HOME}/.cursor/hooks.json"
  local hooks_frag="${AGENTIC_ROOT}/providers/cursor/hooks.json"
  if [[ -f "$hooks_out" ]] && [[ -f "$hooks_frag" ]]; then
    if [[ "$DRY_RUN" == "1" ]]; then
      log "[dry-run] remove repo-managed hook keys from $hooks_out"
    else
      PYTHONPATH="${AGENTIC_ROOT}/providers/shared" python3 - "$hooks_frag" "$hooks_out" <<'PY'
import json
import os
import sys

sys.path.insert(0, os.environ["PYTHONPATH"])
from safe_io import atomic_write_text  # noqa: E402

frag_path, out_path = sys.argv[1], sys.argv[2]
fragment = json.loads(open(frag_path, encoding="utf-8").read())
existing = json.loads(open(out_path, encoding="utf-8").read()) or {}
hooks = dict(existing.get("hooks", {}) or {})
for event in fragment.get("hooks", {}):
    hooks.pop(event, None)
existing["hooks"] = hooks
atomic_write_text(out_path, json.dumps(existing, indent=2) + "\n")
print(f"removed repo-managed hook event(s) from {out_path}")
PY
    fi
  fi
  log "eject complete"
}

if [[ "${1:-}" == "--eject" ]]; then
  eject_cursor
else
  link_skills
  install_mcp
  install_rules
  install_hooks
  install_principles
  log "done"
fi

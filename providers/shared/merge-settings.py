#!/usr/bin/env python3
"""Merge a settings fragment into a provider settings.json.

The repo owns *its own* hook entries and contributes to `permissions.allow`, but
preserves hooks the user added by hand — and every other key in the existing
file, notably machine-local `env` (e.g. a local proxy URL).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_io import atomic_write_text  # noqa: E402


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"merge-settings: invalid JSON in {path}: {exc}")


def _managed_commands(fragment_hooks: dict) -> set:
    """Every command string the repo manages (across all events)."""
    cmds = set()
    for groups in fragment_hooks.values():
        for group in groups:
            for hook in group.get("hooks", []):
                cmd = hook.get("command")
                if cmd:
                    cmds.add(cmd)
    return cmds


def _is_managed_command(cmd: str) -> bool:
    """Recognize a repo-owned hook command by shape, independent of the absolute
    path the command was installed at. Covers `<any path>/lean-ctx hook
    <subcommand>` (e.g. `/opt/homebrew/bin/lean-ctx hook rewrite`) and our own
    providers/claude/hooks/<name>.sh scripts even when their prefix moved or is a
    stale clone path."""
    if "/providers/claude/hooks/" in cmd:
        return True
    fields = cmd.split()
    return len(fields) >= 2 and os.path.basename(fields[0]) == "lean-ctx" and fields[1] == "hook"


# Marks an allow entry as repo-owned (currently only the lean-ctx MCP tools).
# Owned entries form a "managed set": on merge, an owned entry not present in
# the incoming fragment is dropped (e.g. weak tier ships a fragment with none
# of these, which then removes all 12 on merge instead of merely not
# re-adding them) — never a user-added entry, which is anything not matching
# this prefix.
MANAGED_ALLOW_PREFIX = "mcp__lean-ctx__"


def _merge_allow(existing_allow: list, fragment: dict) -> list:
    """Union the fragment's allow entries into existing_allow; for the managed
    set (MANAGED_ALLOW_PREFIX), also drop any existing entry not present in the
    fragment, so a fragment that dropped/shrank its managed entries actually
    removes the stale ones. User-added entries (outside the managed prefix) are
    never touched. A fragment with no "permissions" key expresses no opinion
    and must not wipe the managed set."""
    frag_has_permissions = "permissions" in fragment
    frag_allow = set(fragment.get("permissions", {}).get("allow", []) or [])
    kept = {
        a
        for a in existing_allow
        if not (frag_has_permissions and a.startswith(MANAGED_ALLOW_PREFIX) and a not in frag_allow)
    }
    return sorted(kept | frag_allow)


def _is_managed_group(group: dict, managed_cmds: set) -> bool:
    """True only if every command in the group is one the repo owns, so it is
    safe to replace. A group containing any user command is left untouched."""
    hooks = group.get("hooks", [])
    if not hooks:
        return False
    for hook in hooks:
        cmd = hook.get("command", "")
        if cmd in managed_cmds or _is_managed_command(cmd):
            continue
        return False
    return True


def merge_hooks(existing: dict, fragment_hooks: dict) -> dict:
    """Replace the repo's own hook groups, preserve every user-added hook.

    Events the fragment does not mention are left entirely untouched; within an
    event, only fully-managed groups are dropped before our groups are appended.
    """
    managed_cmds = _managed_commands(fragment_hooks)
    merged = dict(existing)  # keep events (and their order) we do not manage
    for event, our_groups in fragment_hooks.items():
        kept = [
            g
            for g in existing.get(event, [])
            if not _is_managed_group(g, managed_cmds)
        ]
        merged[event] = kept + our_groups
    return merged


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: merge-settings.py <fragment.json> <output settings.json>", file=sys.stderr)
        return 1
    fragment = load_json(Path(sys.argv[1]).resolve())
    output = Path(sys.argv[2]).resolve()
    result = load_json(output) if output.is_file() else {}

    schema = fragment.get("$schema")
    if schema is not None:
        result.setdefault("$schema", schema)
    # Repo owns its own hook entries; user-added hooks are preserved. An existing
    # "hooks": null (a user can hand-edit settings.json to that) is treated as {}
    # rather than crashing merge_hooks's dict(existing) on None.
    if "hooks" in fragment:
        result["hooks"] = merge_hooks(result.get("hooks") or {}, fragment["hooks"])
    # Merge the allow-list with managed-set semantics; keep any existing deny and
    # other permission keys. An existing "permissions": null is treated as {}.
    perms = result.get("permissions") or {}
    result["permissions"] = perms
    perms["allow"] = _merge_allow(perms.get("allow", []) or [], fragment)
    perms.setdefault("deny", [])

    rendered = json.dumps(result, indent=2) + "\n"
    if os.environ.get("DRY_RUN") == "1":
        print(f"[dry-run] would write {output}:\n{rendered}", end="")
        return 0
    atomic_write_text(output, rendered)
    print(f"Merged hooks + {len(perms['allow'])} permission(s) into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

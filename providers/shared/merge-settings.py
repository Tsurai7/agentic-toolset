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


def _is_managed_group(group: dict, managed_cmds: set) -> bool:
    """True only if every command in the group is one the repo owns, so it is
    safe to replace. A group containing any user command is left untouched."""
    hooks = group.get("hooks", [])
    if not hooks:
        return False
    for hook in hooks:
        cmd = hook.get("command", "")
        if cmd in managed_cmds:
            continue
        # Recognize our entries even if the absolute path moved or an older
        # fragment registered an extra lean-ctx subcommand.
        if "/providers/claude/hooks/" in cmd:
            continue
        if cmd.startswith("lean-ctx hook "):
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
    # Repo owns its own hook entries; user-added hooks are preserved.
    if "hooks" in fragment:
        result["hooks"] = merge_hooks(result.get("hooks", {}), fragment["hooks"])
    # Union the allow-list; keep any existing deny and other permission keys.
    frag_allow = fragment.get("permissions", {}).get("allow", [])
    perms = result.setdefault("permissions", {})
    perms["allow"] = sorted(set(perms.get("allow", [])) | set(frag_allow))
    perms.setdefault("deny", [])

    rendered = json.dumps(result, indent=2) + "\n"
    if os.environ.get("DRY_RUN") == "1":
        print(f"[dry-run] would write {output}:\n{rendered}", end="")
        return 0
    atomic_write_text(output, rendered)
    print(f"Merged hooks + {len(frag_allow)} permission(s) into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

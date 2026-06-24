#!/usr/bin/env python3
"""Merge a settings fragment into a provider settings.json.

The repo owns the `hooks` block and contributes to `permissions.allow`. Every
other key in the existing file — notably machine-local `env` (e.g. a local proxy
URL) — is preserved untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"merge-settings: invalid JSON in {path}: {exc}")


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: merge-settings.py <fragment.json> <output settings.json>", file=sys.stderr)
        return 1
    fragment = load_json(Path(sys.argv[1]).resolve())
    output = Path(sys.argv[2]).resolve()
    result = load_json(output) if output.is_file() else {}

    result.setdefault("$schema", fragment.get("$schema"))
    # Repo owns the hooks block.
    if "hooks" in fragment:
        result["hooks"] = fragment["hooks"]
    # Union the allow-list; keep any existing deny and other permission keys.
    frag_allow = fragment.get("permissions", {}).get("allow", [])
    perms = result.setdefault("permissions", {})
    perms["allow"] = sorted(set(perms.get("allow", [])) | set(frag_allow))
    perms.setdefault("deny", [])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Merged hooks + {len(frag_allow)} permission(s) into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

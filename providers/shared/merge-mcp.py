#!/usr/bin/env python3
"""Merge integration MCP fragments into a provider mcp.json file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def load_env(agentic_root: Path) -> dict[str, str]:
    env = {
        "NPX": os.environ.get("NPX", "/opt/homebrew/bin/npx"),
        "PATH": os.environ.get(
            "PATH",
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        ),
        "NODE_PATH": os.environ.get("NODE_PATH", "/opt/homebrew/lib/node_modules"),
    }
    dotenv = agentic_root / "secrets" / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def substitute(obj: object, env: dict[str, str]) -> object:
    if isinstance(obj, str):
        return (
            obj.replace("__NPX__", env["NPX"])
            .replace("__PATH__", env["PATH"])
            .replace("__NODE_PATH__", env["NODE_PATH"])
        )
    if isinstance(obj, dict):
        return {k: substitute(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, env) for v in obj]
    return obj


def collect_fragments(integrations_dir: Path) -> dict:
    merged: dict = {"mcpServers": {}}
    if not integrations_dir.is_dir():
        return merged
    for path in sorted(integrations_dir.glob("**/mcp*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", data)
        if isinstance(servers, dict):
            merged["mcpServers"].update(servers)
    return merged


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: merge-mcp.py <agentic_root> <output_mcp.json>", file=sys.stderr)
        return 1
    agentic_root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    env = load_env(agentic_root)
    overlay_path = agentic_root / "providers" / "cursor" / "mcp.overlay.json"
    base: dict = {"mcpServers": {}}
    if overlay_path.is_file():
        base = json.loads(overlay_path.read_text(encoding="utf-8"))
    fragments = collect_fragments(agentic_root / "integrations")
    base.setdefault("mcpServers", {}).update(fragments.get("mcpServers", {}))
    result = substitute(base, env)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output} ({len(result.get('mcpServers', {}))} server(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

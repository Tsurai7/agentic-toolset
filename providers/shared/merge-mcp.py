#!/usr/bin/env python3
"""Merge integration MCP fragments into a provider mcp.json file."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _which(name: str, fallback: str) -> str:
    return shutil.which(name) or fallback


def _node_path() -> str:
    try:
        out = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.environ.get("NODE_PATH", "")


def load_env(agentic_root: Path) -> dict[str, str]:
    # Resolve tool locations on THIS machine rather than hardcoding Homebrew
    # paths. secrets/.env (loaded below) still overrides anything here.
    env = {
        "NPX": os.environ.get("NPX") or _which("npx", "npx"),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "NODE_PATH": os.environ.get("NODE_PATH") or _node_path(),
        "LEAN_CTX": os.environ.get("LEAN_CTX") or _which("lean-ctx", "lean-ctx"),
        "LEAN_CTX_DATA_DIR": os.environ.get("LEAN_CTX_DATA_DIR")
        or os.path.expanduser("~/.lean-ctx"),
    }
    dotenv = agentic_root / "secrets" / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = os.path.expanduser(value.strip().strip('"').strip("'"))
    return env


def substitute(obj: object, env: dict[str, str]) -> object:
    if isinstance(obj, str):
        for key, value in env.items():
            obj = obj.replace(f"__{key}__", value)
        return obj
    if isinstance(obj, dict):
        return {k: substitute(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, env) for v in obj]
    return obj


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"merge-mcp: invalid JSON in {path}: {exc}")


def collect_fragments(integrations_dir: Path) -> dict:
    merged: dict = {"mcpServers": {}}
    if not integrations_dir.is_dir():
        return merged
    for path in sorted(integrations_dir.glob("**/mcp*.json")):
        data = load_json(path)
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
        base = load_json(overlay_path)
    fragments = collect_fragments(agentic_root / "integrations")
    base.setdefault("mcpServers", {}).update(fragments.get("mcpServers", {}))
    managed = substitute(base, env)

    # Merge into the existing config so servers we do not manage (e.g. work-only
    # servers added by hand) are preserved. Repo-managed servers take precedence.
    result: dict = load_json(output) if output.is_file() else {"mcpServers": {}}
    result.setdefault("mcpServers", {})
    result["mcpServers"].update(managed.get("mcpServers", {}))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    managed_names = ", ".join(sorted(managed.get("mcpServers", {}))) or "none"
    print(
        f"Wrote {output} ({len(result['mcpServers'])} server(s) total; "
        f"managed: {managed_names})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

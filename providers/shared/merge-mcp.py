#!/usr/bin/env python3
"""Merge integration MCP fragments into a provider mcp.json file."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_io import atomic_write_text  # noqa: E402


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


_PLACEHOLDER = re.compile(r"__([A-Z0-9_]+)__")


def substitute(obj: object, env: dict[str, str]) -> object:
    if isinstance(obj, str):
        # Single pass: each __KEY__ is resolved once from the original text, so a
        # resolved value containing a __TOKEN__ is not re-substituted and a
        # prefix key cannot clobber a longer one (BUG-15). Unknown placeholders
        # are left untouched.
        return _PLACEHOLDER.sub(lambda m: env.get(m.group(1), m.group(0)), obj)
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


def _excluded_servers() -> set[str]:
    """Server names to drop, from AGENTIC_MCP_EXCLUDE (comma-separated). The weak
    install tier sets this to omit the orientation-inducing layer (e.g. lean-ctx)."""
    return {n.strip() for n in os.environ.get("AGENTIC_MCP_EXCLUDE", "").split(",") if n.strip()}


def collect_fragments(integrations_dir: Path) -> dict:
    merged: dict = {"mcpServers": {}}
    if not integrations_dir.is_dir():
        return merged
    excluded = _excluded_servers()
    for path in sorted(integrations_dir.glob("**/mcp*.json")):
        data = load_json(path)
        servers = data.get("mcpServers")
        if not isinstance(servers, dict):
            # A fragment must wrap its servers in an mcpServers key; treating a
            # bare/typo'd top-level map as the server set silently injected junk
            # servers (BUG-16). Warn and skip instead.
            print(
                f"merge-mcp: WARNING {path} has no \"mcpServers\" object — skipping "
                "(a fragment must wrap its servers in an mcpServers key)",
                file=sys.stderr,
            )
            continue
        for name, config in servers.items():
            if name in excluded:
                continue
            merged["mcpServers"][name] = config
    return merged


CLAUDE_SERVER_KEYS = ("command", "args", "env", "type", "url", "headers")


def _claude_server_config(config: object) -> dict:
    """Keep only the fields Claude Code understands, dropping e.g. Cursor's
    `autoApprove` (Claude handles auto-approval via settings permissions)."""
    if not isinstance(config, dict):
        return {}
    return {k: v for k, v in config.items() if k in CLAUDE_SERVER_KEYS}


def register_claude_user(agentic_root: Path) -> int:
    """Register repo-managed MCP servers at Claude Code *user* scope via the
    `claude` CLI, which writes ~/.claude.json — the file Claude Code actually
    reads for user-scope servers. Replaces the dead ~/.claude/.mcp.json write so
    servers like gitnexus actually load (PORT-03). Idempotent: each server is
    removed then re-added; user-added servers and other keys are left untouched.
    """
    claude = shutil.which("claude")
    if not claude:
        print(
            "merge-mcp: 'claude' CLI not on PATH — skipping user-scope MCP "
            "registration (add the servers manually with `claude mcp add-json`)",
            file=sys.stderr,
        )
        return 0
    env = load_env(agentic_root)
    warn_if_npx_missing(env)
    fragments = collect_fragments(agentic_root / "integrations")
    managed = substitute(fragments, env).get("mcpServers", {})
    dry = os.environ.get("DRY_RUN") == "1"
    done = []
    for name, config in managed.items():
        payload = json.dumps(_claude_server_config(config))
        if dry:
            print(f"[dry-run] claude mcp add-json {name} <json> --scope user")
            done.append(name)
            continue
        subprocess.run(
            [claude, "mcp", "remove", name, "--scope", "user"],
            capture_output=True, text=True,
        )  # ignore failure: server may not exist yet
        added = subprocess.run(
            [claude, "mcp", "add-json", name, payload, "--scope", "user"],
            capture_output=True, text=True,
        )
        if added.returncode != 0:
            detail = (added.stderr or added.stdout).strip()
            print(f"merge-mcp: failed to register {name}: {detail}", file=sys.stderr)
            return 1
        done.append(name)
    print(
        f"Registered {len(done)} Claude user-scope MCP server(s): "
        f"{', '.join(sorted(done)) or 'none'}"
    )
    return 0


def warn_if_npx_missing(env: dict) -> None:
    """Warn (stderr) when npx can't be resolved, so a 'successful' merge doesn't
    silently leave a dead MCP server (BUG-13). Mirrors the Go path."""
    npx = env.get("NPX", "")
    if shutil.which("npx") is None and npx in ("", "npx"):
        print(
            "merge-mcp: WARNING npx not found on PATH — managed MCP servers that use it "
            "(e.g. gitnexus) will not launch until you install Node/npx (e.g. `brew install node`)",
            file=sys.stderr,
        )


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: merge-mcp.py <agentic_root> <output_mcp.json | --register-claude-user>",
            file=sys.stderr,
        )
        return 1
    agentic_root = Path(sys.argv[1]).resolve()
    if sys.argv[2] == "--register-claude-user":
        return register_claude_user(agentic_root)
    output = Path(sys.argv[2]).resolve()
    env = load_env(agentic_root)
    warn_if_npx_missing(env)
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

    rendered = json.dumps(result, indent=2) + "\n"
    if os.environ.get("DRY_RUN") == "1":
        print(f"[dry-run] would write {output}:\n{rendered}", end="")
        return 0
    atomic_write_text(output, rendered)
    managed_names = ", ".join(sorted(managed.get("mcpServers", {}))) or "none"
    print(
        f"Wrote {output} ({len(result['mcpServers'])} server(s) total; "
        f"managed: {managed_names})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

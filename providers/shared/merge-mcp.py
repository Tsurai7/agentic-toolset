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


def _claude_config_path() -> Path:
    """Resolve the file the `claude` CLI reads/writes user-scope MCP servers to,
    honoring CLAUDE_CONFIG_DIR the same way the CLI itself does."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / ".claude.json"
    return Path.home() / ".claude.json"


def _registered_server_json(name: str) -> str | None:
    """Return the currently-registered config for `name` at user scope, as a
    JSON string suitable for `claude mcp add-json`, or None if not registered.
    Read directly from the CLI's own config file: `claude mcp get` prints a
    human status summary, not the server's JSON config, so it cannot be used to
    restore a server on a failed re-add."""
    path = _claude_config_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    servers = data.get("mcpServers", {})
    if name not in servers:
        return None
    return json.dumps(servers[name])


def register_claude_user(agentic_root: Path) -> int:
    """Register repo-managed MCP servers at Claude Code *user* scope via the
    `claude` CLI, which writes ~/.claude.json — the file Claude Code actually
    reads for user-scope servers. Replaces the dead ~/.claude/.mcp.json write so
    servers like gitnexus actually load (PORT-03). Idempotent: each server is
    removed then re-added; user-added servers and other keys are left untouched.

    Transactional-ish per server: the server's current registration is captured
    before it is removed, so a failed re-add can be restored instead of leaving
    the server permanently unregistered. A failure is recorded and the loop
    CONTINUES with the remaining servers (a single flaky server must not abort
    registration of every server after it); the function exits nonzero and
    lists every failed server if any remain unregistered at the end.
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
    failed = []
    for name, config in managed.items():
        payload = json.dumps(_claude_server_config(config))
        if dry:
            print(f"[dry-run] claude mcp add-json {name} <json> --scope user")
            done.append(name)
            continue
        previous = _registered_server_json(name)
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
            failed.append(name)
            if previous is not None:
                restored = subprocess.run(
                    [claude, "mcp", "add-json", name, previous, "--scope", "user"],
                    capture_output=True, text=True,
                )
                if restored.returncode == 0:
                    print(
                        f"merge-mcp: failed to register {name}: {detail} (restored prior registration)",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"merge-mcp: failed to register {name}: {detail} "
                        "(restore also failed — server is now UNREGISTERED)",
                        file=sys.stderr,
                    )
            else:
                print(f"merge-mcp: failed to register {name}: {detail}", file=sys.stderr)
            continue
        done.append(name)
    print(
        f"Registered {len(done)} Claude user-scope MCP server(s): "
        f"{', '.join(sorted(done)) or 'none'}"
    )
    if failed:
        print(
            f"merge-mcp: {len(failed)} server(s) failed to register: {', '.join(sorted(failed))}",
            file=sys.stderr,
        )
        return 1
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


SIDECAR_NAME = ".agentic-managed.json"
SIDECAR_VERSION = 1


def _sidecar_path(output: Path) -> Path:
    return output.parent / SIDECAR_NAME


def _load_sidecar(path: Path) -> list[str] | None:
    """Return the previously-managed server names, or None if no sidecar exists
    yet (first run: bootstrap only, never retro-claim existing entries)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    names = data.get("servers")
    return names if isinstance(names, list) else None


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
    fragments = collect_fragments(agentic_root / "integrations")
    managed = substitute(fragments, env)
    managed_names = sorted(managed.get("mcpServers", {}))

    # Merge into the existing config so servers we do not manage (e.g. work-only
    # servers added by hand) are preserved. Repo-managed servers take precedence.
    result: dict = load_json(output) if output.is_file() else {"mcpServers": {}}
    result.setdefault("mcpServers", {})
    result["mcpServers"].update(managed.get("mcpServers", {}))

    # Remove servers this repo used to manage but no longer does (fragment deleted
    # from the repo). A server never seen in the sidecar (hand-added by the user)
    # is never touched. First run without a sidecar only bootstraps it — it does
    # not retro-claim/remove any pre-existing entry.
    sidecar_path = _sidecar_path(output)
    previously_managed = _load_sidecar(sidecar_path)
    removed_names: list[str] = []
    if previously_managed is not None:
        removed_names = sorted(set(previously_managed) - set(managed_names))
        for name in removed_names:
            result["mcpServers"].pop(name, None)

    rendered = json.dumps(result, indent=2) + "\n"
    sidecar_rendered = (
        json.dumps({"version": SIDECAR_VERSION, "servers": managed_names}, indent=2) + "\n"
    )
    if os.environ.get("DRY_RUN") == "1":
        print(f"[dry-run] would write {output}:\n{rendered}", end="")
        print(f"[dry-run] would write {sidecar_path}:\n{sidecar_rendered}", end="")
        return 0
    atomic_write_text(output, rendered)
    atomic_write_text(sidecar_path, sidecar_rendered)
    print(
        f"Wrote {output} ({len(result['mcpServers'])} server(s) total; "
        f"managed: {', '.join(managed_names) or 'none'})"
    )
    if removed_names:
        print(f"Removed stale managed server(s): {', '.join(removed_names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

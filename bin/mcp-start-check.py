#!/usr/bin/env python3
"""Prove a stdio MCP server actually starts and completes the handshake.

`doctor.sh --deep` and the JSON-validity checks only confirm a server is
*registered*; they never spawn it, so a runtime-incompatible pin (wrong Node
version, missing dep) shows up as a silent outage — the server is listed but
dead. This spawns the command from a `mcpServers.<name>` entry, sends a
JSON-RPC `initialize` request on stdin, and waits for a matching response.

Usage: python3 bin/mcp-start-check.py <config.json> <server-name> [timeout-sec]

`<config.json>` has the `mcpServers.<server-name>` shape used by
`~/.claude.json` — a `command`, an `args` list, and an optional `env` dict
merged over `os.environ`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

DEFAULT_TIMEOUT = 30


def load_server(config_path: str, name: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    servers = config.get("mcpServers", {})
    if name not in servers:
        raise KeyError(f"'{name}' not found in mcpServers of {config_path}")
    return servers[name]


def read_stdout(pipe, lines: list[str], stop: threading.Event) -> None:
    for line in iter(pipe.readline, ""):
        lines.append(line)
        if stop.is_set():
            return


def read_stderr(pipe, lines: list[str]) -> None:
    for line in iter(pipe.readline, ""):
        lines.append(line)


def check(config_path: str, name: str, timeout: int) -> int:
    server = load_server(config_path, name)
    env = dict(os.environ)
    env.update(server.get("env", {}))
    command = [server["command"], *server.get("args", [])]

    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    stop = threading.Event()
    out_thread = threading.Thread(target=read_stdout, args=(proc.stdout, stdout_lines, stop), daemon=True)
    err_thread = threading.Thread(target=read_stderr, args=(proc.stderr, stderr_lines), daemon=True)
    out_thread.start()
    err_thread.start()

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-start-check", "version": "1.0"},
        },
    }
    try:
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        pass  # process may have already exited; fall through to the deadline loop

    deadline = time.monotonic() + timeout
    reason = "timeout"
    response = None
    seen = 0
    while time.monotonic() < deadline:
        if proc.poll() is not None and len(stdout_lines) == seen:
            reason = f"process exited rc={proc.returncode}"
            break
        while seen < len(stdout_lines):
            line = stdout_lines[seen]
            seen += 1
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("id") == 1:
                response = msg
                break
        if response is not None:
            break
        time.sleep(0.05)

    stop.set()
    proc.kill()
    proc.wait()

    if response is None:
        print(f"FAIL {name}: {reason}", file=sys.stderr)
        for line in stderr_lines[:3]:
            print(line.rstrip(), file=sys.stderr)
        return 1

    server_info = response.get("result", {}).get("serverInfo")
    if not server_info:
        print(f"FAIL {name}: bad response", file=sys.stderr)
        for line in stderr_lines[:3]:
            print(line.rstrip(), file=sys.stderr)
        return 1

    print(f"OK {name} {server_info.get('name')} {server_info.get('version')}")
    return 0


def main() -> int:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <config.json> <server-name> [timeout-sec]", file=sys.stderr)
        return 2
    config_path = sys.argv[1]
    name = sys.argv[2]
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TIMEOUT
    try:
        return check(config_path, name, timeout)
    except KeyError as e:
        print(f"FAIL {name}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

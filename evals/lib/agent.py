"""Agent invocation and transcript handling, shared by both eval tracks.

Kept provider-agnostic on purpose: the agent is a CLI string (`AGENTIC_EVAL_AGENT_CMD`),
so a Cursor or other headless agent can be swapped in without touching the harness.
The Claude Code specifics (stream-json, --model) are applied only when the command
is `claude`.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess


def run_capture(cmd: str, prompt: str, *, model: str | None = None,
                env: dict[str, str] | None = None, timeout: int = 600) -> str:
    """Invoke a CLI agent with a prompt, returning captured stdout.

    `model` and `env` let the value track run the same prompt under different
    models and isolated config directories (see lib/render_config.py).
    """
    argv = shlex.split(cmd)
    if argv and argv[0] == "claude":
        # stream-json + verbose surfaces tool calls in the transcript; the judge
        # and the efficiency metrics both rely on seeing them.
        if "--output-format" not in argv:
            argv += ["--output-format", "stream-json", "--verbose"]
        if model and "--model" not in argv:
            argv += ["--model", model]
    proc_env = {**os.environ, **env} if env else None
    proc = subprocess.run(
        [*argv, prompt], capture_output=True, text=True, timeout=timeout, env=proc_env
    )
    return proc.stdout or proc.stderr


def final_text(raw: str) -> str:
    """Extract the agent's final reply from a transcript.

    Claude Code stream-json emits one JSON object per line; the assistant's
    answer lives in the `result` field of the terminal `{"type":"result"}`
    event, surrounded by hook/system noise. Plain-text CLIs return as-is.
    """
    result = None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "result" and isinstance(obj.get("result"), str):
            result = obj["result"]
    return result if result is not None else raw


def clip(transcript: str, head: int = 12000, tail: int = 8000) -> str:
    """Fit a transcript into the judge's budget without dropping the answer.

    A naive `transcript[:N]` truncates the head, but a long skill/tool load can
    push the agent's final reply past N — the judge then sees only setup noise.
    Keep the head (early tool calls prove a skill fired) and the tail (where the
    final answer lands), eliding the middle.
    """
    if len(transcript) <= head + tail:
        return transcript
    elided = len(transcript) - head - tail
    return f"{transcript[:head]}\n...[{elided} chars elided]...\n{transcript[-tail:]}"


def metrics(raw: str) -> dict:
    """Cheap efficiency signals read straight from a stream-json transcript.

    Free to compute (no extra model calls): tool-call count, transcript size, and
    the token usage reported by the terminal result event (input / output / cache).
    Recording real tokens per arm turns the value track's economy signal into a
    measured token delta rather than a proxy (transcript_chars alone).
    """
    tool_calls = 0
    usage: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Assistant messages carry tool_use blocks in their content array.
        if obj.get("type") == "assistant":
            content = obj.get("message", {}).get("content", [])
            tool_calls += sum(
                1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
            )
        # The terminal result event carries cumulative token usage for the run.
        elif obj.get("type") == "result" and isinstance(obj.get("usage"), dict):
            u = obj["usage"]
            usage = {
                "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
                "cache_read_tokens": u.get("cache_read_input_tokens", 0),
                "cache_creation_tokens": u.get("cache_creation_input_tokens", 0),
            }
    m = {"tool_calls": tool_calls, "transcript_chars": len(raw)}
    if usage:
        usage["total_input_tokens"] = (
            usage["input_tokens"] + usage["cache_read_tokens"] + usage["cache_creation_tokens"]
        )
        m.update(usage)
    return m

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

    Free to compute (no extra model calls): tool-call count, transcript size, the
    token usage reported by the terminal result event (input / output / cache), and
    the run-level cost/latency/turns. Two derived fields make the toolset-overhead
    instrument honest: `repriced_input_tokens` (= input + cache_creation, the billed
    cost once near-free cache_read is excluded) and `prefix_turn1_ctx` (the first
    assistant turn's whole context — a proxy for the always-on prefix weight).
    Recording real tokens per arm turns the value track's economy signal into a
    measured token delta rather than a proxy (transcript_chars alone).
    """
    tool_calls = 0
    usage: dict = {}
    extra: dict = {}
    prefix_turn1_ctx = None
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
            msg = obj.get("message", {})
            content = msg.get("content", [])
            tool_calls += sum(
                1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
            )
            # The first assistant turn's context size proxies the always-on prefix.
            if prefix_turn1_ctx is None and isinstance(msg.get("usage"), dict):
                tu = msg["usage"]
                prefix_turn1_ctx = (
                    tu.get("input_tokens", 0)
                    + tu.get("cache_read_input_tokens", 0)
                    + tu.get("cache_creation_input_tokens", 0)
                )
        # The terminal result event carries cumulative token usage for the run.
        elif obj.get("type") == "result":
            if isinstance(obj.get("usage"), dict):
                u = obj["usage"]
                usage = {
                    "input_tokens": u.get("input_tokens", 0),
                    "output_tokens": u.get("output_tokens", 0),
                    "cache_read_tokens": u.get("cache_read_input_tokens", 0),
                    "cache_creation_tokens": u.get("cache_creation_input_tokens", 0),
                }
            for src, dst in (("total_cost_usd", "cost_usd"),
                             ("duration_ms", "duration_ms"),
                             ("num_turns", "num_turns")):
                if obj.get(src) is not None:
                    extra[dst] = obj[src]
    m = {"tool_calls": tool_calls, "transcript_chars": len(raw)}
    if usage:
        usage["total_input_tokens"] = (
            usage["input_tokens"] + usage["cache_read_tokens"] + usage["cache_creation_tokens"]
        )
        usage["repriced_input_tokens"] = usage["input_tokens"] + usage["cache_creation_tokens"]
        m.update(usage)
    if prefix_turn1_ctx is not None:
        m["prefix_turn1_ctx"] = prefix_turn1_ctx
    m.update(extra)
    return m


def overhead_ratios(on: dict, off: dict) -> dict:
    """ON/OFF ratios for the toolset-overhead instrument (pure arithmetic).

    Each ratio is `metrics(on)[k] / metrics(off)[k]`, or None when the OFF
    denominator is missing or zero. `total_input_ratio` is the headline number the
    owner set the ≤1.5x bar on; `repriced_input_ratio` and `cost_ratio` are the
    honest billed views (see metrics()).
    """
    def ratio(key: str):
        a, b = on.get(key), off.get(key)
        if a is None or not b:
            return None
        return a / b

    return {
        "total_input_ratio": ratio("total_input_tokens"),
        "repriced_input_ratio": ratio("repriced_input_tokens"),
        "output_ratio": ratio("output_tokens"),
        "cost_ratio": ratio("cost_usd"),
        "tool_calls_ratio": ratio("tool_calls"),
    }

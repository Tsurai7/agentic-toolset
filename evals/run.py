#!/usr/bin/env python3
"""Run agent-behavior evals for the agentic config.

Each case in cases/*.json sends a prompt to the agent headless, captures the
transcript (including tool calls), and asks an LLM judge whether the transcript
satisfies the case's `expect` / `expect_not` behaviors.

Dry by default. Set AGENTIC_EVAL_CONFIRM=1 to actually invoke the agent.
Run real evals from a throwaway scratch repo so a misbehaving case cannot touch
real work.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent / "cases"
AGENT_CMD = os.environ.get("AGENTIC_EVAL_AGENT_CMD", "claude -p")
JUDGE_CMD = os.environ.get("AGENTIC_EVAL_JUDGE_CMD", "claude -p")
CONFIRM = os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"

JUDGE_TEMPLATE = """You are grading whether an AI coding agent followed its configured rules.

RULE UNDER TEST:
{rule}

AGENT TRANSCRIPT (includes tool calls):
{transcript}

The agent SHOULD exhibit each of these behaviors:
{expect}

The agent MUST NOT exhibit any of these behaviors:
{expect_not}

Reply with a single JSON object and nothing else:
{{"verdict": "PASS" | "FAIL", "reason": "one sentence"}}
PASS only if every SHOULD behavior is present and no MUST-NOT behavior occurred.
"""


def load_cases() -> list[dict]:
    return [json.loads(p.read_text("utf-8")) for p in sorted(CASES_DIR.glob("*.json"))]


def run_capture(cmd: str, prompt: str) -> str:
    """Invoke a CLI agent with a prompt, returning captured stdout."""
    argv = shlex.split(cmd)
    # Claude Code: stream-json + verbose surfaces tool calls in the transcript.
    if argv and argv[0] == "claude" and "--output-format" not in argv:
        argv += ["--output-format", "stream-json", "--verbose"]
    proc = subprocess.run(
        [*argv, prompt], capture_output=True, text=True, timeout=600
    )
    return proc.stdout or proc.stderr


def judge(case: dict, transcript: str) -> dict:
    prompt = JUDGE_TEMPLATE.format(
        rule=case["rule"],
        transcript=transcript[:20000],
        expect="\n".join(f"- {b}" for b in case.get("expect", [])) or "- (none)",
        expect_not="\n".join(f"- {b}" for b in case.get("expect_not", [])) or "- (none)",
    )
    raw = run_capture(JUDGE_CMD, prompt)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"verdict": "FAIL", "reason": f"unparseable judge output: {raw[:200]}"}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {"verdict": "FAIL", "reason": f"unparseable judge JSON: {raw[start:end+1][:200]}"}


def main() -> int:
    cases = load_cases()
    if not cases:
        print("No cases found in", CASES_DIR, file=sys.stderr)
        return 1

    if not CONFIRM:
        print(f"DRY RUN — {len(cases)} case(s). Set AGENTIC_EVAL_CONFIRM=1 to execute.\n")
        for c in cases:
            print(f"  [{c['id']}] guards: {c['rule']}")
            print(f"      agent <- {AGENT_CMD} {c['prompt']!r}")
        print("\nNothing was executed.")
        return 0

    failures = 0
    for c in cases:
        print(f"== {c['id']} ==")
        transcript = run_capture(AGENT_CMD, c["prompt"])
        verdict = judge(c, transcript)
        mark = "PASS" if verdict.get("verdict") == "PASS" else "FAIL"
        if mark == "FAIL":
            failures += 1
        print(f"  {mark}: {verdict.get('reason', '')}\n")

    total = len(cases)
    print(f"{total - failures}/{total} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""LLM-as-judge grading for both tracks.

Conformance uses a single-transcript PASS/FAIL judge (does the agent obey the
rule). Value uses a pairwise judge (is the treatment transcript better than the
control one). The pairwise judge runs each comparison in both orders and reports
the flip rate, because LLM judges carry a position bias — anything above
FLIP_THRESHOLD means the verdict is order-dependent and not trustworthy.
"""

from __future__ import annotations

import json

from . import agent

FLIP_THRESHOLD = 0.10  # >10% order-dependence ⇒ verdict UNRELIABLE (common LLM-judge guidance)

_CONFORMANCE_TEMPLATE = """You are grading whether an AI coding agent followed its configured rules.

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

_PAIRWISE_TEMPLATE = """You are comparing two AI coding agents on the SAME task. One ran with a
capability enabled (a skill/rule/tool), the other with it removed. Decide which
transcript better satisfies the hypothesis and rubric. Judge outcome quality, not
verbosity; a longer transcript is not automatically better.

HYPOTHESIS (what the capability is supposed to improve):
{hypothesis}

RUBRIC (what a good outcome looks like):
{rubric}

--- TRANSCRIPT A ---
{a}

--- TRANSCRIPT B ---
{b}

Reply with a single JSON object and nothing else:
{{"winner": "A" | "B" | "TIE", "reason": "one sentence"}}
"""


def _parse_json_object(raw: str) -> dict | None:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def judge_conformance(case: dict, transcript: str, judge_cmd: str) -> dict:
    prompt = _CONFORMANCE_TEMPLATE.format(
        rule=case["rule"],
        transcript=agent.clip(transcript),
        expect="\n".join(f"- {b}" for b in case.get("expect", [])) or "- (none)",
        expect_not="\n".join(f"- {b}" for b in case.get("expect_not", [])) or "- (none)",
    )
    raw = agent.final_text(agent.run_capture(judge_cmd, prompt))
    parsed = _parse_json_object(raw)
    if parsed is None:
        return {"verdict": "FAIL", "reason": f"unparseable judge output: {raw[:200]}"}
    return parsed


def _judge_once(case: dict, a: str, b: str, judge_cmd: str) -> str:
    """One pairwise comparison; returns the winning slot label ('A'|'B'|'TIE')."""
    prompt = _PAIRWISE_TEMPLATE.format(
        hypothesis=case.get("hypothesis", "(none)"),
        rubric="\n".join(f"- {r}" for r in case.get("rubric", [])) or "- (none)",
        a=agent.clip(a),
        b=agent.clip(b),
    )
    raw = agent.final_text(agent.run_capture(judge_cmd, prompt))
    parsed = _parse_json_object(raw) or {}
    return parsed.get("winner", "TIE")


def judge_pairwise(case: dict, treatment: str, control: str, judge_cmd: str) -> dict:
    """Compare treatment vs control in BOTH orders to expose position bias.

    Returns the winner from the agent's point of view ('treatment'|'control'|'tie'),
    plus the flip rate across the two orderings and a `reliable` flag. With a single
    swap pair, flip_rate is 0.0 (orders agree) or 1.0 (they disagree); callers
    aggregate flip_rate across the case's N repeats for a stabler estimate.
    """
    # Order 1: treatment=A, control=B.
    w1 = _judge_once(case, treatment, control, judge_cmd)
    pick1 = {"A": "treatment", "B": "control", "TIE": "tie"}[w1]
    # Order 2: swapped, so treatment=B now.
    w2 = _judge_once(case, control, treatment, judge_cmd)
    pick2 = {"A": "control", "B": "treatment", "TIE": "tie"}[w2]

    flipped = pick1 != pick2
    winner = pick1 if pick1 == pick2 else "tie"
    return {
        "winner": winner,
        "order1": pick1,
        "order2": pick2,
        "flip_rate": 1.0 if flipped else 0.0,
        "reliable": not flipped,
    }

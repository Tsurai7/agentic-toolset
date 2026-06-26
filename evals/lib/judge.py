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


# --- metric track (no LLM) -----------------------------------------------------

_METRIC_OPS = {
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
    ">": lambda v, t: v > t,
    "<": lambda v, t: v < t,
}


def judge_metric(case: dict, value: float) -> dict:
    """Grade a measured number against the case threshold. Pure logic, no judge."""
    op, threshold = case["op"], case["threshold"]
    ok = _METRIC_OPS[op](value, threshold)
    return {
        "verdict": "PASS" if ok else "FAIL",
        "reason": f"{case['metric']}={value:.4f} {op} {threshold}",
    }


# --- toolset-overhead gate (no LLM) --------------------------------------------

OVERHEAD_EASY_MAX = 1.5  # the owner's ≤1.5x bar for the easy/lookup regime
OVERHEAD_HARD_MAX = 1.0  # the toolset must keep paying off where it matters


def judge_overhead(easy: dict, hard: dict | None = None, *,
                   easy_max: float = OVERHEAD_EASY_MAX,
                   hard_max: float = OVERHEAD_HARD_MAX) -> dict:
    """Grade the toolset-overhead measurement against the ≤1.5x bar. Pure logic.

    `easy`/`hard` are per-regime dicts produced from `agent.overhead_ratios()` plus
    correctness flags, e.g.::

        {"total_input_ratio": 1.3, "cost_ratio": 1.2,
         "correct_on": True, "correct_off": True}

    Easy regime: total-input and cost overhead must each be <= easy_max (inclusive),
    and the toolset must not regress correctness (ON wrong while OFF right). Hard
    regime (optional): total-input overhead must be <= hard_max, i.e. the toolset
    still pays for itself on work that warrants it.
    """
    reasons: list[str] = []
    ok = True

    ti = easy.get("total_input_ratio")
    if ti is None:
        ok = False
        reasons.append("easy: missing total_input_ratio")
    elif ti > easy_max:
        ok = False
        reasons.append(f"easy total_input {ti:.2f}x > {easy_max}x")
    else:
        reasons.append(f"easy total_input {ti:.2f}x <= {easy_max}x")

    cr = easy.get("cost_ratio")
    if cr is not None:
        if cr > easy_max:
            ok = False
            reasons.append(f"easy cost {cr:.2f}x > {easy_max}x")
        else:
            reasons.append(f"easy cost {cr:.2f}x <= {easy_max}x")

    if easy.get("correct_off") and not easy.get("correct_on"):
        ok = False
        reasons.append("easy: correctness regression (ON wrong, OFF right)")

    if hard is not None:
        hti = hard.get("total_input_ratio")
        if hti is not None:
            if hti > hard_max:
                ok = False
                reasons.append(f"hard total_input {hti:.2f}x > {hard_max}x (toolset not paying off)")
            else:
                reasons.append(f"hard total_input {hti:.2f}x <= {hard_max}x")

    return {"verdict": "PASS" if ok else "FAIL", "reasons": reasons}

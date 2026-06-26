#!/usr/bin/env python3
"""Pure-logic self-tests for the harness — no agent, no judge, no tokens.

Guards the two subtle, non-LLM pieces: the pairwise order-swap mapping (which
turns raw slot picks into treatment/control verdicts and detects position bias)
and the value verdict thresholds. Runs in CI alongside lint.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
from lib import agent, judge  # noqa: E402


def _load_run():
    spec = importlib.util.spec_from_file_location("run", EVALS / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pairwise_detects_position_bias():
    # A judge that always picks the first slot is pure position bias: swapping the
    # order flips the winner, so flip_rate=1.0 and the verdict is not reliable.
    judge._judge_once = lambda case, a, b, jc: "A"
    r = judge.judge_pairwise({}, "TREAT", "CTRL", "x")
    assert r["order1"] == "treatment" and r["order2"] == "control", r
    assert r["flip_rate"] == 1.0 and r["winner"] == "tie" and r["reliable"] is False, r


def test_pairwise_stable_preference():
    # A judge that prefers the treatment content regardless of slot is stable.
    judge._judge_once = lambda case, a, b, jc: ("A" if a == "TREAT" else "B")
    r = judge.judge_pairwise({}, "TREAT", "CTRL", "x")
    assert r["order1"] == "treatment" and r["order2"] == "treatment", r
    assert r["flip_rate"] == 0.0 and r["winner"] == "treatment" and r["reliable"], r


def test_value_verdict_thresholds():
    vv = _load_run()._value_verdict
    pref = {"pass_condition": "treatment_preferred"}
    notworse = {"pass_condition": "treatment_not_worse"}
    assert vv(pref, {"treatment": 3, "control": 0, "tie": 0}, 0.0) == "PASS"
    assert vv(pref, {"treatment": 1, "control": 2, "tie": 0}, 0.0) == "FAIL"
    assert vv(pref, {"treatment": 3, "control": 0, "tie": 0}, 0.5) == "UNRELIABLE"
    assert vv(notworse, {"treatment": 1, "control": 1, "tie": 1}, 0.0) == "PASS"
    assert vv(notworse, {"treatment": 0, "control": 3, "tie": 0}, 0.0) == "FAIL"


def test_metric_verdict():
    # judge_metric is pure threshold logic — the boundary is inclusive for >=.
    ge = {"metric": "weighted_cache_hit_rate", "op": ">=", "threshold": 0.80}
    assert judge.judge_metric(ge, 0.95)["verdict"] == "PASS"
    assert judge.judge_metric(ge, 0.80)["verdict"] == "PASS"
    assert judge.judge_metric(ge, 0.75)["verdict"] == "FAIL"
    le = {"metric": "x", "op": "<=", "threshold": 0.10}
    assert judge.judge_metric(le, 0.05)["verdict"] == "PASS"
    assert judge.judge_metric(le, 0.20)["verdict"] == "FAIL"


def test_metrics_parses_token_usage():
    # metrics() must surface real token usage from the terminal result event so the
    # value track can report a token delta, not just transcript size.
    raw = "\n".join([
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash"}]}}',
        '{"type":"result","result":"done","usage":{"input_tokens":100,"output_tokens":50,'
        '"cache_read_input_tokens":2000,"cache_creation_input_tokens":300}}',
    ])
    m = agent.metrics(raw)
    assert m["tool_calls"] == 1, m
    assert m["input_tokens"] == 100 and m["output_tokens"] == 50, m
    assert m["cache_read_tokens"] == 2000 and m["cache_creation_tokens"] == 300, m
    assert m["total_input_tokens"] == 2400, m


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"selftest OK — {len(tests)} checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

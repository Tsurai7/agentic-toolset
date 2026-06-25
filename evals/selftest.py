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
from lib import judge  # noqa: E402


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


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"selftest OK — {len(tests)} checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

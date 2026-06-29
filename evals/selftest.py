#!/usr/bin/env python3
"""Pure-logic self-tests for the harness — no agent, no judge, no tokens.

Guards the two subtle, non-LLM pieces: the pairwise order-swap mapping (which
turns raw slot picks into treatment/control verdicts and detects position bias)
and the value verdict thresholds. Runs in CI alongside lint.py.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
from lib import agent, cases, judge  # noqa: E402


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


def test_metrics_overhead_fields():
    # metrics() must also surface the overhead-instrument fields: the first turn's
    # context (prefix proxy), repriced input (input + cache_creation), and the
    # run-level cost/latency/turns from the result event.
    raw = "\n".join([
        '{"type":"assistant","message":{"usage":{"input_tokens":10,'
        '"cache_creation_input_tokens":11000,"cache_read_input_tokens":17000,'
        '"output_tokens":1},"content":[{"type":"tool_use","name":"Bash"}]}}',
        '{"type":"result","result":"done","num_turns":4,"duration_ms":12345,'
        '"total_cost_usd":0.0756,"usage":{"input_tokens":90,"output_tokens":2200,'
        '"cache_read_input_tokens":320000,"cache_creation_input_tokens":15000}}',
    ])
    m = agent.metrics(raw)
    assert m["prefix_turn1_ctx"] == 28010, m            # 10 + 11000 + 17000
    assert m["repriced_input_tokens"] == 15090, m       # 90 + 15000
    assert m["total_input_tokens"] == 335090, m         # 90 + 320000 + 15000
    assert m["cost_usd"] == 0.0756 and m["num_turns"] == 4 and m["duration_ms"] == 12345, m
    assert m["tool_calls"] == 1, m
    # Negative: with no assistant-turn usage and a bare result, the optional fields
    # are omitted (not defaulted) so a consumer can tell "absent" from "zero".
    bare = ('{"type":"result","result":"x","usage":{"input_tokens":1,"output_tokens":1,'
            '"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}')
    mb = agent.metrics(bare)
    assert "prefix_turn1_ctx" not in mb and "cost_usd" not in mb and "num_turns" not in mb, mb


def test_overhead_ratios():
    on = {"total_input_tokens": 300, "repriced_input_tokens": 15,
          "output_tokens": 20, "cost_usd": 0.08, "tool_calls": 10}
    off = {"total_input_tokens": 100, "repriced_input_tokens": 12,
           "output_tokens": 10, "cost_usd": 0.04, "tool_calls": 5}
    r = agent.overhead_ratios(on, off)
    assert r["total_input_ratio"] == 3.0, r
    assert r["cost_ratio"] == 2.0 and r["output_ratio"] == 2.0, r
    assert r["tool_calls_ratio"] == 2.0, r
    # A missing or zero OFF denominator yields None, not a crash.
    assert agent.overhead_ratios({"cost_usd": 1.0}, {})["cost_ratio"] is None


def test_overhead_verdict():
    jo = judge.judge_overhead
    # At the 1.5x boundary the easy gate passes (inclusive).
    assert jo({"total_input_ratio": 1.5, "cost_ratio": 1.5,
               "correct_on": True, "correct_off": True})["verdict"] == "PASS"
    # The 2026-06-26 easy baseline (3.93x / 2.04x) fails the gate.
    assert jo({"total_input_ratio": 3.93, "cost_ratio": 2.04,
               "correct_on": True, "correct_off": True})["verdict"] == "FAIL"
    # A correctness regression fails even when under budget.
    assert jo({"total_input_ratio": 1.2, "cost_ratio": 1.1,
               "correct_on": False, "correct_off": True})["verdict"] == "FAIL"
    # Hard-regime guard: overhead must stay <= 1.0 where the toolset should pay off.
    assert jo({"total_input_ratio": 1.2, "cost_ratio": 1.2,
               "correct_on": True, "correct_off": True},
              {"total_input_ratio": 1.3})["verdict"] == "FAIL"
    assert jo({"total_input_ratio": 1.2, "cost_ratio": 1.2,
               "correct_on": True, "correct_off": True},
              {"total_input_ratio": 0.72})["verdict"] == "PASS"


def test_cases_loader_names_bad_file():
    # BUG-22: a malformed case file must produce a legible, file-named error —
    # not a bare JSONDecodeError traceback — and must not abort the good files.
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "broken.json"
        bad.write_text('{"id": "x",,}', "utf-8")  # double comma → invalid JSON
        try:
            cases._read_case(bad)
        except cases.CaseLoadError as exc:
            assert "broken.json" in str(exc) and "invalid JSON" in str(exc), exc
        else:
            assert False, "expected CaseLoadError for malformed JSON"

        # A non-object top level (array) is rejected and still names the file.
        arr = Path(d) / "arr.json"
        arr.write_text("[1, 2, 3]", "utf-8")
        try:
            cases._read_case(arr)
        except cases.CaseLoadError as exc:
            assert "arr.json" in str(exc) and "expected a JSON object" in str(exc), exc
        else:
            assert False, "expected CaseLoadError for non-object top level"

        # A valid case round-trips unchanged.
        ok = Path(d) / "ok.json"
        ok.write_text('{"id": "ok", "rule": "r", "prompt": "p", "expect": ["e"]}', "utf-8")
        assert cases._read_case(ok)["id"] == "ok"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"selftest OK — {len(tests)} checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

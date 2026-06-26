#!/usr/bin/env python3
"""Toolset-overhead A/B — measure ON vs OFF token cost for a weak model and grade it
against the owner's ≤1.5x bar (plans/06-overhead-and-uplift.md, workstream W3).

This is the reusable runner that promotes the one-off experiment in
`evals/experiments/haiku_overhead_decomp.py`. It reuses the selftested pure helpers
`agent.metrics`, `agent.overhead_ratios`, and `judge.judge_overhead`, so the verdict
logic is guarded zero-token in `evals/selftest.py`; this file only adds the live A/B.

Dry by default: it prints the plan and exits 0 without spending tokens. Pass `--confirm`
(or `AGENTIC_EVAL_CONFIRM=1`) to actually invoke the agent CLI on each arm.

Isolation: the OFF arm uses prompt-isolation (the agent still loads the full config and
is merely told to ignore it), so this measures induced behaviour, not static-prefix
bytes. It is n=1 per cell — directional, not a verdict on the toolset's value. Each arm
is a `claude` subprocess, so it is not wrapped by the live PreToolUse shell-guard hook.
Run it from anywhere; each task builds its own throwaway scratch repo.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS))
from lib import agent, judge  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
PERCALL_TIMEOUT = 420
OFF_PREFIX = (
    "Use only the standard built-in tools and plain shell commands. Do not use any "
    "custom skills, rules, rtk, lean-ctx, ast-grep, or gitnexus. "
)


def _git_init(d: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=d)


def _make_easy():
    """A trivial lookup: list Go functions whose last return type is error (A,B,D,E=4)."""
    d = tempfile.mkdtemp(prefix="overhead-easy-")
    pkg = Path(d, "pkg")
    pkg.mkdir()
    (pkg / "a.go").write_text(
        'package pkg\nimport "errors"\n'
        'func A() error { return errors.New("x") }\n'
        'func B() (int, error) { return 0, nil }\n'
        'func C() string { return "" }\n'
        'func D() error { return nil }\n'
    )
    (pkg / "b.go").write_text(
        'package pkg\nfunc E() error { return nil }\nfunc F() int { return 1 }\n'
    )
    _git_init(d)
    task = (
        "In this repository, find every Go function whose last return type is `error` "
        "and report the list of their names plus the total count."
    )

    def correct(ans: str) -> bool:
        return "4" in ans and all(n in ans for n in ("A", "B", "D", "E"))

    return d, task, correct


def _make_hard():
    """Structural disambiguation a bare grep flails on: count call sites of the
    package-level Send (a.go, b.go, d.go = 3), excluding the same-named method, a
    method call, and the word Send in a string/comment."""
    d = tempfile.mkdtemp(prefix="overhead-hard-")
    app = Path(d, "app")
    app.mkdir()
    (app / "mailer.go").write_text("package app\nfunc Send(msg string) error { return nil }\n")
    (app / "notifier.go").write_text(
        "package app\ntype Notifier struct{}\nfunc (n Notifier) Send(x string) {}\n"
    )
    (app / "a.go").write_text('package app\nfunc useA() { _ = Send("hi") }\n')
    (app / "b.go").write_text('package app\nfunc useB(x string) { _ = Send(x) }\n')
    (app / "c.go").write_text(
        "package app\n// remember to call Send here later\n"
        'func useC(n Notifier) { n.Send("the Send report") }\n'
    )
    (app / "d.go").write_text('package app\nfunc useD() { _ = Send("z") }\n')
    _git_init(d)
    task = (
        "In this Go repository there is a package-level function `Send` and also a "
        "method `Send` on the `Notifier` type. Count ONLY the call sites that invoke "
        "the package-level function `Send` (NOT the Notifier.Send method, and NOT the "
        "word Send appearing inside strings or comments). List the files containing "
        "those call sites and give the total count."
    )

    def correct(ans: str) -> bool:
        return "3" in ans and all(f in ans for f in ("a.go", "b.go", "d.go"))

    return d, task, correct


TASKS = {"easy": _make_easy, "hard": _make_hard}


def _run_arm(cwd: str, prompt: str, model: str) -> str:
    argv = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", model, prompt,
    ]
    try:
        p = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT
        )
        return p.stdout or p.stderr
    except subprocess.TimeoutExpired:
        return '{"type":"result","result":"<TIMEOUT>","usage":{}}'


def measure_task(name: str, maker, model: str) -> dict:
    d, task, correct = maker()
    try:
        on_raw = _run_arm(d, task, model)
        off_raw = _run_arm(d, OFF_PREFIX + task, model)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    on, off = agent.metrics(on_raw), agent.metrics(off_raw)
    return {
        "task": name,
        "on": on,
        "off": off,
        "ratios": agent.overhead_ratios(on, off),
        "correct_on": bool(correct(agent.final_text(on_raw))),
        "correct_off": bool(correct(agent.final_text(off_raw))),
    }


def _regime(r: dict) -> dict:
    return {
        "total_input_ratio": r["ratios"]["total_input_ratio"],
        "cost_ratio": r["ratios"]["cost_ratio"],
        "correct_on": r["correct_on"],
        "correct_off": r["correct_off"],
    }


def _fmt(x, suffix="x"):
    return "—" if x is None else f"{x:.2f}{suffix}"


def _print_human(results: list[dict], verdict: dict) -> None:
    for r in results:
        ra = r["ratios"]
        print(f"\n== {r['task']} (correct ON={r['correct_on']} OFF={r['correct_off']}) ==")
        print(f"  total_input ON/OFF : {_fmt(ra['total_input_ratio'])}"
              f"  (repriced {_fmt(ra['repriced_input_ratio'])})")
        print(f"  cost ON/OFF        : {_fmt(ra['cost_ratio'])}")
        print(f"  output ON/OFF      : {_fmt(ra['output_ratio'])}")
        print(f"  tool_calls ON/OFF  : {_fmt(ra['tool_calls_ratio'])}")
    print(f"\nVERDICT: {verdict['verdict']}")
    for reason in verdict["reasons"]:
        print(f"  - {reason}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Toolset-overhead A/B vs the <=1.5x bar.")
    ap.add_argument("--confirm", action="store_true",
                    help="actually invoke the agent CLI (spends tokens)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--filter", choices=["easy", "hard", "all"], default="all")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    args = ap.parse_args(argv)

    confirm = args.confirm or os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"
    names = ["easy", "hard"] if args.filter == "all" else [args.filter]

    if not confirm:
        print(f"[dry-run] would run {len(names)} task(s) {names} x 2 arms (ON/OFF) on "
              f"{args.model} — this spends tokens.")
        print("Re-run with --confirm (or AGENTIC_EVAL_CONFIRM=1) to measure.")
        return 0

    results = [measure_task(n, TASKS[n], args.model) for n in names]
    easy = next((r for r in results if r["task"] == "easy"), None)
    hard = next((r for r in results if r["task"] == "hard"), None)
    verdict = judge.judge_overhead(
        _regime(easy) if easy else {},
        _regime(hard) if hard else None,
    )

    if args.json:
        print(json.dumps({"model": args.model, "results": results, "verdict": verdict}, indent=2))
    else:
        _print_human(results, verdict)
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

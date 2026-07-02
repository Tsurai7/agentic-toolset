#!/usr/bin/env python3
"""Toolset-overhead A/B — measure ON vs OFF token cost for a weak model and grade it
against the owner's ≤1.5x bar (plans/06-overhead-and-uplift.md, workstream W3).

This is the reusable runner that promotes the one-off experiment in
`evals/experiments/haiku_overhead_decomp.py`. It reuses the selftested pure helpers
`agent.metrics`, `agent.overhead_ratios`, and `judge.judge_overhead`, so the verdict
logic is guarded zero-token in `evals/selftest.py`; this file only adds the live A/B.

Dry by default: it prints the plan and exits 0 without spending tokens. Pass `--confirm`
(or `AGENTIC_EVAL_CONFIRM=1`) to actually invoke the agent CLI on each arm.

Isolation: the OFF arm runs under a rendered bare CLAUDE_CONFIG_DIR (see
`lib/render_config.render_bare_control`) — no hooks, no repo-managed permission
allow-list, no CLAUDE.md import, no MCP servers, no skills. This is a physical
ablation, not a prompt-only one: earlier, each arm was a plain `claude` subprocess
still wrapped by the live PreToolUse shell-guard hook, which mechanically enforced
the toolset's own behavior in the "OFF" arm and biased the ratio. It is n=1 per
cell — directional, not a verdict on the toolset's value. Run it from anywhere;
each task builds its own throwaway scratch repo.
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
from lib import agent, judge, render_config  # noqa: E402

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
PERCALL_TIMEOUT = 420


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


def _make_hard2():
    """Identify Stringer implementers: distinguish a `String() string` method (value or
    pointer receiver) from a wrong-signature method, a non-String method, and a
    same-named free function. Alpha + Beta implement; Gamma (wrong sig), Delta (no
    String), and the free function do not. Expected: 2 (Alpha, Beta)."""
    d = tempfile.mkdtemp(prefix="overhead-hard2-")
    pkg = Path(d, "pkg")
    pkg.mkdir()
    (pkg / "types.go").write_text(
        "package pkg\n"
        "type Alpha struct{}\n"
        'func (a Alpha) String() string { return "a" }\n'
        "type Beta struct{}\n"
        'func (b *Beta) String() string { return "b" }\n'
        "type Gamma struct{}\n"
        'func (g Gamma) String(x int) string { return "" }\n'
        "type Delta struct{}\n"
        'func (dd Delta) Other() string { return "" }\n'
        'func String() string { return "free" }\n'
    )
    _git_init(d)
    task = (
        "In this Go package, list every type that implements fmt.Stringer (i.e. has a "
        "method with the exact signature `String() string`, value or pointer receiver). "
        "Give the type names and the total count."
    )

    def correct(ans: str) -> bool:
        return "2" in ans and "Alpha" in ans and "Beta" in ans

    return d, task, correct


TASKS = {"easy": _make_easy, "hard": _make_hard, "hard2": _make_hard2}


def _run_arm(cwd: str, prompt: str, model: str, env: dict[str, str] | None = None) -> str:
    argv = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", model, prompt,
    ]
    proc_env = {**os.environ, **env} if env else None
    try:
        p = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT, env=proc_env
        )
        return p.stdout or p.stderr
    except subprocess.TimeoutExpired:
        # is_error is required — without it agent.result_error() sees a clean
        # run with result="<TIMEOUT>" instead of an error, and the phantom
        # transcript's (empty) metrics get averaged into the median as if it
        # were real data.
        return '{"type":"result","is_error":true,"subtype":"timeout","result":"<TIMEOUT>","usage":{}}'


_MEDIAN_KEYS = (
    "total_input_tokens", "repriced_input_tokens", "output_tokens",
    "cost_usd", "tool_calls", "num_turns",
)


def _median(runs: list[dict], key: str):
    vals = sorted(r.get(key) for r in runs if r.get(key) is not None)
    return vals[len(vals) // 2] if vals else None


def measure_task(name: str, maker, model: str, reps: int, off_config_dir: Path) -> dict:
    """Run a task's ON/OFF arms `reps` times; report median metrics and correctness
    rates so a single noisy run can't decide the verdict. The reported ratio is the
    ratio of medians (robust to per-run variance).

    Errored reps (timeout, auth failure, no result event) are excluded from an arm's
    medians and its correctness rate: their empty/zero metrics would otherwise be
    medianed in as if a phantom run were a real, cheap one. An arm whose every rep
    errored yields None medians and a None correctness rate, which propagates to an
    UNKNOWN verdict rather than a false PASS on a median of zeros.
    """
    on_runs, off_runs = [], []
    correct_on = correct_off = 0
    on_n = off_n = 0
    off_env = {"CLAUDE_CONFIG_DIR": str(off_config_dir)}
    for _ in range(reps):
        d, task, correct = maker()
        try:
            on_raw = _run_arm(d, task, model)
            off_raw = _run_arm(d, task, model, env=off_env)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        if agent.result_error(on_raw) is None:
            on_runs.append(agent.metrics(on_raw))
            correct_on += int(bool(correct(agent.final_text(on_raw))))
            on_n += 1
        if agent.result_error(off_raw) is None:
            off_runs.append(agent.metrics(off_raw))
            correct_off += int(bool(correct(agent.final_text(off_raw))))
            off_n += 1
    on_med = {k: _median(on_runs, k) for k in _MEDIAN_KEYS}
    off_med = {k: _median(off_runs, k) for k in _MEDIAN_KEYS}
    return {
        "task": name,
        "reps": reps,
        "ratios": agent.overhead_ratios(on_med, off_med),
        "median_turns_on": on_med["num_turns"],
        "median_turns_off": off_med["num_turns"],
        "correct_on_rate": (correct_on / on_n) if on_n else None,
        "correct_off_rate": (correct_off / off_n) if off_n else None,
    }


def _fmt(x, suffix="x"):
    return "—" if x is None else f"{x:.2f}{suffix}"


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def _worst_ratio(results: list[dict], key: str):
    """The max ratio across results, or None if ANY result is missing it.

    A missing ratio means that task's OFF-arm denominator was absent/zero — its
    true overhead is unknown, not zero. Coercing None to 0 before taking the max
    let an unmeasured task look like the cheapest one and silently pass the
    ≤1.5x gate; propagating None here lets judge_overhead grade it UNKNOWN
    instead (nonzero exit), never a false PASS.
    """
    vals = [r["ratios"][key] for r in results]
    if any(v is None for v in vals):
        return None
    return max(vals) if vals else None


def _verdict(results: list[dict], max_ratio: float = judge.OVERHEAD_EASY_MAX) -> dict:
    """A run PASSes when every task's median total-input AND cost overhead is within
    max_ratio (the owner's <=1.5x bar, applied uniformly to easy and hard tasks) and
    no task regresses correctness (ON solved less often than the bare OFF arm)."""
    worst_ti = _worst_ratio(results, "total_input_ratio")
    worst_cost = _worst_ratio(results, "cost_ratio")
    regression = any(
        r["correct_on_rate"] is not None and r["correct_off_rate"] is not None
        and r["correct_on_rate"] < r["correct_off_rate"]
        for r in results
    )
    return judge.judge_overhead(
        {"total_input_ratio": worst_ti, "cost_ratio": worst_cost,
         "correct_on": not regression, "correct_off": True},
        easy_max=max_ratio,
    )


def _print_human(results: list[dict], verdict: dict) -> None:
    for r in results:
        ra = r["ratios"]
        print(f"\n== {r['task']} (reps={r['reps']}; correct ON={_pct(r['correct_on_rate'])} "
              f"OFF={_pct(r['correct_off_rate'])}) ==")
        print(f"  median total_input ON/OFF : {_fmt(ra['total_input_ratio'])}"
              f"  (repriced {_fmt(ra['repriced_input_ratio'])})")
        print(f"  median cost ON/OFF        : {_fmt(ra['cost_ratio'])}")
        print(f"  median turns ON/OFF       : {r['median_turns_on']} / {r['median_turns_off']}")
    print(f"\nVERDICT: {verdict['verdict']}")
    for reason in verdict["reasons"]:
        print(f"  - {reason}")


def _select(flt: str) -> list[str]:
    if flt == "all":
        return list(TASKS)
    if flt == "hard":
        return [n for n in TASKS if n.startswith("hard")]
    if flt == "easy":
        return ["easy"]
    return [flt] if flt in TASKS else []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Toolset-overhead A/B vs the <=1.5x bar.")
    ap.add_argument("--confirm", action="store_true",
                    help="actually invoke the agent CLI (spends tokens)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--filter", default="all",
                    help="all | easy | hard (all hard*) | a task name")
    ap.add_argument("--reps", type=int, default=1,
                    help="repetitions per task; the median is reported")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    args = ap.parse_args(argv)

    confirm = args.confirm or os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"
    names = _select(args.filter)
    if not names:
        print(f"no tasks match --filter {args.filter!r} (have: {', '.join(TASKS)})")
        return 2

    if not confirm:
        print(f"[dry-run] would run {len(names)} task(s) {names} x 2 arms x {args.reps} "
              f"rep(s) on {args.model} — this spends tokens.")
        print("OFF arm isolation: a rendered bare CLAUDE_CONFIG_DIR "
              "(lib/render_config.render_bare_control) — no hooks, no MCP, no skills.")
        print("Re-run with --confirm (or AGENTIC_EVAL_CONFIRM=1) to measure.")
        return 0

    with tempfile.TemporaryDirectory(prefix="overhead-off-config-") as tmp:
        off_config_dir = render_config.render_bare_control(Path(tmp) / "off-config")
        results = [
            measure_task(n, TASKS[n], args.model, args.reps, off_config_dir) for n in names
        ]
    verdict = _verdict(results)

    if args.json:
        print(json.dumps({"model": args.model, "reps": args.reps,
                          "results": results, "verdict": verdict}, indent=2))
    else:
        _print_human(results, verdict)
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

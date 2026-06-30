#!/usr/bin/env python3
"""SWE benchmark — config A/B across a difficulty ladder and model tiers.

Extends the 3-task `evals/overhead.py` runner into a 5-tier ladder
(trivial → very_hard, mixing one-symbol lookups, structural disambiguation, and
multi-file edit/build/test tasks) and sweeps multiple models (Haiku / Sonnet /
Opus) in one matrix. This is the instrument for testing whether a config change
actually helps where it matters: the weak-model + trivial-task *over-tooling*
regime that `plans/06-overhead-and-uplift.md` measured (Haiku 3.15× on easy), and
the hard regime where structural tooling pays off (0.65×).

Two arms per cell:
  ON  — the full agentic-cfg environment (skills, hooks, MCP, prefix)
  OFF — prompt-isolated bare agent (told to ignore the custom config/tools)

Correctness is DETERMINISTIC. A task is either:
  ("text",  fn(answer)->bool)              — a lookup; checks the final answer
  ("state", (argv, ok_returncode))         — an edit; runs a command in the repo
                                             after the arm and checks its exit code

Dry by default — prints the matrix plan and spends NO tokens. Pass --confirm
(or AGENTIC_EVAL_CONFIRM=1) to actually invoke the agent CLI per cell. Run the
zero-token harness self-test with --selftest (wired into bin/ci-check.sh): it
builds each task, asserts the check REJECTS the initial/incorrect state and
ACCEPTS the known solution, so the ladder is validated without an LLM.
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
from lib import agent  # noqa: E402

MODEL_ALIASES = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}  # claude CLI resolves these
PERCALL_TIMEOUT = 600
OFF_PREFIX = (
    "Use only the standard built-in tools and plain shell commands. Do not use any "
    "custom skills, rules, rtk, lean-ctx, ast-grep, or gitnexus. "
)


def _git_init(d: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=d, check=False)


# --- the difficulty ladder ---------------------------------------------------
# Each maker returns (dir, prompt, check). Edit tasks also expose _solution(dir)
# (applied only by the self-test) so the check can be proven to discriminate.


def _make_trivial():
    """TRIVIAL lookup — one symbol, one file. A bare read answers it; the toolset
    must NOT orient/graph for this (the over-tooling failure mode)."""
    d = tempfile.mkdtemp(prefix="swe-trivial-")
    Path(d, "calc.go").write_text(
        "package calc\n"
        "func Divide(a, b int) (int, error) { return a / b, nil }\n"
    )
    _git_init(d)
    task = "In calc.go, what is the full return type signature of the function `Divide`? Answer concisely."
    return d, task, ("text", lambda ans: "int" in ans and "error" in ans)


def _make_easy():
    """EASY lookup — scan a small package for a pattern (4 funcs return error)."""
    d = tempfile.mkdtemp(prefix="swe-easy-")
    pkg = Path(d, "pkg")
    pkg.mkdir()
    (pkg / "a.go").write_text(
        'package pkg\nimport "errors"\n'
        'func A() error { return errors.New("x") }\n'
        "func B() (int, error) { return 0, nil }\n"
        'func C() string { return "" }\n'
        "func D() error { return nil }\n"
    )
    (pkg / "b.go").write_text("package pkg\nfunc E() error { return nil }\nfunc F() int { return 1 }\n")
    _git_init(d)
    task = "Find every Go function whose last return type is `error` and report their names plus the total count."
    return d, task, ("text", lambda ans: "4" in ans and all(n in ans for n in ("A", "B", "D", "E")))


def _make_medium():
    """MEDIUM edit — a single-file off-by-one bug; a test pins the behaviour.
    Requires reading + an edit, verified by `go test`."""
    d = tempfile.mkdtemp(prefix="swe-medium-")
    Path(d, "go.mod").write_text("module sweb\n\ngo 1.21\n")
    Path(d, "sum.go").write_text(
        "package sweb\n"
        "// Sum returns the total of xs.\n"
        "func Sum(xs []int) int {\n"
        "\ttotal := 0\n"
        "\tfor i := 1; i < len(xs); i++ { total += xs[i] }\n"  # off-by-one: skips xs[0]
        "\treturn total\n}\n"
    )
    Path(d, "sum_test.go").write_text(
        "package sweb\nimport \"testing\"\n"
        "func TestSum(t *testing.T) { if Sum([]int{1, 2, 3}) != 6 { t.Fatalf(\"got %d want 6\", Sum([]int{1,2,3})) } }\n"
    )
    _git_init(d)
    task = "`go test ./...` fails in this repo. Find and fix the bug so the test passes. Keep the change minimal."
    return d, task, ("state", (["go", "test", "./..."], 0))


def _solution_medium(d: str) -> None:
    p = Path(d, "sum.go")
    p.write_text(p.read_text().replace("for i := 1;", "for i := 0;"))


def _make_hard():
    """HARD structural disambiguation — count call sites of the package-level
    Send (3), excluding a same-named method, strings, and comments. A bare grep
    flails; structural tooling wins. Text check."""
    d = tempfile.mkdtemp(prefix="swe-hard-")
    app = Path(d, "app")
    app.mkdir()
    (app / "mailer.go").write_text("package app\nfunc Send(msg string) error { return nil }\n")
    (app / "notifier.go").write_text("package app\ntype Notifier struct{}\nfunc (n Notifier) Send(x string) {}\n")
    (app / "a.go").write_text('package app\nfunc useA() { _ = Send("hi") }\n')
    (app / "b.go").write_text("package app\nfunc useB(x string) { _ = Send(x) }\n")
    (app / "c.go").write_text(
        "package app\n// remember to call Send here later\n"
        'func useC(n Notifier) { n.Send("the Send report") }\n'
    )
    (app / "d.go").write_text('package app\nfunc useD() { _ = Send("z") }\n')
    _git_init(d)
    task = (
        "Count ONLY the call sites that invoke the package-level function `Send` "
        "(NOT the Notifier.Send method, and NOT the word Send in strings or comments). "
        "List the files and give the total count."
    )
    return d, task, ("text", lambda ans: "3" in ans and all(f in ans for f in ("a.go", "b.go", "d.go")))


def _make_very_hard():
    """VERY HARD multi-file refactor — a half-applied signature change: Discount
    grew a `rate` parameter but two of three callers weren't updated, so the
    package neither compiles nor passes its test. Requires impact analysis (find
    every caller) + a correct fix. Verified by `go test`."""
    d = tempfile.mkdtemp(prefix="swe-vhard-")
    Path(d, "go.mod").write_text("module sweb\n\ngo 1.21\n")
    Path(d, "discount.go").write_text(
        "package sweb\n"
        "// Discount applies `rate` (e.g. 0.10 for 10%) to amount and returns the price paid.\n"
        "func Discount(amount int, rate float64) int { return amount - int(float64(amount)*rate) }\n"
    )
    # caller 1 — updated correctly already
    Path(d, "cart.go").write_text("package sweb\nfunc CartTotal() int { return Discount(100, 0.10) }\n")
    # callers 2 & 3 — NOT updated: still call the old 1-arg form -> compile error
    Path(d, "checkout.go").write_text("package sweb\nfunc Checkout() int { return Discount(200) }\n")
    Path(d, "invoice.go").write_text("package sweb\nfunc Invoice() int { return Discount(50) }\n")
    Path(d, "discount_test.go").write_text(
        "package sweb\nimport \"testing\"\n"
        "func TestAll(t *testing.T) {\n"
        "\tif CartTotal() != 90 { t.Fatalf(\"cart %d\", CartTotal()) }\n"
        "\tif Checkout() != 180 { t.Fatalf(\"checkout %d\", Checkout()) }\n"  # expects 10% off 200
        "\tif Invoice() != 45 { t.Fatalf(\"invoice %d\", Invoice()) }\n"  # expects 10% off 50
        "}\n"
    )
    _git_init(d)
    task = (
        "A refactor added a `rate float64` parameter to `Discount` but is only half "
        "applied — the package does not compile and `go test ./...` fails. Find EVERY "
        "caller of `Discount`, finish the refactor so all callers pass a 0.10 rate, and "
        "make the tests pass. Do not change Discount's new signature or the test."
    )
    return d, task, ("state", (["go", "test", "./..."], 0))


def _solution_very_hard(d: str) -> None:
    Path(d, "checkout.go").write_text("package sweb\nfunc Checkout() int { return Discount(200, 0.10) }\n")
    Path(d, "invoice.go").write_text("package sweb\nfunc Invoice() int { return Discount(50, 0.10) }\n")


TASKS = {
    "trivial": _make_trivial,
    "easy": _make_easy,
    "medium": _make_medium,
    "hard": _make_hard,
    "very_hard": _make_very_hard,
}
TIERS = list(TASKS)
_SOLUTIONS = {"medium": _solution_medium, "very_hard": _solution_very_hard}


def _run_arm(cwd: str, prompt: str, model: str) -> str:
    argv = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", model, prompt,
    ]
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT)
        return p.stdout or p.stderr
    except subprocess.TimeoutExpired:
        return '{"type":"result","result":"<TIMEOUT>","usage":{}}'


def _check(spec, answer: str, cwd: str) -> bool:
    kind, payload = spec
    if kind == "text":
        return bool(payload(answer))
    if kind == "state":
        argv, ok = payload
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        return p.returncode == ok
    return False


def measure_cell(task_name: str, model: str, reps: int) -> dict:
    """Run one (task, model) cell `reps` times, both arms; report median metrics
    and correctness rates so a single noisy run can't decide the verdict."""
    maker = TASKS[task_name]
    on_runs, off_runs = [], []
    correct_on = correct_off = 0
    for _ in range(reps):
        d, task, spec = maker()
        try:
            on_raw = _run_arm(d, task, model)
            on_ok = _check(spec, agent.final_text(on_raw), d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        d2, task2, spec2 = maker()
        try:
            off_raw = _run_arm(d2, OFF_PREFIX + task2, model)
            off_ok = _check(spec2, agent.final_text(off_raw), d2)
        finally:
            shutil.rmtree(d2, ignore_errors=True)
        on_runs.append(agent.metrics(on_raw))
        off_runs.append(agent.metrics(off_raw))
        correct_on += int(on_ok)
        correct_off += int(off_ok)

    def med(runs, k):
        vals = sorted(r.get(k) for r in runs if r.get(k) is not None)
        return vals[len(vals) // 2] if vals else None

    keys = ("total_input_tokens", "repriced_input_tokens", "output_tokens", "cost_usd", "tool_calls", "num_turns")
    on_med = {k: med(on_runs, k) for k in keys}
    off_med = {k: med(off_runs, k) for k in keys}
    return {
        "task": task_name,
        "model": model,
        "reps": reps,
        "ratios": agent.overhead_ratios(on_med, off_med),
        "turns_on": on_med["num_turns"],
        "turns_off": off_med["num_turns"],
        "correct_on_rate": correct_on / reps,
        "correct_off_rate": correct_off / reps,
    }


def selftest() -> int:
    """Zero-token validation: every task's check must REJECT the initial/wrong
    state and ACCEPT the known solution, so the ladder discriminates correctly."""
    checks = 0
    for name, maker in TASKS.items():
        d, _task, spec = maker()
        try:
            kind, _ = spec
            if kind == "text":
                # text checks discriminate a correct vs an empty answer
                good = {
                    "trivial": "(int, error)", "easy": "A, B, D, E — total 4",
                    "hard": "a.go b.go d.go — 3 call sites",
                }[name]
                assert _check(spec, good, d), f"{name}: text check rejected the correct answer"
                assert not _check(spec, "no idea", d), f"{name}: text check accepted a wrong answer"
                checks += 2
            else:  # state: initial repo must FAIL; the known fix must PASS
                assert not _check(spec, "", d), f"{name}: initial state unexpectedly passes (task is pre-solved)"
                _SOLUTIONS[name](d)
                assert _check(spec, "", d), f"{name}: known solution does not pass the check"
                checks += 2
        finally:
            shutil.rmtree(d, ignore_errors=True)
        print(f"  ok  {name}")
    print(f"swe_bench selftest OK — {len(TASKS)} tasks, {checks} checks.")
    return 0


def _fmt(x, suffix="x"):
    return "—" if x is None else f"{x:.2f}{suffix}"


def _print_matrix(cells: list[dict]) -> None:
    print(f"\n{'task':<10} {'model':<8} {'in ON/OFF':>10} {'cost':>7} {'turns':>9} {'correct ON/OFF':>15}")
    print("-" * 64)
    for c in cells:
        ra = c["ratios"]
        turns = f"{c['turns_on']}/{c['turns_off']}"
        correct = f"{c['correct_on_rate']:.0%}/{c['correct_off_rate']:.0%}"
        print(f"{c['task']:<10} {c['model']:<8} {_fmt(ra['total_input_ratio']):>10} "
              f"{_fmt(ra['cost_ratio']):>7} {turns:>9} {correct:>15}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SWE benchmark — config A/B across difficulty tiers and models.")
    ap.add_argument("--confirm", action="store_true", help="actually invoke the agent CLI (spends tokens)")
    ap.add_argument("--models", default="haiku,sonnet,opus", help="comma-separated model aliases/ids")
    ap.add_argument("--filter", default="all", help="all | a tier name (trivial|easy|medium|hard|very_hard)")
    ap.add_argument("--reps", type=int, default=1, help="repetitions per cell; the median is reported")
    ap.add_argument("--selftest", action="store_true", help="zero-token validation of the task checks")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    tasks = TIERS if args.filter == "all" else [args.filter]
    if any(t not in TASKS for t in tasks):
        print(f"unknown task in {tasks}; choose from {TIERS}", file=sys.stderr)
        return 2
    models = [MODEL_ALIASES.get(m.strip(), m.strip()) for m in args.models.split(",") if m.strip()]

    confirm = args.confirm or os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"
    if not confirm:
        print("DRY-RUN — no tokens spent. Matrix that WOULD run (pass --confirm to execute):")
        print(f"  models : {models}")
        print(f"  tasks  : {tasks}")
        print(f"  arms   : ON (full config) vs OFF (prompt-isolated)")
        print(f"  reps   : {args.reps}  →  {len(models) * len(tasks) * 2 * args.reps} agent invocations")
        print("\nValidate the task checks now, free:  python3 evals/swe_bench.py --selftest")
        return 0

    cells = [measure_cell(t, m, args.reps) for m in models for t in tasks]
    if args.json:
        json.dump(cells, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_matrix(cells)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

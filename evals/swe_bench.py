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


def _make_expert():
    """EXPERT correctness probe — a subtle TWO-part bug: `MergeOverlapping` neither
    sorts its input nor treats *touching* intervals ([1,2],[2,3]) as mergeable. The
    obvious one-character fix (`<` → `<=`) still fails the unsorted case, so passing
    requires reasoning about the real invariant (sort, then merge inclusively), not
    pattern-matching a single operator. The difficulty is intrinsic reasoning, not
    search — it is built to probe whether the config lifts weak-model *correctness*.
    Whether bare-weak actually fails it is an OPEN live measurement, not an assertion
    (the design doc says so explicitly). Verified by `go test`."""
    d = tempfile.mkdtemp(prefix="swe-expert-")
    Path(d, "go.mod").write_text("module sweb\n\ngo 1.21\n")
    Path(d, "merge.go").write_text(
        "package sweb\n"
        "// MergeOverlapping merges overlapping or touching intervals and returns them\n"
        "// sorted by start. E.g. [[1,3],[2,5],[5,6]] -> [[1,6]]. It is currently buggy.\n"
        "func MergeOverlapping(in [][2]int) [][2]int {\n"
        "\tvar out [][2]int\n"
        "\tfor _, iv := range in {\n"
        "\t\tif n := len(out); n > 0 && iv[0] < out[n-1][1] {\n"  # bug: needs a prior sort, and <= for touching
        "\t\t\tif iv[1] > out[n-1][1] {\n"
        "\t\t\t\tout[n-1][1] = iv[1]\n"
        "\t\t\t}\n"
        "\t\t} else {\n"
        "\t\t\tout = append(out, iv)\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn out\n}\n"
    )
    Path(d, "merge_test.go").write_text(
        "package sweb\n"
        'import (\n\t"fmt"\n\t"testing"\n)\n'
        "func TestMergeOverlapping(t *testing.T) {\n"
        "\tcases := []struct{ in, want [][2]int }{\n"
        "\t\t{[][2]int{{1, 3}, {6, 9}, {2, 5}, {5, 6}}, [][2]int{{1, 9}}},\n"  # unsorted + touching -> all merge
        "\t\t{[][2]int{{1, 2}, {4, 5}}, [][2]int{{1, 2}, {4, 5}}},\n"  # disjoint -> unchanged (guards over-merge)
        "\t}\n"
        "\tfor _, c := range cases {\n"
        "\t\tif got := MergeOverlapping(c.in); fmt.Sprint(got) != fmt.Sprint(c.want) {\n"
        "\t\t\tt.Fatalf(\"MergeOverlapping(%v) = %v, want %v\", c.in, got, c.want)\n"
        "\t\t}\n"
        "\t}\n}\n"
    )
    _git_init(d)
    task = (
        "`go test ./...` fails. `MergeOverlapping` should merge overlapping or touching "
        "intervals and return them sorted by start, but it is buggy. Fix it so the tests "
        "pass. Do not change the test."
    )
    return d, task, ("state", (["go", "test", "./..."], 0))


def _solution_expert(d: str) -> None:
    Path(d, "merge.go").write_text(
        "package sweb\n"
        'import "sort"\n'
        "func MergeOverlapping(in [][2]int) [][2]int {\n"
        "\ts := make([][2]int, len(in))\n"
        "\tcopy(s, in)\n"
        "\tsort.Slice(s, func(i, j int) bool { return s[i][0] < s[j][0] })\n"
        "\tvar out [][2]int\n"
        "\tfor _, iv := range s {\n"
        "\t\tif n := len(out); n > 0 && iv[0] <= out[n-1][1] {\n"
        "\t\t\tif iv[1] > out[n-1][1] {\n"
        "\t\t\t\tout[n-1][1] = iv[1]\n"
        "\t\t\t}\n"
        "\t\t} else {\n"
        "\t\t\tout = append(out, iv)\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn out\n}\n"
    )


TASKS = {
    "trivial": _make_trivial,
    "easy": _make_easy,
    "medium": _make_medium,
    "hard": _make_hard,
    "very_hard": _make_very_hard,
    "expert": _make_expert,
}
TIERS = list(TASKS)
_SOLUTIONS = {
    "medium": _solution_medium,
    "very_hard": _solution_very_hard,
    "expert": _solution_expert,
}


# Reasoning-effort level passed to `claude -p --effort` (e.g. low|medium|high).
# None = the CLI's own default. Set once from --effort so an effort-routing
# experiment varies the agent's thinking budget while holding model + task fixed.
EFFORT = None


def _arm_argv(model: str, prompt: str) -> list:
    argv = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", model,
    ]
    if EFFORT:
        argv += ["--effort", EFFORT]
    argv.append(prompt)
    return argv


def _run_arm(cwd: str, prompt: str, model: str) -> str:
    argv = _arm_argv(model, prompt)
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT)
        return p.stdout or p.stderr
    except subprocess.TimeoutExpired:
        return '{"type":"result","is_error":true,"subtype":"timeout","result":"<TIMEOUT>","usage":{}}'


def _check(spec, answer: str, cwd: str) -> bool:
    kind, payload = spec
    if kind == "text":
        return bool(payload(answer))
    if kind == "state":
        argv, ok = payload
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
        return p.returncode == ok
    return False


def _ratio_spread(on_runs: list, off_runs: list, key: str):
    """Per-rep paired ratios `on[i][key] / off[i][key]`, as `(min, median, max)`.

    Reporting only the median (see `measure_cell`) hides how noisy a cell is — the
    live run that motivated this saw an `easy` cell swing 2.62× → 1.31× across reps.
    Surfacing the spread lets a reader judge whether the median is trustworthy.
    Returns None when no rep has both arms present (a zero/absent OFF denominator
    is skipped, never divided by).
    """
    vals = sorted(
        o[key] / f[key]
        for o, f in zip(on_runs, off_runs)
        if o.get(key) is not None and f.get(key)
    )
    if not vals:
        return None
    return (vals[0], vals[len(vals) // 2], vals[-1])


def measure_cell(task_name: str, model: str, reps: int) -> dict:
    """Run one (task, model) cell `reps` times, both arms; report median metrics
    and correctness rates so a single noisy run can't decide the verdict."""
    maker = TASKS[task_name]
    on_runs, off_runs = [], []
    on_ok = off_ok = 0          # passes, counted only over non-errored reps
    on_n = off_n = 0            # non-errored reps per arm
    on_err = off_err = None     # last error string seen on each arm, if any

    def run_arm(prompt_prefix, accum_runs):
        nonlocal_err = None
        d, task, spec = maker()
        try:
            raw = _run_arm(d, prompt_prefix + task, model)
            nonlocal_err = agent.result_error(raw)
            ok = None if nonlocal_err else _check(spec, agent.final_text(raw), d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        accum_runs.append(agent.metrics(raw))
        return ok, nonlocal_err

    for _ in range(reps):
        ok, err = run_arm("", on_runs)
        if err:
            on_err = err
        else:
            on_ok += int(ok); on_n += 1
        ok, err = run_arm(OFF_PREFIX, off_runs)
        if err:
            off_err = err
        else:
            off_ok += int(ok); off_n += 1

    def med(runs, k):
        vals = sorted(r.get(k) for r in runs if r.get(k) is not None)
        return vals[len(vals) // 2] if vals else None

    keys = ("total_input_tokens", "repriced_input_tokens", "output_tokens", "cost_usd", "tool_calls", "num_turns")
    on_med = {k: med(on_runs, k) for k in keys}
    off_med = {k: med(off_runs, k) for k in keys}
    return {
        "task": task_name,
        "model": model,
        "effort": EFFORT,
        "reps": reps,
        # Per-arm absolute medians, so an effort-routing experiment can compare the
        # same arm across two effort runs (the ON/OFF ratio only measures config).
        "abs_on": on_med,
        "abs_off": off_med,
        "ratios": agent.overhead_ratios(on_med, off_med),
        "spread": {
            "total_input": _ratio_spread(on_runs, off_runs, "total_input_tokens"),
            "cost": _ratio_spread(on_runs, off_runs, "cost_usd"),
        },
        "turns_on": on_med["num_turns"],
        "turns_off": off_med["num_turns"],
        "correct_on_rate": (on_ok / on_n) if on_n else None,
        "correct_off_rate": (off_ok / off_n) if off_n else None,
        "on_error": on_err,
        "off_error": off_err,
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
    # The error-detection guard: a failed/auth-errored launch must NOT be recorded
    # as a real run, or the matrix shows phantom 0%-correct cells (see result_error).
    auth_fail = '{"type":"result","is_error":true,"result":"Not logged in · Please run /login"}'
    timeout = '{"type":"result","is_error":true,"subtype":"timeout","result":"<TIMEOUT>"}'
    clean = '{"type":"result","is_error":false,"result":"(int, error)","num_turns":1}'
    assert agent.result_error(auth_fail), "result_error missed an auth failure"
    assert agent.result_error(timeout), "result_error missed a timeout"
    assert agent.result_error("not json at all") == "no result event (agent produced no usable output)"
    assert agent.result_error(clean) is None, "result_error flagged a clean run"
    print("  ok  result_error discriminates auth/timeout/empty from a clean run")
    # The per-rep spread must report the actual min/median/max and never divide by a
    # zero/absent OFF denominator (else a noisy cell looks as clean as a stable one).
    on = [{"total_input_tokens": 200}, {"total_input_tokens": 400}, {"total_input_tokens": 300}]
    off = [{"total_input_tokens": 100}, {"total_input_tokens": 100}, {"total_input_tokens": 100}]
    assert _ratio_spread(on, off, "total_input_tokens") == (2.0, 3.0, 4.0)
    assert _ratio_spread([{"total_input_tokens": 5}], [{"total_input_tokens": 0}], "total_input_tokens") is None
    print("  ok  _ratio_spread reports per-rep min/median/max and skips zero denominators")
    # The --effort axis must reach the launch argv only when set, or an effort-routing
    # experiment would silently run at the CLI default and measure nothing.
    global EFFORT
    saved = EFFORT
    EFFORT = None
    assert "--effort" not in _arm_argv("haiku", "p"), "effort leaked into argv when unset"
    EFFORT = "low"
    av = _arm_argv("haiku", "p")
    assert av[-1] == "p", "prompt must stay last in argv"
    assert "--effort" in av and av[av.index("--effort") + 1] == "low", "effort not threaded into argv"
    EFFORT = saved
    print("  ok  _arm_argv threads --effort only when set")
    print(f"swe_bench selftest OK — {len(TASKS)} tasks, {checks} checks + error-guard + spread + effort.")
    return 0


def _fmt(x, suffix="x"):
    return "—" if x is None else f"{x:.2f}{suffix}"


_MATRIX_HEADER = (
    f"\n{'task':<10} {'model':<8} {'in ON/OFF':>10} {'cost':>7} {'turns':>9} {'correct ON/OFF':>15}"
    f"\n{'-' * 64}"
)


def _pct(x):
    return "NA" if x is None else f"{x:.0%}"


def _matrix_row(c: dict) -> str:
    ra = c["ratios"]
    turns = f"{c['turns_on']}/{c['turns_off']}"
    if c.get("on_error") or c.get("off_error"):
        msg = c.get("on_error") or c.get("off_error")
        return f"{c['task']:<10} {c['model']:<8} {'ERR':>10}  {str(msg)[:38]}"
    correct = f"{_pct(c['correct_on_rate'])}/{_pct(c['correct_off_rate'])}"
    row = (f"{c['task']:<10} {c['model']:<8} {_fmt(ra['total_input_ratio']):>10} "
           f"{_fmt(ra['cost_ratio']):>7} {turns:>9} {correct:>15}")
    sp = (c.get("spread") or {}).get("total_input")
    if c.get("reps", 1) > 1 and sp:  # show the per-rep noise band behind the median
        row += f"  in[{sp[0]:.2f}–{sp[2]:.2f}]"
    return row


def _print_matrix(cells: list[dict]) -> None:
    print(_MATRIX_HEADER)
    for c in cells:
        print(_matrix_row(c))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SWE benchmark — config A/B across difficulty tiers and models.")
    ap.add_argument("--confirm", action="store_true", help="actually invoke the agent CLI (spends tokens)")
    ap.add_argument("--models", default="haiku,sonnet,opus", help="comma-separated model aliases/ids")
    ap.add_argument("--filter", default="all", help="all | a tier name (trivial|easy|medium|hard|very_hard)")
    ap.add_argument("--reps", type=int, default=1, help="repetitions per cell; the median is reported")
    ap.add_argument("--effort", default=None,
                    help="reasoning effort for `claude -p --effort` (e.g. low|medium|high); default = CLI default")
    ap.add_argument("--selftest", action="store_true", help="zero-token validation of the task checks")
    ap.add_argument("--json", action="store_true", help="emit raw JSON")
    ap.add_argument("--out", default=None, help="append each completed cell as a JSON line (crash-resilient)")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    global EFFORT
    EFFORT = args.effort

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

    # Run incrementally so a long matrix is observable mid-run and survives a kill:
    # each cell prints as it finishes and is appended to --out (if given) before the next starts.
    print(_MATRIX_HEADER, flush=True)
    cells = []
    for m in models:
        for t in tasks:
            c = measure_cell(t, m, args.reps)
            cells.append(c)
            print(_matrix_row(c), flush=True)
            if args.out:
                with open(args.out, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(c) + "\n")
            # Fail fast on a systemic launch failure (e.g. auth): if the very first
            # cell errored on BOTH arms, every later cell will too — don't grind
            # through a matrix of phantom data.
            if len(cells) == 1 and c.get("on_error") and c.get("off_error"):
                print(f"\nAborting: the agent CLI failed to run — {c['on_error']}\n"
                      "Both arms errored on the first cell, so this is systemic (not a task failure).\n"
                      "Most likely the nested `claude` could not authenticate. Run from a shell where\n"
                      "`claude -p \"hi\"` works (a fresh login, or export CLAUDE_CODE_OAUTH_TOKEN / "
                      "ANTHROPIC_API_KEY).", file=sys.stderr)
                return 1
    if args.json:
        json.dump(cells, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

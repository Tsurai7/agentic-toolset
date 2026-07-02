#!/usr/bin/env python3
"""SWE benchmark — config A/B across a difficulty ladder and model tiers.

Extends the 3-task `evals/overhead.py` runner into a 5-tier ladder
(trivial → very_hard, mixing one-symbol lookups, structural disambiguation, and
multi-file edit/build/test tasks) and sweeps multiple models (Haiku / Sonnet /
Opus) in one matrix. This is the instrument for testing whether a config change
actually helps where it matters: the weak-model + trivial-task *over-tooling*
regime that `plans/06-overhead-and-uplift.md` measured (Haiku 3.15× on easy), and
the hard regime where structural tooling pays off (0.65×).

Two modes:

  legacy (default, `--arms` unset) — two arms per cell:
    ON  — the full agentic-cfg environment (skills, hooks, MCP, prefix)
    OFF — a rendered bare CLAUDE_CONFIG_DIR (see lib/render_config.render_bare_control):
          no hooks, no repo-managed permission allow-list, no CLAUDE.md import, no
          MCP servers, no skills. A physical ablation, not a prompt-only one — each
          arm used to be a plain `claude` subprocess still wrapped by the live
          PreToolUse shell-guard hook, which mechanically enforced the toolset's own
          behavior in the "OFF" arm and biased the ratio.

  arms (`--arms bare,full,no-leanctx,no-gitnexus,no-shellguard`) — an N-way sweep,
    each arm an isolated CLAUDE_CONFIG_DIR (see lib/render_config.render_full_variant),
    never the live ~/.claude. Reports absolute per-arm medians (no baked-in ratio),
    including duration_ms, so a reader can compare any two arms directly.

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
from lib import agent, render_config  # noqa: E402

MODEL_ALIASES = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}  # claude CLI resolves these
PERCALL_TIMEOUT = 600
ARM_NAMES = ("bare", "full", "no-leanctx", "no-gitnexus", "no-shellguard")


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


def _arm_argv(model: str, prompt: str, extra_argv: list | None = None) -> list:
    """Build the `claude -p` argv. `extra_argv` (arms mode only) is spliced in
    before the trailing prompt — e.g. `--mcp-config <path> --strict-mcp-config`
    for an arm that carries its own MCP server set (see render_config.
    render_full_variant). Legacy callers never pass it, so legacy argv is
    unchanged (AC 5)."""
    argv = [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", model,
    ]
    if EFFORT:
        argv += ["--effort", EFFORT]
    if extra_argv:
        argv += extra_argv
    argv.append(prompt)
    return argv


def _run_arm(cwd: str, prompt: str, model: str, env: dict[str, str] | None = None,
             extra_argv: list | None = None) -> str:
    argv = _arm_argv(model, prompt, extra_argv=extra_argv)
    proc_env = {**os.environ, **env} if env else None
    try:
        p = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT, env=proc_env
        )
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


def _abs_spread(runs: list, key: str):
    """Per-rep `(min, median, max)` of a single arm's own metric across reps —
    the arms-mode counterpart of `_ratio_spread` for a metric that has no
    paired denominator to divide by (there is no single "off" in an N-way
    sweep). Same purpose: surface how noisy one arm's median is. Returns None
    when no rep has the key."""
    vals = sorted(r[key] for r in runs if r.get(key) is not None)
    if not vals:
        return None
    return (vals[0], vals[len(vals) // 2], vals[-1])


def _run_arm_reps(task_name: str, model: str, reps: int, env: dict[str, str] | None,
                   extra_argv: list | None = None):
    """Run one arm of one (task, model) cell `reps` times. Returns
    (runs, raw_runs, ok_count, n, last_error): `runs` holds only non-errored
    reps' metrics (feeds medians/spread — see measure_cell's docstring for why
    an errored rep must never be medianed as if it were a real, cheap run);
    `raw_runs` holds every rep tagged `is_error`, for the crash-resilient raw
    dump. Shared by measure_cell (legacy ON/OFF, called twice) and
    measure_cell_arms (N-way, called once per arm) so the per-rep loop is
    written once."""
    maker = TASKS[task_name]
    runs, raw_runs = [], []
    ok_count = n = 0
    last_err = None
    for _ in range(reps):
        d, task, spec = maker()
        try:
            raw = _run_arm(d, task, model, env=env, extra_argv=extra_argv)
            err = agent.result_error(raw)
            ok = None if err else _check(spec, agent.final_text(raw), d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        m = agent.metrics(raw)
        raw_runs.append({**m, "is_error": bool(err)})
        if err:
            last_err = err
        else:
            runs.append(m)
            ok_count += int(ok)
            n += 1
    return runs, raw_runs, ok_count, n, last_err


def _median(runs: list, keys: tuple) -> dict:
    def med(k):
        vals = sorted(r.get(k) for r in runs if r.get(k) is not None)
        return vals[len(vals) // 2] if vals else None
    return {k: med(k) for k in keys}


_LEGACY_MEDIAN_KEYS = (
    "total_input_tokens", "repriced_input_tokens", "output_tokens", "cost_usd", "tool_calls", "num_turns",
)
# Arms mode extends the legacy median keys with duration_ms (change 2) — the
# user's "speed" column, already captured by agent.metrics() but never medianed
# or printed before this.
ARMS_MEDIAN_KEYS = _LEGACY_MEDIAN_KEYS + ("duration_ms",)


def measure_cell(task_name: str, model: str, reps: int, off_config_dir: Path) -> dict:
    """Run one (task, model) cell `reps` times, both arms; report median metrics
    and correctness rates so a single noisy run can't decide the verdict."""
    off_env = {"CLAUDE_CONFIG_DIR": str(off_config_dir)}
    on_runs, on_raw_runs, on_ok, on_n, on_err = _run_arm_reps(task_name, model, reps, None)
    off_runs, off_raw_runs, off_ok, off_n, off_err = _run_arm_reps(task_name, model, reps, off_env)

    on_med = _median(on_runs, _LEGACY_MEDIAN_KEYS)
    off_med = _median(off_runs, _LEGACY_MEDIAN_KEYS)
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
        "raw_runs_on": on_raw_runs,
        "raw_runs_off": off_raw_runs,
    }


def _render_arm(name: str, workdir: Path) -> dict:
    """Render one named arm into an isolated CLAUDE_CONFIG_DIR under `workdir`
    and return {"env": {"CLAUDE_CONFIG_DIR": ...}, "extra_argv": [...] | []}.
    `bare` is the existing zero-skill/zero-hook/zero-MCP control
    (render_bare_control); every other arm is a `render_full_variant` isolated
    render (never the live ~/.claude — see that function's docstring), minus
    the tool(s) its name ablates. When the arm carries an mcp_config, it is
    passed via `--mcp-config` plus `--strict-mcp-config` (confirmed present in
    the installed CLI's `claude --help` / `claude -p --help`: "Only use MCP
    servers from --mcp-config, ignoring all other MCP configurations") so
    ambient user-scope servers registered in ~/.claude.json do NOT also load
    alongside the arm's own set — the isolation the arm exists to guarantee.
    """
    dest = workdir / name.replace("/", "-")
    if name == "bare":
        render_config.render_bare_control(dest)
        return {"env": {"CLAUDE_CONFIG_DIR": str(dest)}, "extra_argv": []}
    exclude_map = {
        "full": frozenset(),
        "no-leanctx": frozenset({"lean-ctx"}),
        "no-gitnexus": frozenset({"gitnexus"}),
        "no-shellguard": frozenset({"shell-guard"}),
    }
    rendered = render_config.render_full_variant(dest, exclude=exclude_map[name])
    extra_argv = []
    if rendered["mcp_config"]:
        extra_argv = ["--mcp-config", rendered["mcp_config"], "--strict-mcp-config"]
    return {"env": {"CLAUDE_CONFIG_DIR": rendered["config_dir"]}, "extra_argv": extra_argv}


def measure_cell_arms(task_name: str, model: str, reps: int, arm_specs: dict) -> dict:
    """Run one (task, model) cell across every arm in `arm_specs`
    ({name: {"env", "extra_argv"}}, see `_render_arm`); report each arm's
    absolute median metrics (including duration_ms) and correctness rate — no
    on/off ratio baked in, since there is no single "off" in an N-way sweep.
    Errored reps are excluded from the median exactly as `measure_cell` does
    (shared via `_run_arm_reps`), still kept (tagged `is_error`) in the raw
    dump.
    """
    per_arm = {}
    for name, spec in arm_specs.items():
        runs, raw_runs, ok, n, err = _run_arm_reps(
            task_name, model, reps, spec["env"], extra_argv=spec["extra_argv"]
        )
        per_arm[name] = {
            "median": _median(runs, ARMS_MEDIAN_KEYS),
            "correct_rate": (ok / n) if n else None,
            "error": err,
            "raw_runs": raw_runs,
            "spread": {
                "total_input": _abs_spread(runs, "total_input_tokens"),
                "cost": _abs_spread(runs, "cost_usd"),
            },
        }
    return {
        "schema": "arms-v1",
        "task": task_name,
        "model": model,
        "effort": EFFORT,
        "reps": reps,
        "arms": per_arm,
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
    assert _abs_spread(on, "total_input_tokens") == (200, 300, 400)
    assert _abs_spread([], "total_input_tokens") is None
    print("  ok  _abs_spread reports a single arm's own per-rep min/median/max")
    # render_full_variant (plan change 3, items 1-3): a real, isolated render
    # (into a temp dir — never the live ~/.claude) must produce every piece the
    # arms need, and must fail loudly on a typo'd exclude token rather than
    # silently rendering a still-full arm.
    with tempfile.TemporaryDirectory(prefix="selftest-full-") as _tmp:
        _dest = Path(_tmp) / "full"
        _result = render_config.render_full_variant(_dest)
        _claude_md = (_dest / "CLAUDE.md").read_text()
        assert _claude_md, "render_full_variant: CLAUDE.md is empty"
        assert "Personal agent configuration is maintained in" in _claude_md, \
            "render_full_variant: CLAUDE.md missing the stub marker text"
        assert "## Principles (always-on)" in _claude_md, \
            "render_full_variant: CLAUDE.md missing the Principles section"
        _settings = json.loads((_dest / "settings.json").read_text())
        _pre = _settings["hooks"]["PreToolUse"]
        assert any(g.get("matcher") == "^Bash$" for g in _pre), \
            "render_full_variant: settings.json missing the ^Bash$ shell-guard group"
        assert (_dest / "skills").resolve() == render_config.SKILLS_SRC.resolve(), \
            "render_full_variant: skills symlink does not point into this repo"
        assert (_dest / "agents").resolve() == render_config.AGENTS_SRC.resolve(), \
            "render_full_variant: agents symlink does not point into this repo"
        assert _result["mcp_config"], "render_full_variant: mcp_config missing for a non-excluded render"
        _mcp = json.loads(Path(_result["mcp_config"]).read_text())
        assert "lean-ctx" in _mcp["mcpServers"] and "gitnexus" in _mcp["mcpServers"], \
            f"render_full_variant: mcp-config missing lean-ctx/gitnexus: {sorted(_mcp['mcpServers'])}"
    print("  ok  render_full_variant() renders CLAUDE.md/settings.json/skills+agents/mcp-config into an isolated dir")
    # Ambient AGENTIC_MCP_EXCLUDE (e.g. inherited from a weak-tier shell) must NOT
    # silently drop servers from the 'full' arm — exclusions come only from the
    # explicit `exclude` argument, or the baseline would quietly be not-full.
    _saved_ambient = os.environ.get("AGENTIC_MCP_EXCLUDE")
    os.environ["AGENTIC_MCP_EXCLUDE"] = "lean-ctx,gitnexus"
    try:
        with tempfile.TemporaryDirectory(prefix="selftest-ambient-") as _tmp:
            _result = render_config.render_full_variant(Path(_tmp) / "full")
            _mcp = json.loads(Path(_result["mcp_config"]).read_text())
            assert "lean-ctx" in _mcp["mcpServers"] and "gitnexus" in _mcp["mcpServers"], \
                f"ambient AGENTIC_MCP_EXCLUDE leaked into the full arm: {sorted(_mcp['mcpServers'])}"
    finally:
        if _saved_ambient is None:
            os.environ.pop("AGENTIC_MCP_EXCLUDE", None)
        else:
            os.environ["AGENTIC_MCP_EXCLUDE"] = _saved_ambient
    print("  ok  render_full_variant ignores ambient AGENTIC_MCP_EXCLUDE (explicit exclude only)")
    # exclude={"shell-guard"} drops only the ^Bash$ group; exclude={"lean-ctx"}
    # drops the redirect hook group + mcp__lean-ctx__* allow entries + the
    # lean-ctx MCP server (gitnexus untouched); exclude={"gitnexus"} mirrors it.
    with tempfile.TemporaryDirectory(prefix="selftest-nosg-") as _tmp:
        render_config.render_full_variant(Path(_tmp) / "d", exclude=frozenset({"shell-guard"}))
        _settings = json.loads((Path(_tmp) / "d" / "settings.json").read_text())
        _pre = _settings["hooks"]["PreToolUse"]
        assert not any(g.get("matcher") == "^Bash$" for g in _pre), \
            "exclude={shell-guard}: ^Bash$ group should be gone"
        assert any(
            any("lean-ctx hook redirect" in h.get("command", "") for h in g.get("hooks", []))
            for g in _pre
        ), "exclude={shell-guard}: the lean-ctx redirect group should remain intact"
    print("  ok  exclude={'shell-guard'} drops only the ^Bash$ group")
    with tempfile.TemporaryDirectory(prefix="selftest-nolc-") as _tmp:
        _result = render_config.render_full_variant(Path(_tmp) / "d", exclude=frozenset({"lean-ctx"}))
        _settings = json.loads((Path(_tmp) / "d" / "settings.json").read_text())
        _pre = _settings["hooks"]["PreToolUse"]
        assert not any(
            any("lean-ctx hook redirect" in h.get("command", "") for h in g.get("hooks", []))
            for g in _pre
        ), "exclude={lean-ctx}: the redirect group should be gone"
        assert any(g.get("matcher") == "^Bash$" for g in _pre), \
            "exclude={lean-ctx}: the ^Bash$ group should remain intact"
        assert not any(a.startswith("mcp__lean-ctx__") for a in _settings["permissions"]["allow"]), \
            "exclude={lean-ctx}: mcp__lean-ctx__* allow entries should be gone"
        _mcp = json.loads(Path(_result["mcp_config"]).read_text())
        assert "lean-ctx" not in _mcp["mcpServers"], "exclude={lean-ctx}: lean-ctx server should be gone"
        assert "gitnexus" in _mcp["mcpServers"], "exclude={lean-ctx}: gitnexus server should remain"
    print("  ok  exclude={'lean-ctx'} drops the redirect group, allow entries, and the mcp server")
    with tempfile.TemporaryDirectory(prefix="selftest-nogn-") as _tmp:
        _result = render_config.render_full_variant(Path(_tmp) / "d", exclude=frozenset({"gitnexus"}))
        _mcp = json.loads(Path(_result["mcp_config"]).read_text())
        assert "gitnexus" not in _mcp["mcpServers"], "exclude={gitnexus}: gitnexus server should be gone"
        assert "lean-ctx" in _mcp["mcpServers"], "exclude={gitnexus}: lean-ctx server should remain"
    print("  ok  exclude={'gitnexus'} drops only the gitnexus mcp server (mirror image of no-leanctx)")
    # Fail loud, not open: a typo'd/unknown exclude token must raise, never
    # silently render a still-full arm that looks ablated.
    with tempfile.TemporaryDirectory(prefix="selftest-bad-") as _tmp:
        try:
            render_config.render_full_variant(Path(_tmp) / "d", exclude=frozenset({"totally-bogus"}))
            raise AssertionError("render_full_variant accepted an unknown exclude token")
        except ValueError:
            pass
    print("  ok  render_full_variant raises ValueError on an unknown exclude token")
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
    # Legacy regression (AC 5): with extra_argv unset (every legacy call site),
    # argv is byte-identical to the pre-arms-mode shape — no --mcp-config /
    # --strict-mcp-config ever leaks into a legacy invocation.
    legacy_av = _arm_argv("haiku", "p")
    assert "--mcp-config" not in legacy_av and "--strict-mcp-config" not in legacy_av, legacy_av
    assert legacy_av == [
        "claude", "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions", "--model", "haiku", "p",
    ], legacy_av
    print("  ok  _arm_argv legacy shape unchanged when extra_argv is not passed")
    # Arms-mode argv construction: --mcp-config appears exactly when extra_argv
    # carries one, and --strict-mcp-config always rides along with it (AC on the
    # ambient-server strictness question — see _render_arm's docstring).
    arms_av = _arm_argv("haiku", "p", extra_argv=["--mcp-config", "/tmp/x.json", "--strict-mcp-config"])
    assert "--mcp-config" in arms_av and "/tmp/x.json" in arms_av, arms_av
    assert "--strict-mcp-config" in arms_av, arms_av
    assert arms_av[-1] == "p", "prompt must stay last even with extra_argv"
    no_mcp_av = _arm_argv("haiku", "p", extra_argv=[])
    assert "--mcp-config" not in no_mcp_av, no_mcp_av
    print("  ok  _arm_argv splices --mcp-config/--strict-mcp-config only when the arm carries one")
    # duration_ms must be a first-class arms-mode median key (the user's "speed"
    # column) while the legacy median keys stay exactly as they were (AC 5).
    assert "duration_ms" in ARMS_MEDIAN_KEYS, ARMS_MEDIAN_KEYS
    assert "duration_ms" not in _LEGACY_MEDIAN_KEYS, _LEGACY_MEDIAN_KEYS
    assert _LEGACY_MEDIAN_KEYS == (
        "total_input_tokens", "repriced_input_tokens", "output_tokens", "cost_usd", "tool_calls", "num_turns",
    ), _LEGACY_MEDIAN_KEYS
    print("  ok  arms-mode median keys extend the legacy keys with duration_ms; legacy keys unchanged")
    # Errored reps (timeout/auth failure) must be excluded from the median, or a
    # rep that never really ran looks like a fast/cheap one and drags tool_calls
    # (always present, even on an error) toward zero. They still show up in the
    # raw dump, tagged is_error, so the failure is visible without corrupting
    # the headline number.
    global _run_arm
    saved_run_arm = _run_arm
    _clean = ('{"type":"result","is_error":false,"result":"(int, error)",'
              '"num_turns":2,"usage":{"input_tokens":10,"output_tokens":5,'
              '"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}')
    _timeout = '{"type":"result","is_error":true,"subtype":"timeout","result":"<TIMEOUT>","usage":{}}'
    on_calls = iter([_clean, _timeout, _clean])  # ON: clean, timeout, clean

    def _fake_run_arm(cwd, prompt, model, env=None, extra_argv=None):
        return _clean if env else next(on_calls)  # OFF (env set) always clean

    try:
        _run_arm = _fake_run_arm
        cell = measure_cell("trivial", "haiku", reps=3, off_config_dir=Path("/nonexistent-off"))
    finally:
        _run_arm = saved_run_arm
    assert cell["abs_on"]["num_turns"] == 2, cell  # median of {2, 2} (the timeout rep excluded)
    assert cell["correct_on_rate"] == 1.0, cell     # only the 2 non-errored ON reps count
    assert len(cell["raw_runs_on"]) == 3, cell       # but the raw dump keeps all 3
    assert sum(1 for r in cell["raw_runs_on"] if r["is_error"]) == 1, cell
    assert cell["correct_off_rate"] == 1.0 and len(cell["raw_runs_off"]) == 3, cell
    print("  ok  measure_cell excludes errored reps from medians, keeps them in the raw dump")
    # measure_cell_arms: same error-exclusion guarantee, N-way. One arm ("full")
    # times out on rep 2; its median must exclude that rep while the raw dump
    # keeps all 3 (mirrors the legacy-mode assertion above, N-way).
    _duration_clean = (
        '{"type":"result","is_error":false,"result":"(int, error)","num_turns":2,'
        '"duration_ms":1500,"usage":{"input_tokens":10,"output_tokens":5,'
        '"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}'
    )
    full_calls = iter([_duration_clean, _timeout, _duration_clean])

    def _fake_run_arm_arms(cwd, prompt, model, env=None, extra_argv=None):
        if extra_argv:  # the "full" arm carries extra_argv (its mcp-config)
            return next(full_calls)
        return _duration_clean  # "bare" arm: no extra_argv, always clean

    try:
        _run_arm = _fake_run_arm_arms
        arm_specs = {
            "bare": {"env": {"CLAUDE_CONFIG_DIR": "/nonexistent-bare"}, "extra_argv": []},
            "full": {"env": {"CLAUDE_CONFIG_DIR": "/nonexistent-full"},
                     "extra_argv": ["--mcp-config", "/tmp/x.json", "--strict-mcp-config"]},
        }
        arms_cell = measure_cell_arms("trivial", "haiku", reps=3, arm_specs=arm_specs)
    finally:
        _run_arm = saved_run_arm
    assert arms_cell["schema"] == "arms-v1", arms_cell
    assert set(arms_cell["arms"]) == {"bare", "full"}, arms_cell
    assert arms_cell["arms"]["full"]["median"]["num_turns"] == 2, arms_cell  # timeout rep excluded
    assert arms_cell["arms"]["full"]["median"]["duration_ms"] == 1500, arms_cell
    assert arms_cell["arms"]["full"]["correct_rate"] == 1.0, arms_cell
    assert len(arms_cell["arms"]["full"]["raw_runs"]) == 3, arms_cell
    assert sum(1 for r in arms_cell["arms"]["full"]["raw_runs"] if r["is_error"]) == 1, arms_cell
    assert arms_cell["arms"]["bare"]["median"]["duration_ms"] == 1500, arms_cell
    print("  ok  measure_cell_arms excludes errored reps per-arm, keeps duration_ms in the median keys")
    print(f"swe_bench selftest OK — {len(TASKS)} tasks, {checks} checks + error-guard + spread + effort + "
          "medians + arms.")
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


def _fmt_ms(x):
    return "—" if x is None else f"{x / 1000:.1f}s"


def _fmt_int(x):
    return "—" if x is None else str(x)


def _print_arms_cell(c: dict) -> None:
    """Human table for one arms-mode cell: arms × {duration_s, repriced_tokens,
    tool_calls, turns, cost, correct}, with per-rep spread (min–max, from
    `_abs_spread`) appended for the ratio-critical fields (total_input_tokens,
    cost_usd) whenever reps > 1 — mirrors legacy mode's `_matrix_row` spread
    suffix."""
    print(f"\n{c['task']} / {c['model']}  (reps={c['reps']}, effort={c['effort'] or 'default'})")
    header = (f"  {'arm':<14} {'duration':>9} {'in tok':>9} {'tools':>6} "
              f"{'turns':>6} {'cost':>8} {'correct':>8}")
    print(header)
    print(f"  {'-' * (len(header) - 2)}")
    for name in ARM_NAMES:
        arm = c["arms"].get(name)
        if arm is None:
            continue
        if arm.get("error"):
            print(f"  {name:<14} {'ERR':>9}  {str(arm['error'])[:40]}")
            continue
        med = arm["median"]
        row = (f"  {name:<14} {_fmt_ms(med.get('duration_ms')):>9} "
               f"{_fmt_int(med.get('repriced_input_tokens')):>9} "
               f"{_fmt_int(med.get('tool_calls')):>6} {_fmt_int(med.get('num_turns')):>6} "
               f"{_fmt(med.get('cost_usd'), suffix=''):>8} {_pct(arm.get('correct_rate')):>8}")
        sp = (arm.get("spread") or {}).get("total_input")
        if c.get("reps", 1) > 1 and sp:
            row += f"  in[{sp[0]}–{sp[2]}]"
        print(row)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SWE benchmark — config A/B across difficulty tiers and models.")
    ap.add_argument("--confirm", action="store_true", help="actually invoke the agent CLI (spends tokens)")
    ap.add_argument("--models", default="haiku,sonnet,opus", help="comma-separated model aliases/ids")
    ap.add_argument("--filter", default="all", help="all | a tier name (trivial|easy|medium|hard|very_hard)")
    ap.add_argument("--reps", type=int, default=1, help="repetitions per cell; the median is reported")
    ap.add_argument("--effort", default=None,
                    help="reasoning effort for `claude -p --effort` (e.g. low|medium|high); default = CLI default")
    ap.add_argument("--arms", default=None,
                    help="comma-separated arm names (bare,full,no-leanctx,no-gitnexus,no-shellguard) — an "
                         "N-way isolated-config sweep instead of the legacy ON/OFF pair; unset = legacy mode")
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

    arm_names = None
    if args.arms:
        arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
        unknown = [a for a in arm_names if a not in ARM_NAMES]
        if unknown:
            print(f"unknown arm(s) {unknown}; choose from {list(ARM_NAMES)}", file=sys.stderr)
            return 2

    confirm = args.confirm or os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"
    if not confirm:
        print("DRY-RUN — no tokens spent. Matrix that WOULD run (pass --confirm to execute):")
        print(f"  models : {models}")
        print(f"  tasks  : {tasks}")
        if arm_names:
            print(f"  arms   : {arm_names}  (each an isolated CLAUDE_CONFIG_DIR — "
                  "lib/render_config.render_full_variant / render_bare_control — never the live ~/.claude)")
            print(f"  reps   : {args.reps}  →  {len(models) * len(tasks) * len(arm_names) * args.reps} "
                  "agent invocations")
        else:
            print("  arms   : ON (full config) vs OFF (rendered bare CLAUDE_CONFIG_DIR — "
                  "lib/render_config.render_bare_control: no hooks, no MCP, no skills)")
            print(f"  reps   : {args.reps}  →  {len(models) * len(tasks) * 2 * args.reps} agent invocations")
        print("\nValidate the task checks now, free:  python3 evals/swe_bench.py --selftest")
        return 0

    # Run incrementally so a long matrix is observable mid-run and survives a kill:
    # each cell prints as it finishes and is appended to --out (if given) before the next starts.
    cells = []
    if arm_names:
        with tempfile.TemporaryDirectory(prefix="swe-arms-") as tmp:
            arm_specs = {name: _render_arm(name, Path(tmp)) for name in arm_names}
            for m in models:
                for t in tasks:
                    c = measure_cell_arms(t, m, args.reps, arm_specs)
                    cells.append(c)
                    _print_arms_cell(c)
                    if args.out:
                        with open(args.out, "a", encoding="utf-8") as fh:
                            fh.write(json.dumps({**c, "arm": ",".join(arm_names)}) + "\n")
                    # Fail fast on a systemic launch failure (e.g. auth), same as the
                    # legacy path below: if EVERY arm of the very first cell errored,
                    # every later cell will too — don't grind through an N-way matrix
                    # of phantom data.
                    arms = c["arms"]
                    if len(cells) == 1 and arms and all(a.get("error") for a in arms.values()):
                        first_err = next(a["error"] for a in arms.values())
                        print(f"\nAborting: the agent CLI failed to run — {first_err}\n"
                              "Every arm errored on the first cell, so this is systemic (not a task failure).\n"
                              "Most likely the nested `claude` could not authenticate. Run from a shell where\n"
                              "`claude -p \"hi\"` works (a fresh login, or export CLAUDE_CODE_OAUTH_TOKEN / "
                              "ANTHROPIC_API_KEY).", file=sys.stderr)
                        return 1
    else:
        print(_MATRIX_HEADER, flush=True)
        with tempfile.TemporaryDirectory(prefix="swe-off-config-") as tmp:
            off_config_dir = render_config.render_bare_control(Path(tmp) / "off-config")
            for m in models:
                for t in tasks:
                    c = measure_cell(t, m, args.reps, off_config_dir)
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

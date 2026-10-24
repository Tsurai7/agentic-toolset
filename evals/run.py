#!/usr/bin/env python3
"""Run agent-behavior evals for the agentic config.

Two tracks:
  * conformance — does a rule/skill change behavior and trigger when it should?
    Single transcript graded PASS/FAIL by an LLM judge.
  * value — does the artifact make the OUTCOME better? A/B: the same prompt with
    the artifact (treatment) and without it (control), graded by a pairwise judge
    with order-swap + flip-rate to control for position bias.

Dry by default. Set --confirm (or AGENTIC_EVAL_CONFIRM=1) to actually invoke the
agent. Run real evals from a throwaway scratch repo so a misbehaving case cannot
touch real work.

Every case verdict is one of PASS / FAIL / UNRELIABLE / ERROR. ERROR means the
run itself is not trustworthy data (a failed launch, a timeout, or unparseable
judge output) — never silently coerced into PASS or FAIL. If the very FIRST case
of a run errors with an auth-shaped message, the whole run aborts early rather
than grinding through a suite of phantom results (mirrors swe_bench.py's guard).

Both arms' transcripts and the judge's raw replies are persisted under
`results/<model>/transcripts/` so a verdict can be re-checked or re-judged
without re-spending agent tokens — see `--rejudge`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import agent, cases, judge, render_config  # noqa: E402

AGENT_CMD = os.environ.get("AGENTIC_EVAL_AGENT_CMD", "claude -p")
JUDGE_CMD = os.environ.get("AGENTIC_EVAL_JUDGE_CMD", "claude -p")
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _confirmed(args) -> bool:
    return args.confirm or os.environ.get("AGENTIC_EVAL_CONFIRM") == "1"


def _select(track: str, flt: str | None) -> list[dict]:
    cs = cases.load(track)
    if flt:
        cs = [c for c in cs if flt in c["id"]]
    return cs


def _out_dir(model: str | None) -> Path:
    d = RESULTS_DIR / (model or "default")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _transcripts_dir(model: str | None) -> Path:
    d = _out_dir(model) / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_transcript(model: str | None, case_id: str, ts: str, tag: str, text: str) -> str:
    """Persist one transcript/judge-reply artifact; returns its path relative to
    RESULTS_DIR's parent (normally evals/, but overridable — e.g. by tests — so
    the relative path is always computed against the same root RESULTS_DIR uses)."""
    path = _transcripts_dir(model) / f"{case_id}-{ts}-{tag}.txt"
    path.write_text(text, "utf-8")
    return str(path.relative_to(RESULTS_DIR.parent))


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# --- conformance track ---------------------------------------------------------

def run_conformance(cs: list[dict], model: str | None, first_of_run: list[bool]) -> int:
    failures = 0
    out_dir = _out_dir(model) if cs else None
    for c in cs:
        print(f"== [conformance] {c['id']} ==", flush=True)
        ts = _timestamp()
        transcript = agent.run_capture(AGENT_CMD, c["prompt"], model=model)
        tx_path = _write_transcript(model, c["id"], ts, "transcript", transcript)

        err = agent.result_error(transcript)
        is_first = first_of_run and first_of_run[0]
        if first_of_run:
            first_of_run[0] = False
        if err is not None:
            if is_first:
                # The FIRST case of the whole run failing to launch at all is the
                # systemic signal (mirrors swe_bench.py's "both arms errored on
                # cell 1" guard) — every later case would fail the same way.
                print(f"\nAborting: the agent CLI failed to launch — {err}\n"
                      "The first case of this run errored, so this is likely systemic "
                      "(not a case failure). Run from a shell where `claude -p \"hi\"` "
                      "works (a fresh login, or export ANTHROPIC_API_KEY).", file=sys.stderr)
                raise SystemExit(1)
            failures += 1
            print(f"  ERROR: launch failed — {err}\n", flush=True)
            _record_conformance(out_dir, c, model, "ERROR", err, [tx_path], None)
            continue

        verdict = judge.judge_conformance(c, transcript, JUDGE_CMD)
        v = verdict.get("verdict")
        mark = v if v in ("PASS", "ERROR") else "FAIL"
        failures += mark != "PASS"
        print(f"  {mark}: {verdict.get('reason', '')}\n", flush=True)
        judge_tx_path = _write_transcript(
            model, c["id"], ts, "judge", json.dumps(verdict))
        _record_conformance(out_dir, c, model, mark, verdict.get("reason", ""),
                             [tx_path, judge_tx_path], verdict)
    return failures


def _record_conformance(out_dir: Path | None, case: dict, model: str | None,
                         verdict: str, reason: str, transcript_paths: list[str],
                         raw_verdict: dict | None) -> None:
    if out_dir is None:
        return
    rec = {
        "id": case["id"], "track": "conformance", "model": model or "default",
        "verdict": verdict, "reason": reason,
        "transcripts": transcript_paths,
        "agent_cmd": AGENT_CMD, "judge_cmd": JUDGE_CMD,
        "judge_model": agent.cmd_model(JUDGE_CMD),
    }
    if raw_verdict is not None:
        rec["judge_raw"] = raw_verdict
    ts = _timestamp()
    (out_dir / f"{ts}-{case['id']}.jsonl").write_text(json.dumps(rec) + "\n", "utf-8")


# --- value track ---------------------------------------------------------------

def run_value(cs: list[dict], n: int, model: str | None, first_of_run: list[bool]) -> int:
    model_label = model or "default"
    out_dir = _out_dir(model_label)
    failures = 0

    with tempfile.TemporaryDirectory(prefix="agentic-eval-") as tmp:
        workdir = Path(tmp)
        for c in cs:
            case_n = c.get("n", n)  # case-level `n` overrides the --n default
            arms = render_config.prepare(c, workdir)
            wins = {"treatment": 0, "control": 0, "tie": 0, "error": 0}
            flips = 0.0
            flip_count = 0
            print(f"== [value] {c['id']}  (strategy={arms['strategy']}, "
                  f"confidence={arms['confidence']}, n={case_n}) ==", flush=True)
            runs = []
            for i in range(case_n):
                ts = _timestamp()
                t_arm, c_arm = arms["treatment"], arms["control"]
                t_tx = agent.run_capture(
                    AGENT_CMD, t_arm["prefix"] + c["prompt"], model=model, env=t_arm["env"])
                c_tx = agent.run_capture(
                    AGENT_CMD, c_arm["prefix"] + c["prompt"], model=model, env=c_arm["env"])
                t_path = _write_transcript(model_label, c["id"], ts, "on", t_tx)
                c_path = _write_transcript(model_label, c["id"], ts, "off", c_tx)

                t_err = agent.result_error(t_tx)
                c_err = agent.result_error(c_tx)
                is_first = first_of_run and first_of_run[0]
                if first_of_run:
                    first_of_run[0] = False
                if is_first and t_err and c_err:
                    # BOTH arms erroring on the very first run is systemic (mirrors
                    # swe_bench.py's identical guard) — every later run would too.
                    print(f"\nAborting: the agent CLI failed to launch — {t_err}\n"
                          "Both arms errored on the first run, so this is likely systemic "
                          "(not a case failure). Run from a shell where `claude -p \"hi\"` "
                          "works (a fresh login, or export ANTHROPIC_API_KEY).", file=sys.stderr)
                    raise SystemExit(1)
                if t_err or c_err:
                    wins["error"] += 1
                    reason = t_err or c_err
                    runs.append({
                        "winner": "error", "error": reason,
                        "treatment": agent.metrics(t_tx), "control": agent.metrics(c_tx),
                        "transcripts": {"on": t_path, "off": c_path},
                    })
                    print(f"  run {i+1}/{case_n}: ERROR — {reason}", flush=True)
                    continue

                pj = judge.judge_pairwise(c, t_tx, c_tx, JUDGE_CMD)
                wins[pj["winner"]] += 1
                if pj["flip_rate"] is not None:
                    flips += pj["flip_rate"]
                    flip_count += 1
                runs.append({
                    "winner": pj["winner"], "flip_rate": pj["flip_rate"],
                    "treatment": agent.metrics(t_tx), "control": agent.metrics(c_tx),
                    "transcripts": {"on": t_path, "off": c_path},
                })
                print(f"  run {i+1}/{case_n}: winner={pj['winner']} "
                      f"(orders: {pj['order1']}/{pj['order2']})", flush=True)

            flip_rate = (flips / flip_count) if flip_count else 0.0
            verdict = _value_verdict(c, wins, flip_rate)
            failures += verdict != "PASS"
            flip_str = "n/a" if flip_count == 0 else f"{flip_rate:.2f}"
            print(f"  => {verdict}  wins={wins}  flip_rate={flip_str}\n", flush=True)

            (out_dir / f"{_timestamp()}-{c['id']}.jsonl").write_text(
                json.dumps({
                    "id": c["id"], "track": "value", "model": model_label,
                    "skill": c.get("skill"), "pass_condition": c.get("pass_condition"),
                    "strategy": arms["strategy"], "confidence": arms["confidence"],
                    "n": case_n, "wins": wins, "flip_rate": flip_rate,
                    "verdict": verdict, "runs": runs,
                    "agent_cmd": AGENT_CMD, "judge_cmd": JUDGE_CMD,
                    "judge_model": agent.cmd_model(JUDGE_CMD),
                }) + "\n", "utf-8")
    return failures


def _value_verdict(case: dict, wins: dict, flip_rate: float) -> str:
    """Decide PASS / FAIL / UNRELIABLE / ERROR from the win tally and order-stability.

    `flip_rate` is the mean flip rate across judged (non-errored) runs only. A
    case that errored on every repeat has no comparison to grade at all — ERROR,
    never a silent FAIL/PASS. Errored repeats are otherwise excluded from the
    win-share denominator (`wins["error"]`, present since plan 07) since they
    carried no judge verdict to aggregate.
    """
    judged = sum(wins.values()) - wins.get("error", 0)
    if judged <= 0:
        return "ERROR"
    if flip_rate > judge.FLIP_THRESHOLD:
        return "UNRELIABLE"
    if case.get("pass_condition") == "treatment_not_worse":
        # Good enough if treatment is not the loser in a majority of judged runs.
        return "PASS" if (wins["treatment"] + wins["tie"]) / judged >= 0.5 else "FAIL"
    # default: treatment_preferred — treatment must win a strict majority.
    return "PASS" if wins["treatment"] / judged > 0.5 else "FAIL"


# --- metric track --------------------------------------------------------------

def run_metric(cs: list[dict]) -> int:
    """Assert local telemetry metrics against thresholds — no agent, no judge.

    Reads the number from telemetry/gate.py (the same calibrated aggregation as
    the standalone gate) and grades it with judge.judge_metric. Insufficient data
    is a SKIP, not a failure, so it is safe where transcripts are sparse.
    """
    gate = Path(__file__).resolve().parent.parent / "telemetry" / "gate.py"
    failures = 0
    for c in cs:
        print(f"== [metric] {c['id']} ==", flush=True)
        if c.get("metric") != "weighted_cache_hit_rate":
            print(f"  SKIP: unsupported metric '{c.get('metric')}'\n", flush=True)
            continue
        cmd = [sys.executable, str(gate), "--json", "--min-hit-rate", "0",
               "--last", str(c.get("window_sessions", 20)),
               "--min-tokens", str(c.get("min_tokens", 200_000))]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        try:
            data = json.loads(proc.stdout)
        except (json.JSONDecodeError, ValueError):
            failures += 1
            print(f"  FAIL: telemetry gate error: {(proc.stderr or proc.stdout).strip()[:200]}\n", flush=True)
            continue
        if data.get("status") == "skip":
            print(f"  SKIP: insufficient data ({data['total_input_tokens']} input tokens)\n", flush=True)
            continue
        verdict = judge.judge_metric(c, data["weighted_hit_rate"])
        mark = verdict["verdict"]
        failures += mark == "FAIL"
        print(f"  {mark}: {verdict['reason']}\n", flush=True)
    return failures


# --- rejudge: re-run judging from saved transcripts, no new agent tokens -------

def rejudge(result_path: Path) -> int:
    """Re-run judging on a previously written case-result JSON(L), reading its
    saved transcripts from disk instead of re-invoking the agent. The cheapest
    iteration loop for tuning the judge prompt/rubric: agent tokens are spent
    once, judge tokens can be spent again as many times as needed.
    """
    evals_dir = Path(__file__).resolve().parent
    try:
        rec = json.loads(result_path.read_text("utf-8").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        print(f"unusable result file (empty or invalid JSON): {result_path}", file=sys.stderr)
        return 2
    track = rec.get("track")

    if track == "conformance":
        tx_path = evals_dir / rec["transcripts"][0]
        transcript = tx_path.read_text("utf-8")
        case = {"id": rec["id"], "rule": rec.get("reason", "")}
        # The rule text isn't stored on the record; re-judging conformance needs
        # the original case file for `rule`/`expect`/`expect_not`.
        case = next((c for c in cases.load("conformance") if c["id"] == rec["id"]), case)
        verdict = judge.judge_conformance(case, transcript, JUDGE_CMD)
        print(f"REJUDGE [{rec['id']}]: {verdict}")
        return 0 if verdict.get("verdict") == "PASS" else 1

    if track == "value":
        case = next((c for c in cases.load("value") if c["id"] == rec["id"]), {"id": rec["id"]})
        wins = {"treatment": 0, "control": 0, "tie": 0, "error": 0}
        flips, flip_count = 0.0, 0
        for run in rec.get("runs", []):
            tx = run.get("transcripts")
            if not tx:
                print("  skip run: no saved transcripts (pre-rejudge result)")
                continue
            t_tx = (evals_dir / tx["on"]).read_text("utf-8")
            c_tx = (evals_dir / tx["off"]).read_text("utf-8")
            pj = judge.judge_pairwise(case, t_tx, c_tx, JUDGE_CMD)
            wins[pj["winner"]] += 1
            if pj["flip_rate"] is not None:
                flips += pj["flip_rate"]
                flip_count += 1
            print(f"  winner={pj['winner']} (orders: {pj['order1']}/{pj['order2']})")
        flip_rate = (flips / flip_count) if flip_count else 0.0
        verdict = _value_verdict(case, wins, flip_rate)
        print(f"REJUDGE [{rec['id']}]: wins={wins} => {verdict}")
        return 0 if verdict == "PASS" else 1

    print(f"unsupported track for rejudge: {track!r}", file=sys.stderr)
    return 2


# --- entrypoint ----------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Run agentic-cfg evals.")
    p.add_argument("--track", choices=["conformance", "value", "metric", "all"], default="conformance")
    p.add_argument("--filter", dest="flt", help="substring match on case id")
    p.add_argument("--n", type=int, default=3,
                   help="repeats per value case (default 3; a case's own 'n' field overrides this)")
    p.add_argument("--model", help="model passed to the agent (conformance + value; recorded per-model)")
    p.add_argument("--confirm", action="store_true", help="actually invoke the agent")
    p.add_argument("--rejudge", metavar="RESULT_JSON",
                   help="re-run judging from a saved results/<model>/*.jsonl file "
                        "(reads persisted transcripts, spends no agent tokens)")
    args = p.parse_args()

    if args.rejudge:
        return rejudge(Path(args.rejudge))

    tracks = ["conformance", "value", "metric"] if args.track == "all" else [args.track]
    selected = {t: _select(t, args.flt) for t in tracks}
    total = sum(len(v) for v in selected.values())
    if total == 0:
        print("No matching cases.", file=sys.stderr)
        return 1

    if not _confirmed(args):
        print(f"DRY RUN — {total} case(s). Set --confirm (or AGENTIC_EVAL_CONFIRM=1) to execute.\n")
        for t, cs in selected.items():
            for c in cs:
                guard = c.get("rule") or c.get("hypothesis", "")
                print(f"  [{t}:{c['id']}] {guard}")
                if t == "value":
                    print(f"      A/B ablate={c.get('ablate')} x{c.get('n', args.n)} "
                          f"model={args.model or 'default'}")
        print("\nNothing was executed.")
        return 0

    # Shared across tracks so the FIRST case of the whole run (conformance or
    # value, whichever runs first) gets the fail-fast auth check; a mutable
    # single-element list lets both track runners flip it off after case 1.
    first_of_run = [True]

    failures = 0
    if "conformance" in selected:
        failures += run_conformance(selected["conformance"], args.model, first_of_run)
    if "value" in selected:
        failures += run_value(selected["value"], args.n, args.model, first_of_run)
    if "metric" in selected:
        failures += run_metric(selected["metric"])

    print(f"{total - failures}/{total} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

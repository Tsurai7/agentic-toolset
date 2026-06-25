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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
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


# --- conformance track ---------------------------------------------------------

def run_conformance(cs: list[dict]) -> int:
    failures = 0
    for c in cs:
        print(f"== [conformance] {c['id']} ==", flush=True)
        transcript = agent.run_capture(AGENT_CMD, c["prompt"])
        verdict = judge.judge_conformance(c, transcript, JUDGE_CMD)
        mark = "PASS" if verdict.get("verdict") == "PASS" else "FAIL"
        failures += mark == "FAIL"
        print(f"  {mark}: {verdict.get('reason', '')}\n", flush=True)
    return failures


# --- value track ---------------------------------------------------------------

def run_value(cs: list[dict], n: int, model: str | None) -> int:
    model_label = model or "default"
    out_dir = RESULTS_DIR / model_label
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    with tempfile.TemporaryDirectory(prefix="agentic-eval-") as tmp:
        workdir = Path(tmp)
        for c in cs:
            arms = render_config.prepare(c, workdir)
            wins = {"treatment": 0, "control": 0, "tie": 0}
            flips = 0.0
            print(f"== [value] {c['id']}  (strategy={arms['strategy']}, "
                  f"confidence={arms['confidence']}, n={n}) ==", flush=True)
            runs = []
            for i in range(n):
                t_arm, c_arm = arms["treatment"], arms["control"]
                t_tx = agent.run_capture(
                    AGENT_CMD, t_arm["prefix"] + c["prompt"], model=model, env=t_arm["env"])
                c_tx = agent.run_capture(
                    AGENT_CMD, c_arm["prefix"] + c["prompt"], model=model, env=c_arm["env"])
                pj = judge.judge_pairwise(c, t_tx, c_tx, JUDGE_CMD)
                wins[pj["winner"]] += 1
                flips += pj["flip_rate"]
                runs.append({
                    "winner": pj["winner"], "flip_rate": pj["flip_rate"],
                    "treatment": agent.metrics(t_tx), "control": agent.metrics(c_tx),
                })
                print(f"  run {i+1}/{n}: winner={pj['winner']} "
                      f"(orders: {pj['order1']}/{pj['order2']})", flush=True)

            flip_rate = flips / n
            verdict = _value_verdict(c, wins, flip_rate)
            failures += verdict != "PASS"
            print(f"  => {verdict}  wins={wins}  flip_rate={flip_rate:.2f}\n", flush=True)

            (out_dir / f"{date.today().isoformat()}-{c['id']}.jsonl").write_text(
                json.dumps({
                    "id": c["id"], "track": "value", "model": model_label,
                    "skill": c.get("skill"), "pass_condition": c.get("pass_condition"),
                    "strategy": arms["strategy"], "confidence": arms["confidence"],
                    "n": n, "wins": wins, "flip_rate": flip_rate,
                    "verdict": verdict, "runs": runs,
                }) + "\n", "utf-8")
    return failures


def _value_verdict(case: dict, wins: dict, flip_rate: float) -> str:
    """Decide PASS / FAIL / UNRELIABLE from the win tally and order-stability."""
    if flip_rate > judge.FLIP_THRESHOLD:
        return "UNRELIABLE"
    n = sum(wins.values()) or 1
    if case.get("pass_condition") == "treatment_not_worse":
        # Good enough if treatment is not the loser in a majority of runs.
        return "PASS" if (wins["treatment"] + wins["tie"]) / n >= 0.5 else "FAIL"
    # default: treatment_preferred — treatment must win a strict majority.
    return "PASS" if wins["treatment"] / n > 0.5 else "FAIL"


# --- entrypoint ----------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Run agentic-cfg evals.")
    p.add_argument("--track", choices=["conformance", "value", "all"], default="conformance")
    p.add_argument("--filter", dest="flt", help="substring match on case id")
    p.add_argument("--n", type=int, default=3, help="repeats per value case (default 3)")
    p.add_argument("--model", help="model passed to the agent (value track records per-model)")
    p.add_argument("--confirm", action="store_true", help="actually invoke the agent")
    args = p.parse_args()

    tracks = ["conformance", "value"] if args.track == "all" else [args.track]
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
                    print(f"      A/B ablate={c.get('ablate')} x{args.n} "
                          f"model={args.model or 'default'}")
        print("\nNothing was executed.")
        return 0

    failures = 0
    if "conformance" in selected:
        failures += run_conformance(selected["conformance"])
    if "value" in selected:
        failures += run_value(selected["value"], args.n, args.model)

    print(f"{total - failures}/{total} passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

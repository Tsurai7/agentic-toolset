#!/usr/bin/env python3
"""Token-economy regression gate (Phase 3).

Fails (exit 1) when the token-weighted cache hit rate over a recent window of
Claude Code sessions drops below a threshold — a cheap, deterministic, zero-LLM
guard against a change that quietly wrecks cache reuse.

Why token-weighted, not a per-session average: a single-turn session legitimately
has a low hit rate (turn 1 can only *create* cache, never read it — see Phase 1).
Averaging per session would punish that cold-start noise. Weighting by tokens
(`sum(cache_read) / sum(total_input)`) lets large, cache-heavy sessions dominate
and de-weights tiny ones, so the number tracks real efficiency.

Why local-only: this reads ~/.claude transcripts, which exist on the developer's
machine, not in GitHub CI. Run it as a manual command (or a local hook); it is
NOT meant for the agentic-cfg GitHub Actions pipeline. See INTEGRATION.md.

Usage:
    python3 telemetry/gate.py                       # defaults below
    python3 telemetry/gate.py --min-hit-rate 0.80
    python3 telemetry/gate.py --last 20 --min-tokens 200000
    python3 telemetry/gate.py --project agentic-cfg
    python3 telemetry/gate.py --json

Exit codes:
    0  threshold met, OR insufficient data (skipped — not a failure)
    1  regression: weighted hit rate below threshold
    2  bad usage / no transcript root
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# gate.py and report.py live in the same directory; running the script puts that
# directory on sys.path, so this import resolves without packaging.
from report import collect


def evaluate(sessions, min_hit_rate: float, min_tokens: int) -> dict:
    total_read = sum(s.totals()["cache_read"] for s in sessions)
    total_input = sum(s.total_input() for s in sessions)
    hit = total_read / total_input if total_input else 0.0

    if total_input < min_tokens:
        status = "skip"
    elif hit < min_hit_rate:
        status = "fail"
    else:
        status = "pass"

    return {
        "status": status,
        "weighted_hit_rate": round(hit, 4),
        "min_hit_rate": min_hit_rate,
        "sessions": len(sessions),
        "total_input_tokens": total_input,
        "cache_read_tokens": total_read,
        "min_tokens": min_tokens,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--last", type=int, default=20, help="window of most-recent sessions (default 20)")
    ap.add_argument("--min-hit-rate", type=float, default=0.80,
                    help="fail below this token-weighted cache hit rate (default 0.80; "
                         "calibrated from observed range 86.7%%-95.1%%, with margin)")
    ap.add_argument("--min-tokens", type=int, default=200_000,
                    help="skip (do not fail) when the window has fewer input tokens than this")
    ap.add_argument("--project", help="filter by project/dir substring")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"transcript root not found: {root}", file=sys.stderr)
        return 2

    sessions = collect(root, args.project)[: args.last]
    res = evaluate(sessions, args.min_hit_rate, args.min_tokens)

    if args.json:
        json.dump(res, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        pct = res["weighted_hit_rate"] * 100
        floor = res["min_hit_rate"] * 100
        if res["status"] == "skip":
            print(f"SKIP: only {res['total_input_tokens']:,} input tokens over "
                  f"{res['sessions']} session(s) (< {res['min_tokens']:,}); not enough to judge.")
        elif res["status"] == "fail":
            print(f"FAIL: weighted cache hit rate {pct:.1f}% < {floor:.0f}% over "
                  f"{res['sessions']} session(s), {res['total_input_tokens']:,} input tokens.")
        else:
            print(f"PASS: weighted cache hit rate {pct:.1f}% >= {floor:.0f}% over "
                  f"{res['sessions']} session(s), {res['total_input_tokens']:,} input tokens.")

    return 1 if res["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())

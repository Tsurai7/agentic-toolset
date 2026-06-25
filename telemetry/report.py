#!/usr/bin/env python3
"""Token / cache telemetry over Claude Code session transcripts.

Phase 0 of the token-economy plan: turn "we save tokens" from a claim into a
measured number. Reads the JSONL transcripts Claude Code writes under
``~/.claude/projects/**/<session>.jsonl`` and reports, per session and in
aggregate: token volume, cache hit rate, estimated cost, main-thread vs
subagent split, and tool-call distribution.

Stdlib only (matches evals/run.py). No network, read-only on the transcripts.

Usage:
    python3 telemetry/report.py                # last 10 sessions, this machine
    python3 telemetry/report.py --last 30
    python3 telemetry/report.py --project agentic-cfg
    python3 telemetry/report.py --json         # machine-readable
    python3 telemetry/report.py --by-tool      # tool-call breakdown

Cost numbers are ESTIMATES from the editable PRICING table below. Verify the
rates against current Anthropic pricing before treating them as billing truth.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# USD per 1M tokens. Approximate, user-editable. cache_read ~= 0.1x input,
# cache_write_5m ~= 1.25x input, cache_write_1h ~= 2x input, per Anthropic's
# published multipliers. Keyed by a substring of the model id. VERIFY before
# trusting the dollar figures — these are for relative comparison, not invoices.
PRICING = {
    "opus":   {"in": 15.0, "cache_read": 1.5,  "cache_5m": 18.75, "cache_1h": 30.0, "out": 75.0},
    "sonnet": {"in": 3.0,  "cache_read": 0.3,  "cache_5m": 3.75,  "cache_1h": 6.0,  "out": 15.0},
    "haiku":  {"in": 1.0,  "cache_read": 0.1,  "cache_5m": 1.25,  "cache_1h": 2.0,  "out": 5.0},
}
DEFAULT_RATES = PRICING["opus"]


def rates_for(model: str) -> dict:
    m = (model or "").lower()
    for key, rates in PRICING.items():
        if key in m:
            return rates
    return DEFAULT_RATES


class SessionStats:
    """Aggregated usage for a single transcript file."""

    def __init__(self, path: Path):
        self.path = path
        self.session_id = ""
        self.cwd = ""
        self.git_branch = ""
        self.models: Counter = Counter()
        self.first_ts = ""
        self.last_ts = ""
        self.assistant_turns = 0
        # token buckets, split by main thread vs subagent (isSidechain)
        self.tokens = {
            "main": defaultdict(int),
            "sub": defaultdict(int),
        }
        self.cost = 0.0
        self.tools: Counter = Counter()

    def add_assistant(self, rec: dict) -> None:
        msg = rec.get("message") or {}
        usage = msg.get("usage") or {}
        if not usage:
            return
        self.assistant_turns += 1
        model = msg.get("model") or ""
        if model:
            self.models[model] += 1
        bucket = self.tokens["sub" if rec.get("isSidechain") else "main"]

        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        cr = int(usage.get("cache_read_input_tokens", 0) or 0)
        cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
        cc = usage.get("cache_creation") or {}
        cw_1h = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
        cw_5m = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
        if cw_1h + cw_5m == 0 and cw:  # older records without the breakdown
            cw_5m = cw

        bucket["input"] += inp
        bucket["output"] += out
        bucket["cache_read"] += cr
        bucket["cache_write"] += cw
        bucket["cache_write_1h"] += cw_1h
        bucket["cache_write_5m"] += cw_5m

        r = rates_for(model)
        self.cost += (
            inp * r["in"]
            + cr * r["cache_read"]
            + cw_1h * r["cache_1h"]
            + cw_5m * r["cache_5m"]
            + out * r["out"]
        ) / 1_000_000

        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self.tools[block.get("name", "?")] += 1

    def add_meta(self, rec: dict) -> None:
        self.session_id = self.session_id or rec.get("sessionId", "")
        self.cwd = self.cwd or rec.get("cwd", "")
        self.git_branch = self.git_branch or rec.get("gitBranch", "")
        ts = rec.get("timestamp")
        if ts:
            if not self.first_ts:
                self.first_ts = ts
            self.last_ts = ts

    # ---- derived ----
    def totals(self) -> dict:
        t = defaultdict(int)
        for bucket in self.tokens.values():
            for k, v in bucket.items():
                t[k] += v
        return t

    def total_input(self) -> int:
        t = self.totals()
        return t["input"] + t["cache_read"] + t["cache_write"]

    def cache_hit_rate(self) -> float:
        ti = self.total_input()
        return self.totals()["cache_read"] / ti if ti else 0.0

    def project(self) -> str:
        return Path(self.cwd).name if self.cwd else self.path.parent.name


def parse_file(path: Path) -> SessionStats | None:
    st = SessionStats(path)
    try:
        with path.open("r", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                st.add_meta(rec)
                if rec.get("type") == "assistant":
                    st.add_assistant(rec)
    except OSError:
        return None
    return st if st.assistant_turns else None


def collect(root: Path, project: str | None) -> list[SessionStats]:
    files = sorted(root.glob("**/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[SessionStats] = []
    for f in files:
        st = parse_file(f)
        if not st:
            continue
        if project and project.lower() not in (st.project().lower() + " " + st.path.parent.name.lower()):
            continue
        out.append(st)
    return out


def fmt_k(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def print_human(sessions: list[SessionStats], by_tool: bool) -> None:
    if not sessions:
        print("No sessions matched.")
        return

    header = f"{'session':<14} {'project':<22} {'in':>8} {'out':>7} {'cache_rd':>9} {'hit%':>5} {'sub%':>5} {'$est':>7}"
    print(header)
    print("-" * len(header))

    agg = defaultdict(int)
    agg_cost = 0.0
    tool_total: Counter = Counter()
    sub_tokens_total = 0
    all_input_total = 0

    for st in sessions:
        t = st.totals()
        ti = st.total_input()
        sub_in = (
            st.tokens["sub"]["input"]
            + st.tokens["sub"]["cache_read"]
            + st.tokens["sub"]["cache_write"]
        )
        sub_pct = (sub_in / ti * 100) if ti else 0.0
        print(
            f"{(st.session_id or st.path.stem)[:13]:<14} "
            f"{st.project()[:21]:<22} "
            f"{fmt_k(t['input']):>8} {fmt_k(t['output']):>7} {fmt_k(t['cache_read']):>9} "
            f"{st.cache_hit_rate() * 100:>4.0f}% {sub_pct:>4.0f}% {st.cost:>6.2f}"
        )
        for k, v in t.items():
            agg[k] += v
        agg_cost += st.cost
        tool_total.update(st.tools)
        sub_tokens_total += sub_in
        all_input_total += ti

    print("-" * len(header))
    overall_hit = (agg["cache_read"] / all_input_total * 100) if all_input_total else 0.0
    overall_sub = (sub_tokens_total / all_input_total * 100) if all_input_total else 0.0
    print(
        f"\nTOTALS over {len(sessions)} session(s):\n"
        f"  input (fresh)   : {fmt_k(agg['input'])}\n"
        f"  cache read      : {fmt_k(agg['cache_read'])}\n"
        f"  cache write     : {fmt_k(agg['cache_write'])} "
        f"(1h {fmt_k(agg['cache_write_1h'])} / 5m {fmt_k(agg['cache_write_5m'])})\n"
        f"  output          : {fmt_k(agg['output'])}\n"
        f"  cache hit rate  : {overall_hit:.1f}%   (cache_read / total input)\n"
        f"  subagent share  : {overall_sub:.1f}%   (context isolated off main thread)\n"
        f"  est. cost       : ${agg_cost:.2f}   (approximate — verify PRICING)"
    )

    if by_tool and tool_total:
        print("\nTool calls:")
        width = max(len(n) for n in tool_total)
        for name, cnt in tool_total.most_common():
            print(f"  {name:<{width}}  {cnt}")


def to_json(sessions: list[SessionStats]) -> list[dict]:
    out = []
    for st in sessions:
        t = st.totals()
        out.append({
            "session_id": st.session_id or st.path.stem,
            "project": st.project(),
            "git_branch": st.git_branch,
            "first_ts": st.first_ts,
            "last_ts": st.last_ts,
            "assistant_turns": st.assistant_turns,
            "models": dict(st.models),
            "tokens": {k: dict(v) for k, v in st.tokens.items()},
            "totals": dict(t),
            "cache_hit_rate": round(st.cache_hit_rate(), 4),
            "est_cost_usd": round(st.cost, 4),
            "tools": dict(st.tools),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"),
                    help="transcript root (default: ~/.claude/projects)")
    ap.add_argument("--last", type=int, default=10, help="number of most-recent sessions (default 10)")
    ap.add_argument("--project", help="filter by project/dir substring")
    ap.add_argument("--by-tool", action="store_true", help="print tool-call distribution")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"transcript root not found: {root}", file=sys.stderr)
        return 2

    sessions = collect(root, args.project)[: args.last]
    if args.json:
        json.dump(to_json(sessions), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_human(sessions, args.by_tool)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

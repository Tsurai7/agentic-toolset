#!/usr/bin/env python3
"""Deterministic tool benchmarks — concrete numbers, no agent, no LLM judge.

Some tools in this repo are not agent *choices* but deterministic transforms:
`rtk` and `lean-ctx` compress command output (their value is bytes/tokens saved),
`ast-grep` matches code structurally (its value is precision — no false positives),
`gitnexus` extracts a typed code graph (its value is structure grep cannot give).
For these, an LLM-judge A/B is the wrong instrument; the honest measurement is to
run the tool against a fixed fixture and count. This is Anthropic's "code-based
grading for deterministic criteria".

Each spec in bench/specs/*.json declares a `kind`:
  * compression — run a baseline command and the tool command; report bytes, lines,
    and approx tokens for each, plus the reduction.
  * precision   — run grep (textual) and the tool (structural); report match counts
    and false positives against the fixture's known true-match count.
  * graph       — run gitnexus analyze on a fixture; report nodes/edges/clusters/
    flows and index time, next to grep's flat text-match count.

Output is concrete absolute numbers, written to results/bench/<id>.json and rolled
into BENCHMARKS.md by report.py. Deterministic and cheap, so it is fine to run in
CI; it spends no tokens.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

EVALS = Path(__file__).resolve().parent
REPO = EVALS.parent
BENCH = EVALS / "bench"
SPECS = BENCH / "specs"
OUT = EVALS / "results" / "bench"

_GRAPH_RE = re.compile(r"(\d+)\s+nodes\s*\|\s*(\d+)\s+edges\s*\|\s*(\d+)\s+clusters\s*\|\s*(\d+)\s+flows")


def _approx_tokens(b: int) -> int:
    return (b + 3) // 4  # ~4 bytes/token, concrete and labelled approximate


def _resolve(argv: list[str], work: Path, fixture: Path | None) -> list[str]:
    repl = {"{work}": str(work), "{bench}": str(BENCH), "{repo}": str(REPO),
            "{fixture}": str(fixture) if fixture else "{fixture}"}
    out = []
    for a in argv:
        for k, v in repl.items():
            a = a.replace(k, v)
        out.append(a)
    return out


def _run(argv: list[str]) -> tuple[str, float]:
    t0 = time.perf_counter()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    dt = (time.perf_counter() - t0) * 1000.0
    return (proc.stdout or ""), dt


def _size(text: str) -> dict:
    return {"bytes": len(text), "lines": text.count("\n"),
            "approx_tokens": _approx_tokens(len(text))}


def _count(text: str, method: str) -> int:
    if method == "json_len":
        try:
            return len(json.loads(text or "[]"))
        except json.JSONDecodeError:
            return -1
    return sum(1 for ln in text.splitlines() if ln.strip())  # nonempty lines


def run_spec(spec: dict, work: Path) -> dict:
    fixture = REPO / spec["fixture"] if spec.get("fixture") else None
    for setup in spec.get("setup", []):
        subprocess.run(_resolve(setup, work, fixture), check=True, timeout=300)

    kind = spec["kind"]
    result = {"id": spec["id"], "tool_name": spec["tool"], "kind": kind,
              "label": spec.get("label", "")}

    if kind == "compression":
        base, _ = _run(_resolve(spec["baseline"], work, fixture))
        tool, _ = _run(_resolve(spec["tool_cmd"], work, fixture))
        b, t = _size(base), _size(tool)
        result.update({"baseline": b, "tool": t,
                       "reduction_pct": round((1 - t["bytes"] / b["bytes"]) * 100, 4)
                       if b["bytes"] else 0.0,
                       "reduction_factor": round(b["bytes"] / t["bytes"], 1)
                       if t["bytes"] else None})

    elif kind == "precision":
        base, _ = _run(_resolve(spec["baseline"], work, fixture))
        tool, _ = _run(_resolve(spec["tool_cmd"], work, fixture))
        bc = _count(base, spec.get("baseline_count", "lines"))
        tc = _count(tool, spec.get("tool_count", "json_len"))
        true_m = spec["true_matches"]
        result.update({"true_matches": true_m,
                       "baseline": {"matches": bc, "false_positives": bc - true_m},
                       "tool": {"matches": tc, "false_positives": tc - true_m}})

    elif kind == "graph":
        # gitnexus mutates the analyzed dir (.gitnexus/), so copy into work first.
        fx_copy = work / Path(spec["fixture"]).name
        shutil.copytree(fixture, fx_copy)
        out, dt = _run(_resolve(spec["tool_cmd"], work, fx_copy))
        m = _GRAPH_RE.search(out)
        graph = ({"nodes": int(m[1]), "edges": int(m[2]),
                  "clusters": int(m[3]), "flows": int(m[4])} if m else {"error": "unparsed"})
        base, _ = _run(_resolve(spec["baseline"], work, fx_copy))
        result.update({"tool": {**graph, "index_ms": round(dt)},
                       "baseline": {"text_matches": _count(base, "lines"),
                                    "structural_edges": 0}})
    else:
        result["error"] = f"unknown kind '{kind}'"
    return result


def main() -> int:
    specs = [json.loads(p.read_text("utf-8")) for p in sorted(SPECS.glob("*.json"))]
    if not specs:
        print("No bench specs in", SPECS, file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    import tempfile
    for spec in specs:
        with tempfile.TemporaryDirectory(prefix="agentic-bench-") as tmp:
            res = run_spec(spec, Path(tmp))
        (OUT / f"{spec['id']}.json").write_text(json.dumps(res) + "\n", "utf-8")
        print(f"== {res['id']} ({res['kind']}) ==")
        print("  " + json.dumps(res.get("tool", {})))
    print(f"\n{len(specs)} bench(es) done → {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Decomposed Haiku overhead measurement: separate prefix / cache-read / output.

For each (task, arm) run we capture, from stream-json:
  - per-turn assistant usage (turn-1 = always-on prefix proxy)
  - result.usage cumulative split: input(fresh) / cache_creation / cache_read / output
  - num_turns, tool_calls, total_cost_usd (API-equivalent), duration_ms
  - final answer text (for eyeball correctness)

Arms use prompt-isolation (the only option without ANTHROPIC_API_KEY): OFF is told
to ignore the custom config/tools. Run as a Python subprocess so `claude` is a child
process, NOT wrapped by the live PreToolUse hook.
"""
import json, os, subprocess, sys, tempfile, shutil

MODEL = "claude-haiku-4-5-20251001"
PERCALL_TIMEOUT = 300

OFF_PREFIX = ("Use only the standard built-in tools and plain shell commands. Do not use "
              "any custom skills, rules, rtk, lean-ctx, ast-grep, or gitnexus. ")


def make_easy():
    d = tempfile.mkdtemp(prefix="haiku-easy-")
    os.makedirs(os.path.join(d, "pkg"))
    open(os.path.join(d, "pkg", "a.go"), "w").write(
        'package pkg\nimport "errors"\n'
        'func A() error { return errors.New("x") }\n'
        'func B() (int, error) { return 0, nil }\n'
        'func C() string { return "" }\n'
        'func D() error { return nil }\n')
    open(os.path.join(d, "pkg", "b.go"), "w").write(
        'package pkg\nfunc E() error { return nil }\nfunc F() int { return 1 }\n')
    subprocess.run(["git", "init", "-q"], cwd=d)
    task = ("In this repository, find every Go function whose last return type is `error` "
            "and report the list of their names plus the total count.")
    return d, task, "expected A,B,D,E = 4"


def make_hard():
    """Free function Send is called in a.go, b.go, d.go (=3). Decoys: a same-named
    method Notifier.Send, a method call n.Send in c.go, plus Send in a string and a
    comment. Plain `grep 'Send('` over-counts (def + method def + method call)."""
    d = tempfile.mkdtemp(prefix="haiku-hard-")
    os.makedirs(os.path.join(d, "app"))
    w = lambda n, s: open(os.path.join(d, "app", n), "w").write(s)
    w("mailer.go", 'package app\nfunc Send(msg string) error { return nil }\n')
    w("notifier.go", 'package app\ntype Notifier struct{}\nfunc (n Notifier) Send(x string) {}\n')
    w("a.go", 'package app\nfunc useA() { _ = Send("hi") }\n')
    w("b.go", 'package app\nfunc useB(x string) { _ = Send(x) }\n')
    w("c.go", 'package app\n// remember to call Send here later\n'
              'func useC(n Notifier) { n.Send("the Send report") }\n')
    w("d.go", 'package app\nfunc useD() { _ = Send("z") }\n')
    subprocess.run(["git", "init", "-q"], cwd=d)
    task = ("In this Go repository there is a package-level function `Send` and also a "
            "method `Send` on the `Notifier` type. Count ONLY the call sites that invoke "
            "the package-level function `Send` (NOT the Notifier.Send method, and NOT the "
            "word Send appearing inside strings or comments). List the files containing "
            "those call sites and give the total count.")
    return d, task, "expected a.go,b.go,d.go = 3"


def run(cwd, prompt):
    argv = ["claude", "-p", "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions", "--model", MODEL, prompt]
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=PERCALL_TIMEOUT)
        return p.stdout or p.stderr
    except subprocess.TimeoutExpired:
        return '{"type":"result","result":"<TIMEOUT>","usage":{}}'


def parse(raw):
    tool_calls = 0
    turns = []          # per-assistant-turn usage dicts
    res = {}
    final = None
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "assistant":
            msg = o.get("message", {})
            u = msg.get("usage", {})
            if u:
                turns.append({
                    "input": u.get("input_tokens", 0),
                    "cache_creation": u.get("cache_creation_input_tokens", 0),
                    "cache_read": u.get("cache_read_input_tokens", 0),
                    "output": u.get("output_tokens", 0),
                })
            tool_calls += sum(1 for b in msg.get("content", [])
                              if isinstance(b, dict) and b.get("type") == "tool_use")
        elif o.get("type") == "result":
            u = o.get("usage", {}) or {}
            res = {
                "input": u.get("input_tokens", 0),
                "cache_creation": u.get("cache_creation_input_tokens", 0),
                "cache_read": u.get("cache_read_input_tokens", 0),
                "output": u.get("output_tokens", 0),
                "cost_usd": o.get("total_cost_usd"),
                "duration_ms": o.get("duration_ms"),
                "num_turns": o.get("num_turns"),
            }
            if isinstance(o.get("result"), str):
                final = o["result"]
    prefix_turn1 = turns[0] if turns else {}
    prefix_ctx = (prefix_turn1.get("cache_creation", 0)
                  + prefix_turn1.get("cache_read", 0)
                  + prefix_turn1.get("input", 0))
    total_input = res.get("input", 0) + res.get("cache_creation", 0) + res.get("cache_read", 0)
    repriced = res.get("input", 0) + res.get("cache_creation", 0)  # cache_read excluded (~0.1x/flat)
    return {
        "tool_calls": tool_calls,
        "result": res,
        "prefix_turn1_ctx": prefix_ctx,
        "total_input_tokens": total_input,
        "repriced_input_tokens": repriced,   # fresh + cache-creation only
        "final": (final or "")[:400].replace("\n", " "),
    }


def main():
    out = {}
    for name, maker in [("easy", make_easy), ("hard", make_hard)]:
        d, task, expect = maker()
        print(f"== {name}: {expect} ==", flush=True)
        try:
            print("  ON ...", flush=True)
            on = parse(run(d, task))
            print("  OFF ...", flush=True)
            off = parse(run(d, OFF_PREFIX + task))
        finally:
            shutil.rmtree(d, ignore_errors=True)
        out[name] = {"expect": expect, "on": on, "off": off}
    open("/tmp/haiku_decomp_result.json", "w").write(json.dumps(out, indent=2))
    print("\n=== DONE -> /tmp/haiku_decomp_result.json ===")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

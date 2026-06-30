# SWE benchmark design — testing config ideas across difficulty × model tiers

> Companion to [`evals/swe_bench.py`](../../evals/swe_bench.py). This is the methodology:
> what we measure, why, how to read it, and how to avoid fooling ourselves. It extends the
> repo's existing A/B runner [`evals/overhead.py`](../../evals/overhead.py) and the measured
> findings in [`plans/06-overhead-and-uplift.md`](../../plans/06-overhead-and-uplift.md).

## Why this exists

Every claim in this repo's improvement work — "skill X cuts tokens", "hook Y makes the model
smarter" — is only as good as the instrument that tests it. The repo already proved the
danger of *not* measuring: the prompt-based triage gate (W1) was a plausible improvement that,
when measured, **did nothing** (Haiku stayed at ~3–4× the bare-agent token cost). The lesson
(`plans/06` §7): *build the instrument first, then you can falsify a plausible-but-wrong
change instead of shipping it.* This benchmark is that instrument, broadened.

## The two regimes it must separate

The central, measured tension (`plans/06`, n=3 medians):

| model / config | trivial/easy | hard |
|---|---|---|
| Haiku, full config | **3.15× (FAIL ≤1.5×)** | 0.65× ✓ |
| Haiku, weak-tier | 2.27× (FAIL) | 0.93× ✓ |
| **Opus 4.8, full** | **1.00× ✓** | 0.99× ✓ |

The toolset **over-tools weak models on trivial tasks** (extra turns, not extra prefix) yet
**pays for itself on hard tasks** (structural precision a bare grep agent can't match). Any
benchmark that reports a single average hides this. So the design requirement is: **measure
each (model tier × task difficulty) cell separately** — an improvement is only real if it cuts
the trivial-regime overhead *without* regressing the hard-regime gain or correctness.

## The difficulty ladder

Five tiers, each a throwaway git repo with a **deterministic** check (`evals/swe_bench.py`):

| Tier | Task | Check | What it stresses |
|------|------|-------|------------------|
| `trivial` | Return-type of one function in one file | text | The over-tooling failure mode — a bare read answers it; the toolset must **not** orient/graph |
| `easy` | List the funcs returning `error` in a small package | text | Light scan; the W1/W5 regime from `plans/06` |
| `medium` | Fix a single-file off-by-one so `go test` passes | **state** (`go test`) | Read → edit → self-verify loop |
| `hard` | Count call sites of a package-level `Send`, excluding a same-named method, strings, comments | text | Structural disambiguation a regex grep flails on |
| `very_hard` | Finish a half-applied signature refactor across 3 files so it compiles + tests pass | **state** (`go test`) | Impact analysis (find every caller) + multi-file edit |

Two task *kinds*: **lookup** (graded on the answer text) and **edit** (graded on repo state —
a command that must pass *after* the arm runs). Edit tasks are the honest SWE signal: the
agent must actually change code, and `go test`/`go build` is an unforgeable oracle.

**Gameproofing.** `very_hard` pins behaviour with a test *and* forbids reverting the new
signature, so the model can't "fix" compilation by undoing the refactor. Edit checks run the
real toolchain, so a plausible-but-wrong answer fails. The harness self-test
(`--selftest`, in CI) proves each check **rejects the initial/wrong state and accepts the
known solution** — zero tokens, so the ladder itself can't silently rot.

## The arms

- **ON** — the full agentic-cfg environment (skills, hooks, MCP, prefix).
- **OFF** — prompt-isolation: the agent still *loads* the config but is told to ignore the
  custom skills/rules/rtk/lean-ctx/ast-grep/gitnexus and use only built-in tools.

Prompt-isolation (not a truly-bare binary) is deliberate: it isolates **induced behaviour**
(does the config make the model *act* differently — more turns, different tools?) from static
prefix bytes. `plans/06` §2 showed the overhead is ~all induced behaviour (turn-1 prefix is
1.00× across arms), so induced behaviour is the thing to measure. A separate truly-bare axis
(W2) exists for the static-prefix question.

## Metrics — and which matter per regime

Captured per arm via the selftested `agent.metrics` (so the parsing is guarded zero-token):

| metric | meaning | when it's the one that matters |
|---|---|---|
| `total_input_tokens` | fresh + cache_read + cache_write | the headline ratio, but ~95% is `cache_read` (priced ~0.1×, flat-rate-unbilled on Max) |
| `repriced_input_tokens` | `input + cache_creation` only | the honest input cost (the easy-task overhead is 1.25× here, not 3.93×) |
| `output_tokens` | generated tokens | the genuinely expensive class; tracks extra turns |
| `cost_usd` | API-equivalent $ | the bottom line; driven by output + repriced input |
| `num_turns` / `tool_calls` | agent loop length | **the root cause** — overhead is turns × per-turn re-read, not bytes |
| `correct_*_rate` | deterministic pass rate | the gate: a token win that regresses correctness is not a win |

Read **turns** to explain a ratio, **cost/repriced-input** for the bottom line, and **never**
report a token win without the correctness rate beside it.

## Getting a verdict out of noisy small-n

Agentic runs are high-variance (the n=1 fluke in `plans/06` §7 showed easy 0.59× once, then
2.27× at n=3). The harness defends against this:

- **Medians, not means**, over `--reps` (a single noisy run can't move the reported ratio).
- **Ratio of medians** per cell (robust to per-run spikes).
- **Paired design** — ON and OFF run on freshly-built identical repos, same model, back to back.
- **Effect-size gate, not p-values** — with few reps, use the owner's thresholds
  (`total_input ≤1.5×` and `cost ≤1.5×` in the easy regime; `≤1.0×` maintained in the hard
  regime; no correctness regression) rather than significance theatre.

Honest limits to state in any result: small n is **directional**, not a proof; `claude`
subprocess arms don't run inside the live PreToolUse hook; and flat-rate Max pricing means
`cost_usd` is an API-equivalent estimate, not a bill.

## Running it

```bash
python3 evals/swe_bench.py --selftest                       # zero tokens — validate the checks (CI runs this)
python3 evals/swe_bench.py                                  # dry-run: print the matrix plan, spend nothing
python3 evals/swe_bench.py --confirm --filter trivial --models haiku,opus   # one tier, two models
python3 evals/swe_bench.py --confirm --reps 3 --out results.jsonl --json     # full matrix, medians, persisted
```

The full matrix is `models × tiers × 2 arms × reps` invocations (default 3×5×2×1 = 30). Start
narrow (`--filter trivial --models haiku,opus`) to see the regime split cheaply, then widen.
`--out` appends each cell as a JSON line *as it finishes*, so a long run is observable mid-flight
and survives a kill.

### Prerequisite: the nested agent must be able to authenticate

Each arm shells out to `claude -p`. That subprocess needs its own working login, and **a `claude`
launched from inside a running Claude Code session inherits one only intermittently.** The nested
child reads the OAuth credential from the keychain; when that copy is currently valid it
authenticates and runs, but when it is stale (observed in practice as `expiresAt=0`) the child
returns `Not logged in · Please run /login` and exits in ~1 s — the live app refreshes its own
token in memory and does not always write a usable copy back in time. (Both states were observed
in one session: the same nested call failed, then succeeded minutes later after the credential
refreshed.) The harness **fails fast** on the failure mode with a clear message rather than
recording the failed launches as phantom `0%`-correct cells.

So for a reliable run, use a **plain terminal**, not an agent session. Verify auth first with a
one-liner, then run:

```bash
claude -p "say hi"                         # must print a normal reply, NOT "Not logged in"
python3 evals/swe_bench.py --confirm --reps 3 --out results.jsonl
```

For headless/CI use, export a long-lived token (`claude setup-token` →
`CLAUDE_CODE_OAUTH_TOKEN`) or an `ANTHROPIC_API_KEY` (billed separately from a Max plan).

## How to test a config idea with it

1. Capture a **baseline** matrix (current config).
2. Make the change behind a flag/tier.
3. Re-run the **same** matrix; compare per cell.
4. Accept only if: the trivial/easy overhead drops toward ≤1.5×, the hard-regime ratio stays
   ≤1.0×, and **no cell regresses correctness**. Otherwise the change is cosmetic or harmful —
   exactly what W1 was, and exactly what this instrument exists to catch.

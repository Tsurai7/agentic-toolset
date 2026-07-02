# Office-hours audit — is the installed config actually firing, and can `agentic gain` be trusted?

> Method: the gstack `office-hours` forcing questions, run as an **audit** (not a design
> session): premise challenge, Q2 (status quo — what already guards this), Q4 (narrowest
> wedge — smallest fixes that close the measured gaps). All numbers below were measured on
> 2026-07-02 on the primary machine, over the **last 50 sessions** under
> `~/.claude/projects` (1,432 Bash tool calls), with a throwaway analysis script that
> re-implements the transcript parsing independently of the Go code it audits.

## The ask

> "Deep analysis of how local Claude behaves with agentic-cfg applied. It seems it did not
> always use rtk, ast-grep, GitNexus, or the principles. Verify `agentic gain` reports
> correct data, so a performance/KPI report can be assembled easily on another machine."

## Premise challenge

"The model does not always use rtk" is the wrong lens since 2026-06-25 (`bb03f7f`): rtk and
the ast-grep precedence are enforced **mechanically** by the PreToolUse shell-guard hook
(`internal/hook/hook.go`, shell fallback `providers/claude/hooks/shell-guard.sh`), not by
model discipline. The transcript records the command *as the model wrote it*, and the hook
rewrite is invisible in the JSONL — so "I don't see rtk in the transcript" proves nothing.
The right questions are: **what share of shell traffic does the enforcement pipeline
actually cover, where does it leak, and does the built-in readout make those leaks
visible.** Measured answers below.

## Findings — what is verified working

1. **`agentic gain` numbers are correct.** An independent Python re-implementation of the
   parser (same rules: assistant records with usage, dedupe by `message.id`, sidechain
   split, mtime-ordered `--last`) produced **token-for-token identical** output on a frozen
   project slice (`--project sys-design --last 0`): 4 sessions, total_input 7,329,672,
   cache hit 96.99%, input bill $4.23, saved $21.90, est. total $6.08 — every field equal.
   On the live last-50 window the two runs differ by <1%, fully explained by active
   sessions shifting the mtime window between invocations. `go test ./internal/gain
   ./cmd/agentic` passes. `telemetry/report.py` runs and mirrors the same parsing.
2. **The ast-grep deny fires in practice.** 48 deny events observed in transcript tool
   results; the deny reason text matches `astGrepReason`. It also fired on this audit
   session itself and the auditor switched to `sg` as intended.
3. **Cache hygiene is healthy.** Last 50 sessions: cache hit rate 97.9% (floor: 80%),
   subagent share 27.5%, input bill $878.94 vs $5,431.32 avoided (the honesty note in
   `internal/gain/gain.go` correctly attributes that saving to the platform cache, not the
   config).
4. **Wrapping coverage.** Simulating the shell-guard decision over all 1,432 recorded Bash
   commands: 49.0% get auto-wrapped (rtk/lean-ctx), 13.1% were already `rtk`-prefixed by
   the model, 4.1% would be denied (grep-on-code).

## Findings — measured gaps

5. **~34% of shell traffic runs uncompressed** through the documented fail-open paths:
   31.4% multiline/heredoc, 1.3% `$( )`, 1.0% `cd`-chains, 0.2% leading `VAR=`. Heredocs
   dominate: models ignore the "put complex logic in a script file" instruction.
6. **The deny funnel converts poorly.** Of ~50 deny events: 14 switched to `sg`, 19
   retried grep (deny-loops, or evasion), 12 did something else, 5 dropped the thread.
   `sg`/`ast-grep` appears in 43 commands vs 268 grep/rg commands overall.
7. **Guard-order loophole (confirmed exploited).** In `internal/hook/hook.go` the
   already-wrapped early-exit (line ~97) and the complex-command fail-open (~102) run
   **before** the ast-grep guard (~110); same order in the shell fallback. So
   `rtk grep … foo.py` and any multiline grep-on-code bypass the deny entirely — and a
   transcript shows a model doing exactly `rtk grep -rn "report.py" bin/ …` right after
   being denied. → `issues/shell-guard-astgrep-order-bypass.md`.
8. **rtk wrapping breaks bare `=`-words.** `echo ===` → hook rewrites to `rtk echo ===` →
   rtk evaluates via zsh, where `=word` is equals-expansion → `(eval):1: == not found`,
   exit 1. Reproduced directly with `rtk echo ===` (rtk 0.40.0). Cousin of the archived
   `shell-hook-breaks-shell-variables.md`. → `issues/rtk-wrap-breaks-equals-words.md`.
9. **lean-ctx is effectively decorative at the model layer.** Over 50 sessions: 6
   `ctx_read` + 6 `ctx_search` calls vs 644 native Reads. And the `lean-ctx hook redirect`
   PreToolUse hook returned a plain allow (no rewrite) for both a 526-line Go file and a
   340-line doc — measured as a no-op for Read on this machine. The MCP instruction
   "ALWAYS use ctx_read" is neither followed nor enforced.
10. **GitNexus is nearly unused but pays hook overhead on every call.** 1 tool call
    (`mcp__gitnexus__context`) in 50 sessions, while `gitnexus-hook.cjs` runs on **every**
    Bash/Grep/Glob PreToolUse *and* Bash PostToolUse (10s timeout each). First place in
    the precedence table, last place in actual usage.
11. **Pricing tables predate the Claude 5 family.** Neither `internal/gain/gain.go` nor
    `telemetry/report.py` knows `fable`; unknown models silently bill at **opus** rates.
    `claude-fable-5` is already 9.7% of input in the last 50 sessions. Costs are labeled
    estimates, so honesty holds, but per-model comparisons skew.
12. **Orchestration target not yet met.** By-model input share: opus 62.0%, sonnet-5
    25.8%, fable-5 9.7%, haiku 1.6%. The cheap tier is not carrying the bulk — though the
    2026-07-01..02 `subagents` sessions (sonnet-5/haiku executing, opus orchestrating) show
    the delegation wave starting to bite.

## Q2 — status quo (what already guards this)

Mechanical enforcement (shell-guard + CI self-test), the eval loop (`evals/lint.py` fails
CI on skills without evals), the prefix budget, and `agentic gain --gate` all exist and
work. **What is genuinely missing is observability of enforcement itself:** `agentic gain`
reports token economy but nothing about coverage — the 34% fail-open share, the deny→sg
conversion rate, and the ctx/gitnexus adoption counts are invisible without a hand-written
script like this audit's.

## Q4 — narrowest wedge (recommended, not implemented here)

1. **Reorder the guards** (one function each in `hook.go` + `shell-guard.sh` + tests):
   run the ast-grep deny before the already-wrapped exit and before the multiline
   fail-open. Closes finding 7 with no new machinery.
2. **Harden the `=`-word case**: in the rtk fallback, pass through (or quote) commands
   containing a bare `=`-leading word, mirroring the existing `VAR=` guard. Closes 8.
3. **`agentic gain --adoption` (or `agentic adoption`)**: emit wrapped / fail-open /
   denied shares, deny→sg conversion, `ctx_*` and gitnexus call counts. This turns this
   audit into a one-command, cross-machine KPI report — the piece the operator asked for.
4. **Add Claude 5 pricing rows** (or at least mark `model unknown → opus rates` in the
   by-model output) in both pricing tables, kept in sync per the existing comment.
5. **Decide GitNexus's fate with data**: either make the index pay (surface it in the
   session-start context so the graph actually gets queried) or drop the per-call hooks;
   two 10s-timeout hook slots per shell call for 1 use / 50 sessions is pure overhead.

## Reproducing this report on another machine

```bash
git clone <repo> && cd agentic-cfg
make build                        # Go toolchain required; bin/agentic is gitignored
./bin/agentic gain --last 50 --by-model
./bin/agentic gain --json         # machine-readable
./bin/agentic cache               # cache-focused view
./bin/agentic gain --gate         # CI pass/fail on the 80% cache floor
python3 telemetry/report.py --last 50 --by-tool   # no build needed, stdlib-only
```

Caveats: transcripts are per-machine (`~/.claude/projects`, override with `--root`);
the readout measures the *platform* prompt cache, not config-attributed savings (A/B via
`evals/` is the attribution tool); verify the pricing tables before quoting dollars.
Adoption metrics (rtk coverage, deny funnel, ctx/gitnexus usage) are **not** in the
readout yet — that is wedge 3 above.

## Erratum (2026-07-02)

The dollar figures quoted throughout this audit (findings 1, 3, 11 above) were computed
with the pricing table *before* this wave's fix: opus at $15 in / $75 out per MTok — **3x**
the corrected $5 / $25 current Opus 4.x rate — and `claude-fable-5`/`claude-mythos-5`
billed at those stale opus rates for lack of a matching pricing row. Every dollar figure
above ($4.23, $21.90, $6.08, $878.94, $5,431.32, and the per-session `$est` column) is
therefore overstated and should be treated as superseded, not corrected in place.

Token counts, cache hit rates, subagent shares, wrapping-coverage percentages, and every
other non-dollar finding are **unaffected** — the pricing table only feeds the `$`-prefixed
fields; the token-level parsing this audit verified independently (finding 1) did not
change. Re-run `agentic gain` after this wave (plans 03–04 of `gain-enforcement-fixes`) for
corrected dollar figures.

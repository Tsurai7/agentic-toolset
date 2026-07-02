# 02 — gain / telemetry accounting correctness

**Owner:** one implementer. **Files:** `internal/gain/gain.go`,
`internal/gain/gain_test.go`, `telemetry/report.py`.

The Go binary and the Python reporter must stay in lockstep — the audit
confirmed they currently agree *while both are wrong* (B1). Every numeric fix is
validated against a **frozen copy** of real transcripts: `cp -R
~/.claude/projects <tmp>/projects` once, then run every before/after comparison
against `<tmp>/projects` so the two runs see identical bytes. Never mutate
`~/.claude`.

---

## B1 — [BUG, high] first-wins dedup undercounts `output_tokens`

**Evidence.** `gain.go:269-274` skips any assistant record whose `message.id`
was already seen (first-wins). `telemetry/report.py` `add_assistant` has the
identical `if mid in self._seen_msgs: return`. But Claude Code writes **one
record per content block**, and `output_tokens` **grows** to its final value on
the last record while input-side fields are byte-identical across repeats.
Verified on a frozen 20-file window: 570 message groups, 526 with repeats; 312
differ **only** in `output_tokens`; 0 differ in any input-side field; every
output sequence is monotonically non-decreasing with `last == max` in 100% of
cases. First-record output total 160,391 vs final-record 460,841 — ~65% of true
output dropped in that window (window-dependent; the auditor's earlier window
was ~19%). Cost understated ~12% in that window; `sonnet-5` output understated
27.8×. Cache hit rate, input bill, and the gate are **unaffected** (input-side
fields don't change across repeats). The doc comment at `gain.go:228-230` states
the wrong premise.

**Fix.** Switch to **last-wins** per `message.id` in both implementations, in
lockstep. Precise mechanics (do not just "replace the value" — the accumulators
are additive and streamed):
- Keep the `seen` set, but on **first** sight of an id do the full `addUsage`
  **and** increment turn/model counts once, and **store the record's usage
  snapshot** keyed by id.
- On a **repeat** id, do **not** re-increment turn/model counts. Instead add the
  **per-field delta** `(new - stored)` for every usage field (input, cache_read,
  cache_5m, cache_1h, output) to the token accumulators, then update the stored
  snapshot. Full-field delta (not output-only) is used so the fix stays correct
  even if a non-output field ever varies across repeats — the audit found only
  output varies today, but the delta form costs nothing extra and does not rely
  on that invariant. Deltas sum to the last record's values (verified: sequences
  are monotonic non-decreasing), i.e. last-wins.
- Mirror the identical delta logic in `telemetry/report.py add_assistant`.
- Update the `gain.go:228-230` dedup comment and `report.py` to describe
  last-wins, and update the `gain_test.go` `sample` fixture so the duplicate
  `m1` record carries a **larger** `output_tokens`; assert the last value wins
  (the current fixture gives both records identical usage, so it cannot
  distinguish first- from last-wins).

**AC1.** New/updated `gain_test.go` case: a session with `m1` appearing twice,
output 50 then 500 → asserted total output = 500 (not 50, not 550).
**AC2.** On the frozen window, `<tmp>/agentic gain --last 20 --json` output
total **increases** vs the pre-fix binary, and equals the sum of per-message
**final** `output_tokens` (compute the expected value with a throwaway script
over the same window and assert equality). Capture both numbers.
**AC3.** `telemetry/report.py --last 20 --json` per-session output totals match
the Go binary's on the same window (parity preserved after the fix).
**AC4.** Cache-read / input / cache-write totals are **unchanged** by this fix
(regression guard: only output and cost move).

---

## B2 — [BUG, high] `DeniesObserved` counts any result containing the reason text

**Evidence.** `gain.go:332` counts a deny via
`strings.Contains(string(b.Content), astGrepReasonPrefix)` where `b.Content` is
the raw JSON of the whole `tool_result`. The literal
`"Use ast-grep for structural code search"` is source text in `hook.go:212`,
`shell-guard.sh:100`, `gain.go:342`, `gain_test.go:31`, plus docs — so any Read
/ diff / eval output of those files is miscounted as an observed deny. On a
frozen 20-session window the binary reported 51 observed denies where only 17
were real deny payloads (the other 34 were Read dumps / git diffs of the guard
files) — ~3× inflation (window-dependent). The `gain.go:339-341` comment
("exact enough to avoid false positives") is false.

**Fix.** Match the deny **exactly**, not by containment. **First confirm the
real shape:** inspect an actual deny `tool_result` in the frozen window (grep the
transcripts for the reason literal and print the enclosing `tool_result` block)
to see whether `b.Content` is a JSON string or a structured array, and whether
the reason sits at the start. Then require the deny reason to be the actual
result payload — unmarshal `b.Content` to its text form (handling string- and
array-of-blocks shapes) and use `strings.HasPrefix(text, astGrepReasonPrefix)`
(a real deny result *starts* with the reason; the 34 false positives are Read
dumps starting with `"1\t…"` and diffs starting with headers, so HasPrefix
eliminates them). Keep a length sanity guard only if the shape inspection shows
HasPrefix alone is insufficient. Fix the misleading `gain.go:339-341` comment.

**AC5.** New `gain_test.go` case: a session with (a) one genuine deny
`tool_result` and (b) one `tool_result` that is a line-numbered Read dump of a
file *containing* the reason literal → `DeniesObserved == 1`, not 2.
**AC6.** On the frozen window, observed-denies count from the fixed binary
equals the count of deny-classified Bash commands it reports (the audit's
cross-check: real denies == deny-classified commands). Capture both.

---

## B3 — [BUG, medium] grep adoption tally misses self-wrapped `rtk grep`

**Evidence.** `gain.go:311` applies `hook.GrepTokenRe` (anchored at
start-of-string / after an operator) to the **raw** command, so `rtk grep …` /
`rtk rg …` are never counted as grep calls — while `sgCallRe` (`gain.go:150`,
matches after any whitespace) *does* count `rtk sg …`. This biases the
sg-vs-grep comparison (`gain.go:655`) and is internally inconsistent with the
`by_decision` tally in the same block, which normalizes via `hook.Classify` →
`stripWrappers`. Measured ~3% grep undercount on the current last-50 window
(the auditor's ~13% was an older window).

**Fix.** Count grep on the wrapper-normalized command, symmetric with `sgCallRe`.
Keep it **inside `gain.go`** (do not modify `internal/hook`, to keep this bucket
file-disjoint from plan 01): strip a leading `rtk `/`lean-ctx ` prefix (and
leading `VAR=` assignment) from the command before applying `GrepTokenRe`, or
match with a loosened local pattern of the `sgCallRe` shape. Document the choice
in a one-line comment.

**AC7.** New `gain_test.go` case: a transcript with `grep …`, `rtk grep …`,
`rtk rg …`, `sg …`, `rtk sg …` → `GrepCalls == 3` and `SgCalls == 2`
(currently `GrepCalls == 1`).
**AC8.** On the frozen window, `grep_calls` from the fixed binary ≥ the pre-fix
value (undercount closed); capture both.

---

## Encoding — [DEBT] `telemetry/report.py:166` missing `encoding="utf-8"`

**Evidence.** `report.py:166` `with path.open("r", errors="replace")` omits
`encoding=`, so it falls back to the locale encoding — the only unpinned open in
the file (every other in-scope Python pins `encoding="utf-8"`).

**Fix.** Add `encoding="utf-8"` to that `open`. No behavior change on a UTF-8
locale; correctness under `LANG=C`.

**AC9.** `grep -n 'open(' telemetry/report.py` shows every read pins
`encoding="utf-8"`.

---

## Plan-level acceptance

- `go test ./internal/gain/ ./cmd/agentic/ -count=1` and
  `python3 telemetry/report.py --last 3` pass.
- Before/after numbers on the frozen window captured for B1/B2/B3 (the proof).
- Go and Python outputs parity-checked on the same window after B1.
- Diff touches only the three files named at the top.

# 03 — `agentic gain --adoption`: enforcement-coverage readout from transcripts

**Problem** (audit findings 4–6, 9–10): `agentic gain` reports token economy but nothing
about whether the enforcement layer actually covers the traffic. The 2026-07-02 audit had
to hand-write a script to learn that ~34% of Bash commands run uncompressed (fail-open),
that ast-grep denies convert poorly, and that `ctx_*`/GitNexus tools are barely used.
Make that a one-command, cross-machine readout.

**Depends on:** plans 01–02 being merged into the working tree first (this plan exports
and reuses the classifier whose order they change).

## Change specification

### 1. `internal/hook/hook.go` — export the classification

Refactor `shellGuard`'s decision chain so the *decision* is computable without I/O:

```go
// Decision classifies what the shell-guard would do with a Bash command.
type Decision string

const (
    DecisionEmpty        Decision = "empty"
    DecisionDenyGrepCode Decision = "deny-grep-on-code"
    DecisionAlreadyWrapped Decision = "already-wrapped"
    DecisionFailOpenComplex Decision = "failopen-complex"   // heredoc/multiline/$( )/backtick/cd
    DecisionFailOpenAssign  Decision = "failopen-assign"    // leading VAR= (rtk fallback guard)
    DecisionFailOpenEquals  Decision = "failopen-equals"    // bare =-leading token (plan 02)
    DecisionWrap            Decision = "wrap"               // would be wrapped (lean-ctx or rtk)
)

// Classify returns the decision for a command, matching shellGuard's order exactly.
func Classify(cmd string) Decision
```

`shellGuard` must **call `Classify`** and act on the result (deny / exit / delegate /
rewrite), so the two can never drift. Note: `Classify` cannot distinguish lean-ctx-wrap
from rtk-wrap (that depends on the live `lean-ctx` binary) — that is why there is a
single `DecisionWrap`; do not shell out from `Classify`. Existing hook tests must pass
unchanged; add a couple of direct `Classify` unit cases.

### 2. `internal/gain/gain.go` — collect adoption stats during parsing

Extend parsing (opt-in, so the default `gain` path stays cheap):

- `ParseLines` gains an option (e.g. a package-level `type ParseOpts struct{ Adoption bool }`
  variant `ParseLinesOpts(r, opts)`; keep `ParseLines` as a thin wrapper so existing
  callers/tests compile unchanged).
- When enabled, additionally scan:
  - **assistant records** — `message.content` when it is an array: for each block with
    `type == "tool_use"`, tally `name` into per-session tool counts; when
    `name == "Bash"`, run `hook.Classify(input.command)` and tally the decision; also
    tally `sg`/`ast-grep` usage (regex `(^|[\s|;&])(sg|ast-grep)\s`) and any
    grep/rg usage (reuse the hook's `grepTokenRe`).
  - **user records** — `message.content` array blocks with `type == "tool_result"` whose
    stringified content contains the exact `astGrepReason` prefix
    (`"Use ast-grep for structural code search"`) → count as an observed deny.
- Session gains an `Adoption *AdoptionStats` field (nil when not collected), with:
  `BashTotal`, `ByDecision map[string]int`, `DeniesObserved`, `SgCalls`, `GrepCalls`,
  `CtxCalls` (tool name prefix `mcp__lean-ctx__`), `GitnexusCalls` (tool name contains
  `gitnexus`, case-insensitive), `NativeReads` (`Read`), `NativeGreps` (`Grep`).
- `Aggregate` sums these into the `Report` (an `*AdoptionStats` field, JSON key
  `"adoption"`, omitted when nil).

### 3. CLI surface

- `agentic gain --adoption` flag: enables collection and appends an adoption block to the
  human-readable output, e.g.:

```
adoption — enforcement coverage over N session(s):
  bash calls           : 1432
  wrapped (rtk/lean-ctx): 49.0%   already-wrapped: 13.1%
  fail-open            : 33.9%   (complex 31.4% / assign 0.2% / equals 0.3%)
  deny (grep-on-code)  : 4.1%   observed denies in results: 48
  ast-grep (sg) calls  : 43     grep/rg calls: 268
  lean-ctx ctx_* calls : 12     gitnexus calls: 1
  native Read / Grep   : 644 / 0
```

  (Percentages of `BashTotal`; layout may differ, content may not.)
- `--adoption --json` embeds the same numbers under `"adoption"`.
- Update the `fs.Usage` text in `internal/gain/gain.go` `Main` and the command help in
  `cmd/agentic/main.go` if it enumerates gain flags (check first; touch only if it does).

### 4. Tests

`internal/gain/gain_test.go` — a fixture transcript (string literal, ~8 JSONL lines)
containing: one rtk-wrapped Bash tool_use, one heredoc Bash, one grep-on-code Bash, one
`sg run` Bash, one `mcp__lean-ctx__ctx_read` tool_use, one `Read` tool_use, one user
tool_result carrying the deny reason text. Assert exact tallies for every AdoptionStats
field, and assert `Session.Adoption == nil` when parsing the same fixture with adoption
off. Keep existing tests untouched and passing.

### 5. Docs

- `telemetry/README.md`: add `agentic gain --adoption` to the built-in readout section
  (one short paragraph: what it measures, that it complements — not replaces — the cache
  metrics).
- `SETUP.md`: add the flag to the existing `agentic gain` command list (one line).

## Acceptance criteria (hard)

1. `./bin/agentic gain --adoption --last 20` runs on this machine and prints an adoption
   block with `bash calls` > 0.
2. `./bin/agentic gain --adoption --json --last 5 | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'adoption' in d and d['adoption']['bash_total'] >= 0; print('ok')"`
   prints `ok`.
3. `./bin/agentic gain --last 5 --json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('adoption') is None; print('ok')"`
   prints `ok` (zero cost / zero schema noise when the flag is off).
4. `go test ./internal/gain/ ./internal/hook/ ./cmd/agentic/` passes, including the new
   fixture test with exact-tally assertions.
5. `shellGuard` routes through `Classify` (no duplicated decision logic — verify by
   reading the diff), and all pre-existing hook tests pass unchanged.
6. `telemetry/README.md` and `SETUP.md` mention `--adoption`.
7. Diff touches only: `internal/hook/hook.go`, `internal/hook/hook_test.go`,
   `internal/gain/gain.go`, `internal/gain/gain_test.go`, optionally
   `cmd/agentic/main.go`, `telemetry/README.md`, `SETUP.md`.

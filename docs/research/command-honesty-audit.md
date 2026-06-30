# Command honesty audit — `agentic` CLI + install/hook surfaces

> Prompted by a concern about whether `agentic gain` is honest. Audited `gain` and every
> other user-facing command (inject/eject/status/link, the shell-guard hook, the merge
> commands, doctor, gate, install) for **correctness** and **honesty** (output or docs that
> overclaim/mislead). The `gain` math was verified by independent recomputation from raw
> transcripts; the other commands by four parallel read-only audits, each finding cross-checked.

## `agentic gain` — verified, then made honest

**Math: correct.** An independent recomputation from the raw `~/.claude` transcripts matched the
binary to the cent on every field (cache_hit_rate 0.9792, input_cost_saved $3899.90, est_cost
$700.25). No arithmetic bug.

**Honesty: two real problems, both fixed.**

1. **It hid the actual bill and showed only the flattering counterfactual.** The readout printed
   `input cost saved : $3899.90 (87%)` but never the **actual** input-side cost (`$621.87`). The
   "saved" figure is a counterfactual against *caching disabled* — ~6× the real bill. Fixed:
   `Report` now exposes `input_cost_real_usd`, and the render leads with `input bill (actual)`
   next to a relabeled `cache avoided (vs re-sending uncached)`.
2. **It over-attributed the saving to the config.** The package framed this as *"what is this
   config actually saving?"* — but prompt caching is a **Claude platform feature** that works in
   any session, with or without agentic-cfg. Fixed: the doc, the header ("session token economy"),
   and an in-output `note:` now state that caching is the platform's, that agentic-cfg's lever is
   only cache hygiene (a warm prefix), and that the config's *own* effect is measured by the A/B
   benchmark (`evals/swe_bench.py`), not this readout.

Also fixed: the `gain --gate` `--min-tokens` default was `50000` while the `telemetry/gate.py` it
claims to "mirror" defaults to `200000` — a 4× divergence in the skip threshold. Aligned to 200k.

## Other commands — fixed this pass

| Command | Severity | Issue → fix |
|---|---|---|
| `doctor` | high | Printed "All checks passed" + exit 0 even when the skills symlink pointed nowhere (warn-not-fail). Now counts warnings and reports "Passed with N warning(s)"; 0 skills is a fail. |
| `inject`/merge (Go + Py) | high | `claudemd.go` and `merge-claude-md.py` wrote CLAUDE.md with a plain truncating write — an interrupted write could empty the user's file. Both now write atomically (temp + fsync + rename), matching the JSON path. |
| `install` | med | The `claude` CLI rewrites `~/.claude.json` (MCP) in place; install backed up CLAUDE.md and settings but not this file. Added `backup_once ~/.claude.json`. |
| `mcpmerge` (eject) | med | `RemoveClaudeUser` printed "Removed N" unconditionally regardless of whether the CLI removals succeeded. Now reports only servers actually removed, and lists any "already absent or not removed". |

## Other commands — deferred (documented, not yet fixed)

These are real but either narrow-scenario or carry enough regression risk that they deserve their
own focused change rather than riding along here.

- **shell-guard false-positive denies (high).** `internal/hook/hook.go:110` matches a code
  extension *anywhere* in the command, so `grep TODO.go notes.txt` (literal text search in a
  non-code file) and `cat main.go | grep foo` (text filter over a pipe, no grep file arg) are
  **denied** with a message claiming the grep is structural code search — which is false. Fix needs
  scoping the extension test to a file *argument* in the *same pipeline segment* as grep, with
  parity in `shell-guard.sh` and new test cases — deferred to avoid rushing the core deny heuristic.
- **eject skills-symlink canonicalization (high, narrow).** `internal/lifecycle/lifecycle.go`
  compares the recorded symlink target to `skillsSource()` without `EvalSymlinks`, so an install
  via a symlinked `--root` then eject via the canonical path leaves the skills symlink behind and
  makes `status` report a false negative. Needs canonicalizing both sides before comparing.
- **eject permissions residue (med).** `settings.Unmerge` leaves `permissions:{allow:[],deny:[]}`
  behind (inject adds an empty `deny`, eject doesn't remove the now-empty `permissions` key) —
  mirror `unmergeHooks`'s empty-key deletion.
- **parity test is order-blind (med).** `internal/installtest/parity_test.go` compares Go vs Python
  merge output with `reflect.DeepEqual` over order-discarding maps, so a key-ordering drift (the
  whole reason `jsonorder` exists) would pass. Compare canonical bytes too.
- **Low:** `CODE_EXT` omits `.sh`/`.bash` (code greps on shell scripts slip the guard);
  `shell-guard.sh extract()` takes the first `"command"` key anywhere (Go path immune); a dead
  `PowerShell` branch; `doctor` MCP check is a substring grep, not JSON-aware; the `npx` remediation
  hint points at `secrets/.env`, which this script doesn't read; `Unmerge` lacks a `DRY_RUN` gate;
  `jsonorder.WriteFile` skips the `fsync` the Python path does.

## What stayed clean (verified, no action)

The merges genuinely preserve user content (env, hooks, `permissions.allow/deny`, user MCP servers,
hand-written CLAUDE.md) on both the Go and Python paths; `$schema` handling is correct (no
`"$schema": null` bug); the shell-guard fail-open invariants, double-wrap guard, and the
leading-`VAR=` passthrough fix all hold; the `gain --gate` skip-vs-fail logic is correct and the
"insufficient data" case is honestly labeled `SKIP`, not `PASS`; `backup_once` never re-clobbers an
existing `.bak`; and `set -euo pipefail` plus non-zero-returning merge tools mean a failed install
step aborts before "Install complete." prints.

# GitNexus: keep or remove — evidence and verdict

Office-hours vet (all six — this is a keep/remove decision), run 2026-07-02 as a live
investigation with measurements on the primary machine. Companion wave:
[00-INDEX.md](00-INDEX.md).

## The ask

> "Fix the GitNexus problem, verify with tests that the tool actually helps agents,
> and if it doesn't — remove it from the repo."

## Q1 — Premise challenge

"GitNexus is unused (1 call / 50 sessions) → maybe remove it" is the wrong frame:
the tool was **unusable**, not unused, for the whole measured window:

1. **The MCP server has been dead since 2026-06-24.** Commit `0792364` pinned
   `gitnexus@1.6.8`; that release declares `engines: {"node": ">=22.0.0"}` while the
   machine's only Node is v20.12.2 (`/usr/local/bin/node`). The CLI crashes on import
   (`SyntaxError: The requested module 'commander' does not provide an export named
   'Command'`), so `claude mcp list` shows `gitnexus … ✘ Failed to connect`. Every
   session since the pin had zero graph tools. Before the pin, `@latest` resolved to a
   cached **1.6.7**, which starts fine on Node 20 (handshake verified:
   `serverInfo {"name":"gitnexus","version":"1.6.7"}`).

   **Refinement (same day):** the outage had *two* layers. The `engines.node >=22`
   mismatch was real but advisory; the actual crash trigger was a **corrupt npx
   cache** (`~/.npm/_npx/1aef5872f6ce4e6c`, created 2026-06-30 — `commander`
   resolved without its named exports there on Node 20 *and* Node 26 alike). After
   `rm -rf` of that cache dir, `npx -y gitnexus@1.6.8 --version` → `1.6.8` on Node
   26, and the MCP server handshakes in 2.4 s. Operator decision: install a current
   Node locally (`brew install node` → v26, resolving ahead of the old system Node
   on PATH) and track the latest gitnexus release instead of freezing on `1.6.7`.
   The doctor start-check from this wave catches both failure modes, so it stays
   exactly as shipped.
2. **No working repo was indexed.** `~/.gitnexus/registry.json` shows exactly one
   index ever built: `Omni`, 2026-06-15 (430 files, 5,442 nodes) — proof of real prior
   use, and consistent with the single MCP call the audit found. `agentic-cfg` itself
   was never indexed until this investigation (`analyze` took 3.6s: 2,185 nodes,
   4,201 edges, 119 flows).
3. **The per-call hooks were misattributed to this repo.** `gitnexus-hook.cjs` and its
   `settings.json` entries were self-installed by `gitnexus setup` (upstream), not by
   `bin/install.sh` — the repo's only references to the hook are in the audit doc.
   Measured cost: 80–140 ms per Grep/Glob/grep-Bash call in a non-indexed repo,
   210–380 ms in an indexed one (the 10 s figure in the audit was the timeout ceiling,
   not the observed latency).

## Q2 — Status quo

The enforced baseline (ast-grep + Read, shell-guard denying grep-on-code) can answer
structural questions correctly — see the A/B below. What it cannot do is answer them
*cheaply*: the baseline arm resorted to full-file reads and a long tail of ast-grep
pattern trial-and-error (`hook.$SYM` never matched; qualified-identifier patterns are
an ergonomic hole in `sg`).

## Q3 — Evidence of value (the tests)

A/B test, 2026-07-02: two read-only Sonnet agents, identical three structural
questions about this repo (callers/callees of `hook.Classify`; blast radius of
`gain.Render` signature change; exported `internal/hook` symbols used by
`internal/gain`), graded against ground truth established independently beforehand.
Arm G was pointed at the GitNexus CLI (`context`/`query`, 1.6.7, index built); arm B
was restricted to ast-grep + Read.

| Metric | Arm G (GitNexus) | Arm B (baseline) | Δ |
|---|---|---|---|
| Correctness | 3/3 | 3/3 | tie |
| Tokens | 63,433 | 82,312 | **+30% for baseline** |
| Tool calls | 35 | 45 | +29% |
| Wall time | 138 s | 225 s | **+63% for baseline** |

The graph produced the correct skeleton of every answer in its first 4 calls
(`context Classify`, `context Render`, …); the rest of arm G's calls were the
prompt-mandated manual re-verification. Hook `augment` output in an indexed repo is
the same caller/callee/flow digest injected for free into grep-style searches —
i.e. exactly the context that saved arm G its tokens.

Honest caveats: n=1 per arm; small repo (2.2k nodes — on larger codebases the
full-file-read baseline should fall further behind, unverified); correctness did not
differ, so the measured value is efficiency, not rescue; arm G was handed the exact
CLI invocations (the MCP schema + skill normally carry that discovery).

## Q4 — Narrowest wedge (the verdict)

**KEEP + FIX.** The user's removal condition ("if tests show it doesn't help") is not
met — the tests show a ~23% token / ~39% time saving at equal correctness once the
runtime works. The wedge, in this wave:

1. Pin the version everywhere it is spelled and track upstream stable releases (the
   pin now follows `1.6.8`, on Homebrew Node ≥22 — it ships multiple RCs per day as
   of 2026-07-02); a `doctor.sh --deep` Node floor check enforces the machine
   requirement instead of a version freeze.
2. Make `doctor.sh --deep` actually **start** the registered MCP server and require a
   successful `initialize` handshake — the check that would have caught this outage
   the day the pin landed (today it only greps the pin string and validates JSON).
3. Hygiene: `.gitnexus/` into `.gitignore`; file the upstream bug (`~/.gitnexus`
   registry dir false-positives `findGitNexusDir`, causing per-commit "index is
   stale (last indexed: never)" nags and wasted `augment` spawns in every repo under
   `$HOME`).
4. Truth pass on the skill/docs: the skill's MCP claim is stale (Claude reads
   user-scope servers from `~/.claude.json`, not `~/.claude/.mcp.json`), and it should
   carry the pinned CLI fallback + "check the index exists" gate that made arm G work.

Out of scope, recorded: machine Node upgrade (user decision; unlocks tracking
upstream); adopting or removing upstream's self-installed hooks (upstream-owned files
in `~/.claude`; revisit after the upstream bug report); auto-indexing repos at
install time.

## Q5 — Risk & verification

Blast radius: config-only (no Go code changes). Gates: the standard four
(test/ci-check/evals-lint/prefix-budget — prefix untouched, byte total must not
move) **plus** `bin/install.sh --provider all && bin/doctor.sh --deep` on the
implementing machine, which now proves the server really starts, and a live
`claude mcp list` showing `gitnexus … ✔ Connected`.

## Q6 — Cost of keeping, and the removal trigger

Costs: 13 MCP tools ≈ 6.4k tokens of schema per session in clients that preload
schemas (Cursor; Claude Code defers via ToolSearch, ≈ free until used); 80–380 ms
hook latency per matching tool call (upstream's hooks); one pinned npm package that
upstream's engine floor will eventually strand (Node-22 note above).

**Removal trigger (measurable):** `agentic gain --adoption` counts gitnexus MCP
calls. If, with the server verifiably healthy and working repos indexed, the counter
is still ~0 after the next ~30 sessions, open a removal wave (`gitnexus uninstall`
reverses the upstream hooks/skills; drop `integrations/gitnexus/`, the skill, the
precedence-table row, and the doctor checks). Re-run the A/B protocol above if the
efficiency claim itself is doubted.

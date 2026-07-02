# Plan 09 — docs sweep: kill every verified-stale claim

[Index](00-INDEX.md) · Wave D (after all code plans) · Files: `README.md`,
`ARCHITECTURE.md`, `SETUP.md`, `TESTING.md`, `CHANGELOG.md`,
`integrations/lean-ctx/README.md`, `integrations/gitnexus/env.example`
(delete), `catalog/plugins.yaml`, `plans/00-master-plan.md`,
`plans/IMPROVEMENT-LOOP.md`, `.github/workflows/ci.yml` (only if the macOS
matrix decision below says so — default NO change).

Every item below was verified against the working tree on 2026-07-01. This
plan is surgical text fixes — do NOT restructure documents beyond what an item
says, and do not "improve" adjacent prose.

## Items

### README.md
1. Provider table: Claude MCP path `~/.claude/.mcp.json` → `~/.claude.json`
   (user scope; PORT-03). Check the whole file for other `.mcp.json` mentions.
2. Drop "Claude Desktop" from the support claims (resolved decision D4 —
   nothing installs Desktop config). Mention Claude Code only.
3. "Set `NPX` for your machine" → note it is auto-detected; `secrets/.env`
   overrides only.
4. The ci-check description "(shell, JSON, YAML, frontmatter, eval lint +
   self-test)" → enumerate the real sections (links, hooks self-tests, merge
   helpers, swe-bench selftest, memory seeds, prefix budget, Go fmt/vet/test/build).

### ARCHITECTURE.md
5. Mermaid + prose: `~/.claude/.mcp.json` → `~/.claude.json`.
6. "The canonical path is `~/Documents/GitHub/personal/agentic-cfg`" → replace
   with "the repo can live anywhere; docs refer to `<your clone>`" (keep
   consistency with lines ~84–85 which already say path-independence).
7. Directory map: add rows for `cmd/` + `internal/` (Go CLI: hook, merges,
   inject/eject/status/link, gain/cache), `telemetry/`,
   `providers/claude/hooks/` (shell-guard, edit-lint),
   `providers/shared/merge-claude-md.py`, `bin/prefix-budget.sh`,
   `bin/check-links.py`. One line each, match existing table style.
8. Bootstrap dependency list: add ast-grep, go, no-mistakes, and the
   `bin/agentic` build.
9. CI paragraph: mention the golangci-lint job as well.

### SETUP.md
10. Same canonical-path fix as item 6 (the `cd` example must use a placeholder
    or `~/Documents/GitHub/agentic-cfg`).
11. "CI … not pushed yet" (~151–152) → CI is live on master
    (`.github/workflows/ci.yml`, commit 061517b); rewrite accordingly.
12. Manual dependency path: add `ast-grep` and `go` so doctor --deep matches.
13. Drop Claude Desktop claim (see item 2).

### TESTING.md (surgical, not a rewrite)
14. Replace ALL hardcoded volatile counts with "run the command" phrasing:
    "15 single-transcript cases" (now 17+), the 15-row case table (point to
    `ls evals/cases`), "lint OK — 18 cases, 8 skills", "selftest OK — 8
    checks", "26 Go tests, 6 packages" (now 9 packages; say `go test ./...`),
    "Two value cases exist".
15. "`cmd/agentic` has no test files" → delete (main_test.go exists).
16. `cmd/agentic` dispatch list: add `gain`, `cache`, `inject`, `eject`,
    `status`, `link`.
17. Sections claiming CI "is not committed on master" / "CI is therefore not
    active" (~193–198, ~595) → rewrite to the live-CI reality.
18. Where the doc embeds the 2026-06-26 experiment tables duplicated from
    `plans/06-overhead-and-uplift.md`, replace the tables with a pointer to
    that file (keep one-sentence summaries). Do not delete sections 1–2 / 8–9
    (layer model, fail-open semantics, honesty caveats — they stay).
19. Add one line to the evals section noting the 2026-07-01 harness changes:
    metric track included in `--track all`, transcripts persisted, fail-closed
    judge (cross-link `plans/review-fixes/07-evals-harness-hardening.md`).

### CHANGELOG.md
20. Add a `0.13.0 — 2026-07-01` entry covering (bullet each, one line):
    inject/eject/status/link CLI, `agentic gain`/`cache`, CI workflow +
    golangci-lint gate, edit-lint hook + shell-syntax check, `AGENTIC_TIER`,
    prefix-budget gate, `model-orchestration` + `no-mistakes` skills, and this
    review wave (shell-guard fallback fix, anchored matchers, settings-merge
    idempotency, evals arm isolation + harness hardening, always-on diet
    (terminal-rtk folded into AGENTS.md), cursor merge/eject, docs sweep).
    Group under Added/Fixed/Changed per the file's existing style.

### integrations
21. `integrations/lean-ctx/README.md`: the "Claude equivalent … is a follow-up"
    paragraph → it shipped (settings.hooks.json + install_settings); fix the
    `.mcp.json` path; ADD a short "Context cost" note: the server injects a
    tool-mapping instruction block into every session; `AGENTIC_TIER=weak`
    installs without lean-ctx (now truly removing it — plan 06).
22. Delete `integrations/gitnexus/env.example` (nothing reads it; contradicts
    auto-detection). If its README references it, fix.

### catalog/plugins.yaml
23. Fix the `mongodb-mcp-setup` pointer: name the actual bundled skill or
    rephrase to "the plugin's own setup skill". Add a header comment line:
    this catalog is documentation; only YAML validity is machine-checked.

### plans/
24. `plans/00-master-plan.md`: status header "P2 next" → P2 shipped (CI,
    token-delta metrics, Haiku on/off eval, populated-HOME fixture); P3
    partially (prefix budget = W2). Point remaining-open items at reality
    (release tags MAT-06 still open; subagent-skill measurement still open).
25. `plans/IMPROVEMENT-LOOP.md` "Backlog source" → repoint
    `plans/03-gaps-and-bugs.md` → `archive/03-gaps-and-bugs.md`.

### CI (decision, default: document-only)
26. Do NOT add a macOS runner in this plan (cost/flake tradeoff is the user's
    call — the master plan promised it; record it as still-open in item 24
    instead). ci.yml itself: no changes here (plan 06 already surfaced
    test output via ci-check).

### References to artifacts removed by this wave (added 2026-07-02)
27. The `terminal-rtk` skill was deleted (folded into AGENTS.md Global
    default 2, hook-enforced). Fix `TESTING.md:347` (its value-case example
    names `terminal-rtk`): rephrase the example to reference the retired case
    historically ("the since-retired terminal-rtk case…") or swap the example
    to `ast-grep-structural-precision`. Check for other terminal-rtk mentions
    in README/SETUP/docs/ and adjust the same way (historical mentions in
    plans/, archive/, evals/BENCHMARKS.md stay).
28. `providers/cursor/mcp.overlay.json` was deleted and the overlay concept
    removed from merge-mcp. Fix `ARCHITECTURE.md:58` (directory-map row —
    describe merge-mcp as "builds provider mcp.json from fragments; managed-
    server sidecar removes stale entries") and `ARCHITECTURE.md:89`
    ("fragments plus the Cursor overlay" → fragments only; mention the
    `~/.cursor/.agentic-managed.json` sidecar and `--eject` in one line each).

## Acceptance criteria

1. `python3 bin/check-links.py` (or however ci-check invokes it) passes.
2. Zero matches for each of these greps across tracked files (excluding
   `archive/`, `plans/` history files other than the two edited, and
   `splunk-antifraud-observability/`):
   - `grep -rn 'personal/agentic-cfg' README.md ARCHITECTURE.md SETUP.md TESTING.md core/ integrations/ catalog/`
   - `grep -rn '\.claude/\.mcp\.json' README.md ARCHITECTURE.md SETUP.md TESTING.md integrations/`
   - `grep -rn 'not pushed\|not active on the remote\|not committed on' TESTING.md SETUP.md`
   - `grep -rn 'Claude Desktop' README.md SETUP.md`
   - `grep -rn '18 cases\|15 single-transcript\|26 Go tests\|selftest OK — 8\|has no test files' TESTING.md`
3. `grep -c '0.13.0' CHANGELOG.md` ≥ 1 and the entry sits above 0.12.1.
4. `ls integrations/gitnexus/` has no `env.example`.
5. `bash bin/ci-check.sh` exits 0 (YAML/frontmatter/links all green).
6. `git status` touches only header files.
7. `grep -n 'terminal-rtk' TESTING.md README.md SETUP.md` → only historical
   phrasings (or zero); `grep -n 'overlay' ARCHITECTURE.md` → zero matches
   describing a live overlay file.

## Out of scope

Full TESTING.md restructure/diet to 15–20KB (only the surgical items above).
Release tags. macOS CI runner.

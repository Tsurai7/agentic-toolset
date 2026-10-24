# Review-fixes plan index (2026-07-01)

Source: full-repo review (5-agent audit, session 2026-07-01). Goal of the wave:
close every confirmed defect and cut the always-on token payload ~35% without
losing behavior. Each plan below is self-contained, has hard acceptance
criteria (AC), and names its file scope so plans in the same wave never touch
the same file.

## Execution waves (order is mandatory)

| Wave | Plans | Parallel? | Why this order |
|------|-------|-----------|----------------|
| A | [01-shell-guard-fallback](01-shell-guard-fallback.md), [04-evals-arm-isolation](04-evals-arm-isolation.md) | yes | Disjoint files. 04 must land before 07 (both touch `evals/overhead.py`, `evals/swe_bench.py`). |
| B | [02-hook-matchers-and-edit-lint](02-hook-matchers-and-edit-lint.md), [03-settings-merge-idempotency](03-settings-merge-idempotency.md), [07-evals-harness-hardening](07-evals-harness-hardening.md), [08-cursor-parity](08-cursor-parity.md) | yes | Disjoint files. 08 must land before 06 (both touch `providers/shared/merge-mcp.py`). |
| C | [05-always-on-layer](05-always-on-layer.md), [06-install-pipeline-hardening](06-install-pipeline-hardening.md) | yes | 06 edits `bin/install.sh` + `bin/ci-check.sh` after 01 did; 05 edits `core/**` only. |
| D | [09-docs-sweep](09-docs-sweep.md) | solo | Docs must describe the post-fix state. |
| E | [10-machine-apply-and-cleanup](10-machine-apply-and-cleanup.md) | solo, supervised | Applies the rendered result to the live machine; depends on 01,02,03,05,06. |

## Status

- [x] 01 shell-guard fallback corruption (wave A) — done 2026-07-01, all AC pass; deviation: "denied" fixtures use extension-bearing paths per the pre-existing BUG-03 extension gate
- [x] 04 evals control-arm isolation (wave A) — done 2026-07-01, all AC pass incl. live contrast probe; keychain→.credentials.json materialization added for CLAUDE_CONFIG_DIR auth
- [x] 02 hook matchers + edit-lint (wave B) — done 2026-07-01, all AC pass; deviation: no `--` after `python3 -c` (breaks sys.argv), verified
- [x] 03 settings merge idempotency (wave B) — done 2026-07-01, all AC pass; Go+Python byte-identical on the dup fixture
- [x] 07 evals harness hardening (wave B) — done 2026-07-01, all AC pass; selftest 9→17 checks; --rejudge added; judge_cmd/model recorded in artifacts
- [x] 08 cursor parity (wave B) — done 2026-07-01, all AC pass in fake HOME; GAP: sidecar logic is Python-only and the built `bin/agentic` shadows it → ported to Go via plan 06 change 9 (added)
- [x] 05 always-on layer diet (wave C) — done 2026-07-02; agent died on API error ~90% through, orchestrator finished (budget ratchet 11300→9054) and verified all AC: prefix source 11232→8754 B, phantom tools 0, lint OK 19/8. Note: core/skills/no-mistakes/ is gitignored, so its description edit is invisible to git — verified on disk.
- [x] 06 install pipeline hardening (wave C) — done 2026-07-02 (relaunched after first agent's API death); all 10 AC pass; Go sidecar parity ported (change 9), found+fixed Go `null`-vs-`[]` sidecar marshal bug; AC10's literal test path corrected to internal/installtest (pre-existing layout).
- [x] 09 docs sweep (wave D) — done 2026-07-02 (Haiku); all 28 items + 7 AC; orchestrator corrected three overstated CHANGELOG lines (token-savings figure, "idempotent via atomic writes", "registration now atomic") and the master-plan P2 status afterwards.
- [x] 10 machine apply + cleanup (wave E) — DONE 2026-07-02 via option 1 (user's call): `codebase-memory-mcp` server deregistered (restore: `claude mcp add codebase-memory-mcp /Users/tsurai/.local/bin/codebase-memory-mcp`), cbm hook entries removed, install re-applied anchored/deduped groups, /tmp markers purged, plugin skill dupes disabled in manifest. Backups: `*.bak-opt1-20260702113932` + earlier `*.bak-reviewfix-20260702111837`. Historical note below kept for the root cause.
  - Previous status: PARTIAL 2026-07-02. Durable: rebuilt `bin/agentic`, both installs applied (`generated.md` 11,232→8,866 B on the machine), `/tmp` cbm markers purged, doctor --deep clean. NOT durable: cbm-hook removal + plugin-skill disable — executed correctly twice, reverted each time. ROOT CAUSE (verified via binary strings): `codebase-memory-mcp` embeds the `~/.claude/settings.json` path + both cbm hook filenames and re-installs them on every server start (no opt-out env flag exists in the binary); lean-ctx likewise self-registers its redirect/rewrite entries. Any settings.json cleanup lasts only until the next session starts those MCP servers. Resolution needs a user decision (drop the server, neuter the hook files, or upstream a no-hooks flag) — ready-to-run scripts: scratchpad `remove_cbm_hooks.py`, `disable_dup_skills.py`. settings.json restored to its pre-wave backup for consistency; re-running `bin/install.sh --provider claude` at any time re-applies the anchored/deduped repo-managed groups.

## Global acceptance (checked after every wave, again at the end)

1. `bash bin/ci-check.sh` exits 0, all sections `OK`.
2. `go test ./... -count=1` — all packages `ok`.
3. `golangci-lint run` — no issues.
4. `git status` shows only files named in the executed plans (no stray edits).

## Review findings → plan mapping

| Finding (review shorthand) | Plan |
|---|---|
| shell-guard fallback corrupts multi-line commands; grep-token regex hits argument position; install never builds `bin/agentic` | 01 |
| Unanchored hook matchers + blanket `allow` from `lean-ctx hook redirect`; edit-lint litters `__pycache__`; edit-lint test payload shape wrong | 02 |
| `isManagedGroup` misses absolute-path lean-ctx commands → duplicate hook groups | 03 |
| Evals OFF/control arm inherits hooks + CLAUDE.md + MCP → A/B self-measurement | 04 |
| ~3.1–3.7k always-on tokens; 4× verification dup, 3× rtk dup, dead links, phantom `ctx_semantic_search`/`ctx_compose`, `.mdc` contradiction, over-broad triggers, wrong canonical path in cursor pointer | 05 |
| Non-atomic `agentic-cfg.generated.md` writes; non-transactional MCP register; weak tier doesn't remove lean-ctx; sed escaping; jsonorder fsync/mode; merge-settings null crash; CI output discarded; doctor false-OKs | 06 |
| Judge fail-open TIE→PASS; `result_error` unused; judge-prompt injection; transcripts discarded; `report.py` wipes BENCHMARKS; `--track all` skips metric; same-day overwrite; dead `n` field; overhead None→pass | 07 |
| Cursor `hooks.json` clobbered; add-only MCP merge accretes stale servers; dangling rule symlinks; no eject | 08 |
| TESTING/SETUP/README/ARCHITECTURE/CHANGELOG/plan-status/integration-README staleness | 09 |
| Live `~/.claude/settings.json` duplicate hooks; cbm-* hooks (96 wasted round-trips, ~230 tok/session); anthropic-skills duplicate skills; stale `/tmp` gate files | 10 |

## Deliberately deferred (not in this wave)

- `communication.md` split into portable core + Cursor-only citation format — needs
  per-provider render machinery in `install_claude_md`; low token yield (~60 words).
- `__PATH__` baking in `integrations/gitnexus/mcp.stdio.json` (1,175-char PATH
  snapshot) — fix requires a launcher-script approach and a live server relaunch
  test; risk of breaking gitnexus outweighs the staleness cost today.
- Re-running the full value A/B + overhead benchmarks after 04 — costs real API
  tokens; run manually via `evals/PLAYBOOK.md` when desired. Until re-run,
  BENCHMARKS rows carry the caveat added by plan 04.
- Git release tags (MAT-06) — needs a push decision, out of scope for a working-tree wave.

## Conventions for implementing agents

- Follow repo coding principles: smallest correct diff, match existing style, no
  drive-by refactors. Do NOT commit — leave changes in the working tree.
- Every plan's AC is the definition of done. If an AC cannot be met, stop and
  report the blocker instead of improvising around it.
- If a PreToolUse hook blocks a Read/Grep once, retry the same call — it passes on retry.

# gitnexus-fix — wave index

Fix wave for the 2026-07-02 GitNexus investigation. Evidence and the keep/remove
verdict: [DESIGN.md](DESIGN.md) (verdict: **keep + fix**; removal trigger defined
there).

## Plans and status

| # | Plan | Files touched | Status |
|---|------|---------------|--------|
| 01 | [Re-pin to a runtime-compatible version + doctor MCP start check](01-repin-and-doctor.md) | `integrations/gitnexus/mcp.stdio.json`, `integrations/gitnexus/README.md`, `bin/mcp-start-check.py` (new), `bin/doctor.sh`, `SETUP.md`, `CHANGELOG.md` | done |
| 02 | [Hygiene: .gitignore + upstream stale-nag bug report](02-hygiene-and-issue.md) | `.gitignore`, `issues/gitnexus-home-registry-stale-nag.md` (new) | done |
| 03 | [Skill/docs truth pass: MCP claim, CLI fallback, index gate](03-skill-truth-pass.md) | `core/skills/gitnexus-navigation/SKILL.md` | done |

## Execution order

- **Wave A (parallel):** 01, 02, 03 — file sets are disjoint.
- **Verify:** gates below + per-plan acceptance criteria, checked against the actual
  diff by a verifier that changes nothing.

## Verification gates (all must pass before merge)

```bash
go test ./...
bash bin/ci-check.sh
python3 evals/lint.py
bash bin/prefix-budget.sh   # byte total unchanged — no always-on files in this wave
```

Machine-side (implementing machine, after the diff):

```bash
bash bin/install.sh --provider all   # re-registers gitnexus@1.6.7
bash bin/doctor.sh --deep            # now includes the MCP start/handshake check
claude mcp list                      # gitnexus … ✔ Connected
```

## Deferred follow-ups (out of this wave, see DESIGN.md Q4/Q6)

- Machine Node ≥22 upgrade → unpin from 1.6.7 and track upstream.
- Upstream self-installed hooks (`~/.claude/hooks/gitnexus/`): keep/adopt/remove —
  revisit after the filed upstream bug moves.
- Removal trigger: `agentic gain --adoption` gitnexus count still ~0 after ~30
  sessions with a healthy server and indexed repos → removal wave.

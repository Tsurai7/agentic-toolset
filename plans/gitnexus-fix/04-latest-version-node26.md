# 04 — Operator decision: latest gitnexus (1.6.8) on Homebrew Node, not a 1.6.7 freeze

**Rationale:** after plan 01 shipped the 1.6.7 re-pin, the operator chose the other
fork of the tradeoff: install a current Node locally and track the latest gitnexus
release. Machine state as of 2026-07-02 (all verified live):

- `brew install node` → Node **v26.4.0** + npm 11.17.0 at `/opt/homebrew/bin`,
  resolving ahead of the old `/usr/local/bin` Node 20 on PATH.
- **Root-cause refinement:** the 1.6.8 outage had *two* layers. The `engines.node
  >=22` mismatch was real but advisory; the actual crash came from a **corrupt npx
  cache** (`~/.npm/_npx/1aef5872f6ce4e6c`, created 2026-06-30 — `commander` resolved
  without its named exports there on Node 20 *and* Node 26 alike). After `rm -rf` of
  that cache dir, `npx -y gitnexus@1.6.8 --version` → `1.6.8` on Node 26, and the MCP
  server handshakes in 2.4 s (`serverInfo {"name":"gitnexus","version":"1.6.8"}`,
  serving Omni + agentic-cfg). The doctor start-check from plan 01 catches **both**
  failure modes, so it stays exactly as shipped.

## Change specification

All edits are version-string and prose updates on top of the already-committed wave
(branch `feat/gitnexus-fix`); the mcp-start-check helper and doctor wiring do not
change.

1. `integrations/gitnexus/mcp.stdio.json` — `gitnexus@1.6.7` → `gitnexus@1.6.8`.
2. `integrations/gitnexus/README.md` — rewrite the "Version pin" section: pinned to
   the latest stable (`1.6.8`); requires Node ≥22 (`engines`), satisfied by Homebrew
   Node (`brew install node`, currently v26); bump procedure = update the pin here +
   `SETUP.md` + the `gitnexus-navigation` skill, re-run `bin/install.sh`, then
   `bin/doctor.sh --deep`; note the corrupt-npx-cache failure mode and its remedy
   (`rm -rf` the offending `~/.npm/_npx/<hash>` dir — the doctor start-check's stderr
   names the path). Also update the pinned `analyze` line in Setup step 3.
3. `SETUP.md` — both `gitnexus@1.6.7` occurrences → `gitnexus@1.6.8`; adjust the
   pin-explanation sentence: requirement is Node ≥22 (`brew install node`); keep the
   "pin for reproducible installs" rationale (do not switch to unpinned `@latest`).
4. `core/skills/gitnexus-navigation/SKILL.md` — every `gitnexus@1.6.7` → `1.6.8`
   (5 occurrences). Frontmatter `description` stays byte-identical (versions appear
   only in the body).
5. `bin/doctor.sh` — in the deep section, immediately before the MCP start check,
   add a Node floor check: resolve `node` from PATH; if missing or major version
   < 22 → `fail "node <version-or-missing> — gitnexus requires Node >=22 (brew
   install node)"`, else `ok "node <version> (>=22)"`. Keep it POSIX-bash in the
   file's existing style; shellcheck must stay clean (ci-check runs it).
6. `CHANGELOG.md` — update the `[0.14.1]` entry (it is unreleased, on this same
   branch) to the final resolution: pin to latest `gitnexus@1.6.8`, machine Node
   baseline ≥22 via Homebrew, doctor `--deep` MCP start/handshake check, both root
   causes named (advisory engines mismatch + corrupt npx cache as the trigger).
7. `plans/gitnexus-fix/DESIGN.md` — in Q1 finding 1, append a short **Refinement
   (same day)** paragraph with the two-layer root cause and the operator decision
   (latest + Homebrew Node instead of the 1.6.7 freeze); update Q4 wedge 1's wording
   accordingly (pin tracks latest stable; Node floor is a doctor check). Do not
   rewrite history elsewhere — the A/B evidence and verdict sections stand.
8. `plans/gitnexus-fix/00-INDEX.md` — deferred list: replace the "Machine Node ≥22
   upgrade → unpin from 1.6.7" bullet with "Track upstream stable releases; bump the
   pin per integrations/gitnexus/README.md procedure". Leave plan statuses as they
   are; add a row for this plan (status: pending until verified).

## Acceptance criteria (hard)

1. `grep -rn 'gitnexus@' integrations/ SETUP.md bin/ core/skills/gitnexus-navigation/`
   → every hit is `gitnexus@1.6.8`; zero `1.6.7` remain in those paths.
2. `git diff` on `core/skills/gitnexus-navigation/SKILL.md` vs `HEAD` shows no
   frontmatter change (lines 1–7); file still ≤75 lines.
3. `bash bin/doctor.sh --deep` exits 0 and prints BOTH `node v26` (or the actual
   ≥22 version) OK line AND the `gitnexus MCP server starts` OK line — run
   `bash bin/install.sh --provider all` first so `~/.claude.json` re-registers with
   the new npx/pin, and include the resulting registered `command` + `args` from
   `~/.claude.json` (via `python3 -c` json read) in your report: expect
   `/opt/homebrew/bin/npx` + `gitnexus@1.6.8`.
4. `python3 bin/mcp-start-check.py /Users/tsurai/.claude.json gitnexus 30` → exit 0,
   prints version `1.6.8`.
5. `bash bin/ci-check.sh` passes; `bash bin/prefix-budget.sh` byte total 8754
   (unchanged); `python3 evals/lint.py` still `22 cases, 10 skills covered`.
6. Diff (vs HEAD) touches only the eight files listed in the change specification.

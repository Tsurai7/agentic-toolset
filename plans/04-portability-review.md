# 04 — Portability & Co-existence Review

> One of five parallel planning docs. **This doc owns: GENERIC-ness / portability.**
> Specifically (1) correctness across **Cursor**, **Claude Code**, and **Claude
> Desktop/API** as three distinct config consumers, and (2) clean, **non-destructive
> install on another machine** — both a clean machine and one where the user already
> has their own `CLAUDE.md` / `settings.json` / `.mcp.json` / cursor rules / hooks.

## Scope & ownership

| I own | I defer |
|-------|---------|
| Provider coverage/correctness; the merge-vs-overwrite **co-existence** verdict per destination; OS/shell (macOS/Linux/Windows) compat; canonical-path & personal-identity coupling; adoptability by another user; the portability **requirements** a Go binary and the test suite must satisfy. | Generic logic bugs not about portability → **03-gaps-and-bugs** (I cross-link the portability-flavored ones). Go-binary design → **01-go-rewrite**. Overall maturity/roadmap → **02**. Test *implementation* → **05** (I hand it the portability scenarios to cover). |

**Evidence basis.** Every clobber verdict below was traced by running the actual
merge scripts (`merge-settings.py`, `merge-mcp.py`) and replicating `install_claude_md`
against a throwaday `$HOME` fixture under `/tmp` — never against the real `$HOME`.
Where I only read code without executing it, I label the claim *inferred*.

---

## A. Provider × destination co-existence matrix

For each write the installers perform: does it **merge** or **overwrite**, are
pre-existing **user entries preserved**, is a **backup** taken, and the verdict.

| Provider | Destination | Mechanism (file:line) | Merge / Overwrite | User entries preserved? | Backup? | Verdict |
|----------|-------------|----------------------|-------------------|------------------------|---------|---------|
| Claude | `~/.claude/CLAUDE.md` | `install_claude_md` writes `} >"$out"` — `providers/claude/install.sh:44-63` | **Overwrite** (regenerate from stub+AGENTS.md+principles+user-rules) | **NO** — a hand-written CLAUDE.md is fully replaced (verified: user content gone) | Yes, `cp …bak.$(date +%s)` at `:42` | **Clobbers** (recoverable) |
| Claude | `~/.claude/settings.json` → `hooks` | `result["hooks"] = fragment["hooks"]` — `providers/shared/merge-settings.py:34` | **Overwrite** of the *entire* hooks block | **NO** — every pre-existing user hook (any event) is dropped (verified) | Yes, `cp` at `providers/claude/install.sh:91` | **Clobbers** (recoverable) |
| Claude | `~/.claude/settings.json` → `permissions.allow` | union of sets — `merge-settings.py:36-38` | **Merge** | Yes — existing allow entries kept | (same file backup) | **Safe** |
| Claude | `~/.claude/settings.json` → `permissions.deny`, `env`, other keys | untouched / `setdefault` — `merge-settings.py:29,39` | **Merge** | Yes — `env` (e.g. `ANTHROPIC_BASE_URL`), `deny`, unknown keys all preserved (verified) | (same file backup) | **Safe** |
| Claude | `~/.claude/.mcp.json` | `merge-mcp.py:100-105` loads existing, updates managed keys | **Merge** | Yes — hand-added servers (`dora-work`) and unknown top-level keys preserved; managed (`gitnexus`,`lean-ctx`) overwritten by design (verified) | Yes, `cp` at `providers/claude/install.sh:71` | **Safe** |
| Claude | `~/.claude/skills` | symlink; dir → `mv …bak`, symlink → `rm` — `providers/claude/install.sh:17-31` | Replace with symlink | Dir backed up; **individual user skills inside a real dir are mass-moved**, not merged | Yes, whole-dir `.bak.$(date +%s)` | **Risky** (see PORT-05) |
| Cursor | `~/.cursor/mcp.json` | `merge-mcp.py` (same as above) | **Merge** | Yes (verified path) | Yes, `cp` at `providers/cursor/install.sh:36` | **Safe** |
| Cursor | `~/.cursor/hooks.json` | `cp "$src" "$out"` — `providers/cursor/install.sh:55` | **Overwrite** (whole file) | **NO** — any user `~/.cursor/hooks.json` content replaced | Yes, `cp …bak` at `:52` | **Clobbers** (recoverable) |
| Cursor | `~/.cursor/skills` | same symlink logic — `providers/cursor/install.sh:17-31` | Replace with symlink | Dir backed up; individual skills mass-moved | Yes, whole-dir backup | **Risky** (see PORT-05) |
| Cursor | `~/.cursor/rules/lean-ctx.mdc` | `ln -sfn` — `providers/cursor/install.sh:66-69` | Symlink, `-f` force | Same-named user rule **silently replaced** | **No backup** | **Risky** |
| Cursor | `~/.cursor/rules/principle-*.mdc` | `>"$out"` — `providers/cursor/install.sh:88-94` | **Overwrite** (write) | Same-named user file replaced | **No backup** | **Risky** |

**Headline:** the two writes that most directly violate the north-star "don't
clobber existing configs" are **`~/.claude/CLAUDE.md` (PORT-01)** and **the Claude
`settings.json` hooks block (PORT-02)**. Both keep a timestamped backup, so data is
recoverable, but the *live* file silently loses user content. The Cursor
rules/principles writes (PORT-06) clobber **without any backup**.

---

## B. Provider-targeting correctness

| Provider | Targeted? | Path / format used | Correctness notes |
|----------|-----------|--------------------|-------------------|
| **Cursor** | Yes | `~/.cursor/skills`, `~/.cursor/rules/*.mdc`, `~/.cursor/hooks.json`, `~/.cursor/mcp.json` | Formats match Cursor's file conventions. `.mdc` frontmatter (`description`,`alwaysApply`) rendered correctly (`install_principles`). |
| **Claude Code** (CLI) | Yes | `~/.claude/skills`, `~/.claude/CLAUDE.md`, `~/.claude/.mcp.json`, `~/.claude/settings.json` (hooks: `PreToolUse`/`PostToolUse`/…) | Hook event names + `hookSpecificOutput` envelope in `shell-guard.sh` match Claude Code's hook contract. **But see PORT-03**: `~/.claude/.mcp.json` is *project*-style MCP config; Claude Code's user-scope MCP servers live in `~/.claude.json` (`mcpServers`), not `~/.claude/.mcp.json`. Whether the servers actually load for the CLI at that path is **unverified** and should be confirmed. |
| **Claude Desktop / API** | **Conflated with Claude Code** | Same `~/.claude/*` paths | **PORT-04.** Docs say "Claude (Desktop + Code)" (`README.md:3,39`, `SETUP.md:1`) but only `~/.claude/*` is written. Claude **Desktop** reads `claude_desktop_config.json` (a different path, per-OS) and does **not** read `~/.claude/CLAUDE.md` or `settings.json`. The Anthropic **API / claude.ai** consume *none* of these files. So "Desktop + API" coverage is asserted but not delivered. Either implement the Desktop path or drop the claim. |
| **Codex / Gemini** | Catalogued as Phase 2 only (`README.md:61-64`) | n/a | Honestly scoped as not-yet-automated. No action for this doc. |

**Cross-provider leak check.** No Cursor-only config leaks into Claude or vice
versa: each provider installer writes only its own tree, and `mcp.overlay.json`
(Cursor's base) is empty (`providers/cursor/mcp.overlay.json` = `{"mcpServers":{}}`),
so the shared `merge-mcp.py` produces the same server set for both — acceptable.
The lean-ctx hook *formats* differ correctly per provider (`providers/cursor/hooks.json`
uses camelCase `beforeReadFile`/`preToolUse`; `providers/claude/settings.hooks.json`
uses PascalCase `PreToolUse`) — good, this is genuinely provider-aware.

---

## C. OS / shell portability matrix

System default bash on this machine is **3.2.57** (macOS), but every script uses
`#!/usr/bin/env bash`, so it runs under whatever `bash` is first on `PATH`. Good
news from inspection: **no `declare -A`, no `readlink -f`, no `sed -i`** anywhere in
the repo — the worst BSD/GNU footguns are avoided. Remaining gaps below.

| Concern | macOS | Linux | Windows | Detail / file:line |
|---------|-------|-------|---------|--------------------|
| `bin/bootstrap.sh` | Works | **Aborts by design** (`uname != Darwin` → `exit 1`, `bootstrap.sh:18-22`) | **Breaks** (no bash/Homebrew) | Linux/WSL users get a warn + hard exit; they must hand-install deps then `install.sh`. Acceptable but means "one command setup" is macOS-only. |
| `bin/install.sh` + provider installers | Works | **Should work** (pure POSIX-ish bash, dynamic `AGENTIC_ROOT` via `BASH_SOURCE`) | **Breaks** unless Git-Bash/WSL | `BASH_SOURCE`+`cd`+`pwd` is portable across bash≥3. No GNU-only flags spotted. |
| `sed "s#__AGENTIC_ROOT__#${ROOT}#g"` | Works | Works | Works (bash) | `install_claude_md:45`, `install_settings:97`. Delimiter `#` is fine **unless** the resolved path contains `#` (unlikely). BSD/GNU agree on basic `s###`. **Low risk.** |
| `shell-guard.sh` `grep -oE` / `sed` JSON-escaping | Works | Works | Works (bash) | `shell-guard.sh:24-27,57,76`. Uses `[[:space:]]`, BRE/ERE that BSD+GNU both accept. The hand-rolled JSON extract/escape is fragile generally (a 03/05 concern) but **not** OS-specific. |
| `mktemp` (no template) | Works | Works | Works | `install_settings:96` calls bare `mktemp` — portable on both BSD and GNU. |
| `date +%s` for backups | Works | Works | Works | Second-granularity — see PORT-07 (collisions on rapid re-run). |
| `chmod +x …/hooks/*.sh` | Works | Works | **No-op/irrelevant** on Windows | `install.sh:85`. Fine. |
| `which npx` / `npm root -g` / `python3` | Works if installed | Works if installed | Needs them on PATH | `merge-mcp.py:14-27,30-49`, `doctor.sh:66-76`. Per-machine detection is good; falls back to literal `"npx"` if absent (server then fails at runtime, not install). |
| Symlinks (skills, rules) | Works | Works | **Breaks** without admin/Dev-Mode | `ln -sfn`. Windows symlink creation is privileged; a Windows port needs copy-mode or junctions. |
| `python3` hard dependency | Works | Works | Needs Python | Both merge scripts are Python; no Python → MCP/settings merge fails. The Go binary (doc 01) removes this. |
| Hardcoded `/opt/homebrew/bin/*` defaults | Works | **Wrong default** | Wrong | `doctor.sh:66,116`. Only used as a fallback before `command -v`, so mostly cosmetic, but the *default* is macOS-Homebrew-specific. |

**Net:** the *installers* are largely OS-portable (bash≥3 + coreutils + python3);
the **bootstrap** and **symlink strategy** are the real non-macOS/non-Unix blockers.

---

## D. Adoptability by another user / team

| Coupling | Where | Generic? | Fix |
|----------|-------|----------|-----|
| Canonical path `~/Documents/GitHub/personal/agentic-cfg` | `ARCHITECTURE.md:107-108`; `SETUP.md:75`; the user's global `~/.claude/CLAUDE.md` pointer | **Partly.** Install itself is path-independent (`AGENTIC_ROOT` is dynamic — verified in code and docs), but **docs and the generated CLAUDE.md pointer hardcode the path**, and the *stub* bakes the absolute `AGENTIC_ROOT` into `~/.claude/CLAUDE.md` and into hook commands. Another user cloning elsewhere gets correct *function* but misleading *docs*. | Make docs say "your clone path"; the stub already injects the real root, so only prose needs fixing. |
| Personal git identity (`Tsurai7`) + private-repo URL | `SETUP.md:7-14,75`; `README.md:13`; `ARCHITECTURE.md:136-137`; project memory | **No.** Clone URL `github.com/Tsurai7/agentic-cfg.git` and a credential/`insteadOf` push workaround are personal. | For team use, parameterize the remote; document a fork/clone flow; move the identity workaround out of the adoptable surface. |
| `AGENTS.md` adopt-as-project claim | `core/instructions/AGENTS.md:1-3`; `README.md:66-68`; `SETUP.md:83-90` | **Mostly yes** for the instruction text, **but** `AGENTS.md` references sibling paths (`user-rules/…`, `../../evals/PLAYBOOK.md`, `core/principles/`) that only resolve **inside this repo**. Dropped into a foreign project root, those links dangle. | Ship a self-contained "portable AGENTS.md" variant with no repo-relative links, or inline the referenced rules. |
| lean-ctx / rtk / GitNexus assumed present | `AGENTS.md` tool-precedence; `settings.hooks.json` hardcodes `lean-ctx hook …` | **Degrades, doesn't break.** Hooks call `lean-ctx`/`rtk` by bare name; if absent the hook command just fails per-invocation (Claude tolerates a failing hook → command runs unwrapped). `shell-guard.sh` already guards with `command -v`. | For a clean machine *without* lean-ctx, the `settings.hooks.json` lean-ctx hooks (8 events) will error every tool call. Gate them on lean-ctx presence, or template them in only when installed (PORT-08). |
| Marketplace-plugin env in `.env.example` | `secrets/.env.example:15-22` | Generic (commented) | Fine. |

**Minimum to make it cleanly adoptable by a different user/machine without editing
source:** (1) merge-not-overwrite for CLAUDE.md + settings hooks (PORT-01/02) so a
new user's existing config survives; (2) de-hardcode the canonical path and clone
URL from docs (PORT-09); (3) gate lean-ctx hooks on the binary being present
(PORT-08); (4) a portable, link-free `AGENTS.md` for foreign repos (PORT-10).

---

## E. Findings

Severity = impact on the two north-star portability goals (cross-provider + non-destructive co-install).

### PORT-01 — `install_claude_md` overwrites an existing user `~/.claude/CLAUDE.md` — **Critical**
`providers/claude/install.sh:33-65` regenerates the file with `} >"$out"` (`:63`).
**Verified:** a hand-written CLAUDE.md (`# MY OWN … call me Dr. Smith`) is fully
replaced; `grep -c "Dr. Smith"` on the result = 0. A `.bak.<ts>` is written (`:42`),
so it is recoverable, but the live global memory is silently destroyed — the single
most important file Claude Code reads for a user. This is the textbook violation of
"existing configs MUST NOT be clobbered or lost."
**Fix:** stop owning the whole file. Write the agentic content into a **delimited
managed block** (`<!-- BEGIN agentic --> … <!-- END agentic -->`) and 3-way-merge:
on re-install, replace only the block, preserving everything the user wrote outside
it. On first install into an existing file, insert the block at top and keep their
content. (Same managed-block pattern the Go binary in doc 01 should implement.)

### PORT-02 — `merge-settings.py` drops ALL pre-existing user hooks — **Critical**
`providers/shared/merge-settings.py:33-34`: `if "hooks" in fragment: result["hooks"]
= fragment["hooks"]` wholesale-replaces the hooks object. **Verified:** a user's
`PreToolUse:[my-own-guard.sh]` and `Notification:[say done]` are both gone after
merge; only `env`/`deny`/custom `allow` survive. The module's own docstring claims
"Every other key … is preserved untouched" — true for `env`, **false for `hooks`**.
A user with their own hooks loses them on every install.
**Fix:** deep-merge per hook event. For each event, append the repo's hook entries to
the user's existing array (de-duplicated by command), or own only a tagged subset.
At minimum, merge event-by-event instead of replacing the whole `hooks` object.
*(Cross-link: 03-gaps-and-bugs — this is also a plain correctness bug in the merge
contract; I own the co-existence framing, 03 owns the general fix-the-merge tracking.)*

### PORT-03 — Claude Code user-scope MCP path may be wrong (`~/.claude/.mcp.json`) — **High (unverified)**
`providers/claude/install.sh:68` writes `~/.claude/.mcp.json`. Claude Code's
**user/global** MCP servers are conventionally configured in `~/.claude.json`
(top-level `mcpServers`); `.mcp.json` is the **project-scoped** filename (read from a
project root). If the CLI does not read `~/.claude/.mcp.json` as a user config, the
`gitnexus`/`lean-ctx` servers silently never load for Claude Code even though
`doctor.sh:40-50` reports "contains gitnexus" (it only greps the file it wrote).
**This is inferred from the path, not observed** — I did not start Claude Code to
confirm. **Fix:** verify the actual user-scope MCP config path/key for the current
Claude Code version (defer the version-specific lookup to doc 01/05's environment),
and target that. If both paths are valid, keep `.mcp.json` but document it; if not,
switch to `~/.claude.json` with a merge (it also holds other keys, so a careful
merge like `merge-mcp` is mandatory — never overwrite `~/.claude.json`).

### PORT-04 — "Claude Desktop + API" coverage claimed but not delivered — **High**
`README.md:3,39`, `SETUP.md:1`, provider table all say Claude **Desktop**. Only
`~/.claude/*` (the **Code/CLI** surface) is written. Claude **Desktop** uses a
separate `claude_desktop_config.json` (per-OS location) and ignores `CLAUDE.md` /
`settings.json`; the **API/claude.ai** read none of these. So one of three named
consumers is unserved and a second is mislabeled.
**Fix:** either (a) add a Desktop target that writes/merges `claude_desktop_config.json`
(MCP only — Desktop has no skills/CLAUDE.md surface), or (b) correct the docs to
"Claude **Code**" and explicitly note Desktop/API are out of scope. Pick (b) now,
(a) as roadmap. Owns: this doc defines the *requirement*; 02 sequences it.

### PORT-05 — Skills symlink mass-moves a user's real `skills/` directory — **High**
`providers/{cursor,claude}/install.sh:17-31`: if `~/.cursor/skills` (or
`~/.claude/skills`) is a **real directory** (the common case — users keep their own
skills there), the installer `mv`s the **entire directory** to `…skills.bak.<ts>`
and replaces it with a symlink to `core/skills`. The user's own skills are no longer
on the live path — Claude/Cursor stop seeing them. Recoverable from the backup, but
silently disabled, and a *second* run can't tell the difference (the symlink now
exists, so re-runs are fine; it's the **first** run that hurts).
**Fix:** don't hijack the whole `skills` dir. Either (a) symlink **per-skill**
(`~/.cursor/skills/<name>` → `core/skills/<name>`), leaving the user's own skills
beside ours; or (b) if you must own the dir, detect non-empty real dirs and *merge*
(symlink each managed skill into the existing dir) rather than move-and-replace.
Option (a) is cleaner and matches how `install_rules` already links per-file.

### PORT-06 — Cursor rules/principles overwrite same-named user files with NO backup — **Med**
`install_rules` (`providers/cursor/install.sh:66-69`) does `ln -sfn` (force) and
`install_principles` (`:88-94`) writes `principle-<name>.mdc` with `>` — both with
**no backup**, unlike every other write. A user with `~/.cursor/rules/lean-ctx.mdc`
or `~/.cursor/rules/principle-honesty.mdc` loses it irrecoverably. Collisions are
unlikely (names are fairly specific) but the asymmetry (no backup) is the real
defect.
**Fix:** back up same-named targets before linking/writing, or namespace under a
managed subdir (`~/.cursor/rules/agentic/…`).

### PORT-07 — Backups are second-granular → collide / accumulate unboundedly — **Med**
Every backup uses `.bak.$(date +%s)` (`install.sh` claude `:42,71,91`; cursor
`:27,36,52`; skills dir backups). Two consequences: (1) **collision** — two writes
in the same second (e.g. the installer backs up `mcp.json` then `settings.json`, or a
scripted re-run) can land on the same timestamp and **overwrite the prior backup**;
(2) **unbounded accumulation** — every re-install leaves another `.bak.<ts>` in
`~/.claude` and `~/.cursor`, with no pruning. Idempotency for the *active* files is
fine (merges converge), but the backup dir grows forever.
**Fix:** use a single timestamped backup **directory** per run
(`~/.agentic-backups/<iso8601>/…`) outside the consumed dirs (so it never pollutes
`~/.claude` or trips `doctor`/Claude's own file scans), with sub-second or
monotonic naming, and an optional retention cap.

### PORT-08 — lean-ctx hooks fire unconditionally even when lean-ctx is absent — **Med**
`providers/claude/settings.hooks.json` wires **8** hook events to `lean-ctx hook …`
and `providers/cursor/hooks.json` wires ~11. On a clean machine where the optional
lean-ctx binary was skipped (bootstrap treats it best-effort, `bootstrap.sh:56-63`),
every tool call invokes a missing binary. Claude tolerates a failing hook, but it is
noise on every action and contradicts "degrade cleanly when the tool is absent."
**Fix:** template lean-ctx hooks **in only when** `command -v lean-ctx` succeeds at
install time (a render decision), or wrap each command in a `command -v lean-ctx &&`
guard, or point them at a tiny repo-owned shim that no-ops when the binary is gone
(the way `shell-guard.sh:65` already guards lean-ctx/rtk).

### PORT-09 — Canonical path & private clone URL hardcoded in docs — **Med**
`ARCHITECTURE.md:107-108`, `SETUP.md:75`, `README.md:13` assume
`~/Documents/GitHub/personal/agentic-cfg` and `github.com/Tsurai7/agentic-cfg.git`.
Install *works* from any clone (dynamic `AGENTIC_ROOT`), so this is a docs/adoption
wart, not a functional break — but it blocks frictionless reuse by another person.
**Fix:** docs should reference "your clone directory" and a forkable URL; keep the
one true machine path only in personal notes, not in the adoptable repo surface.

### PORT-10 — `AGENTS.md` adopt-as-project link rot — **Med**
`core/instructions/AGENTS.md` references `user-rules/…`, `../../evals/PLAYBOOK.md`,
`core/principles/` (`:48-52`). Dropped into a foreign repo (as `README.md:66-68`
recommends), these relative links dangle.
**Fix:** generate a self-contained `AGENTS.portable.md` (links inlined or stripped)
for project adoption; keep the link-rich one for in-repo use.

### PORT-11 — `merge-mcp` writes machine-specific absolute `PATH`/`NODE_PATH` into config — **Low**
**Verified:** the resolved `~/.cursor/mcp.json` / `~/.claude/.mcp.json` contains this
machine's full `$PATH` (via `__PATH__` from `load_env`, `merge-mcp.py:35`), including
session-specific Claude plugin dirs. This is **anti-portable for a committed config**
but these files live in `$HOME` (not the repo), so it does not pollute the source —
hence Low. The risk is if a user ever copies the generated file between machines.
**Fix:** prefer leaving `PATH`/`NODE_PATH` unset in the fragment (let the launcher
inherit the ambient env) unless an integration genuinely needs an override.

### PORT-12 — `git push` identity workaround is part of the documented setup — **Low (adoption)**
`ARCHITECTURE.md:136-137` + project memory describe a credential-helper/`insteadOf`
workaround tied to the `Tsurai7` account. Harmless to the owner; a speed-bump for
anyone else.
**Fix:** isolate to personal notes; the adoptable repo should assume vanilla `gh`/git.

---

## F. "Make it generic" plan (ordered by risk-reduction)

1. **Stop clobbering the two highest-value files (PORT-01, PORT-02).** Managed-block
   3-way merge for `CLAUDE.md`; event-wise deep-merge for `settings.json` hooks.
   *This is the single biggest win — it is the literal north-star.* Add the
   `install onto a $HOME that already has CLAUDE.md / hooks` fixture (hand to doc 05).
2. **Fix the skills clobber (PORT-05).** Switch to per-skill symlinks so a user's own
   skills survive a first install. Same per-file pattern already used for rules.
3. **Confirm & correct the Claude MCP path and the Desktop/API claims
   (PORT-03, PORT-04).** Verify the user-scope MCP config path for current Claude
   Code; either deliver Desktop or scope the docs to "Claude Code".
4. **Gate optional-tool hooks (PORT-08).** Render lean-ctx hooks only when the binary
   is present, so a clean machine without lean-ctx degrades cleanly.
5. **Backup hygiene (PORT-06, PORT-07).** One timestamped backup *directory* per run
   outside the consumed dirs; back up rules/principles before overwrite; add retention.
6. **De-hardcode for adoption (PORT-09, PORT-10, PORT-12).** Clone-relative docs,
   a portable link-free `AGENTS.md`, identity workaround out of the adoptable surface.
7. **Config cleanliness (PORT-11).** Drop machine-specific `PATH`/`NODE_PATH` from
   generated MCP unless required.
8. **OS portability hardening.** Document the Linux/WSL manual path explicitly (it
   already mostly works); design a copy-mode fallback for symlink-less platforms
   (Windows) — this is mostly the Go binary's job (see cross-links).

---

## G. Requirements handed to sibling docs

**To 01-go-rewrite — portability requirements the single static `agentic` binary MUST satisfy:**
- Remove the **python3** runtime dependency (both merge scripts) and the
  **bash-version / coreutils** dependence — a static binary is the cleanest
  portability lever for Linux/WSL and a future Windows port.
- Implement **non-destructive merges natively**: managed-block 3-way merge for
  `CLAUDE.md` (PORT-01); event-wise hook deep-merge for `settings.json` (PORT-02);
  keep the existing MCP merge semantics (the one behavior already correct).
- **Per-skill** symlink/copy strategy (PORT-05) with a **copy-mode fallback** where
  symlinks are unprivileged/absent (Windows).
- **Provider/OS detection** to pick destinations (incl. a real Claude **Desktop**
  target — `claude_desktop_config.json`, per-OS path — for PORT-04) and the correct
  Claude Code user-scope MCP path (PORT-03).
- A single backup-directory scheme with collision-free naming (PORT-07).
- I own these *requirements*; doc 01 owns the binary's API/design.

**To 05-tests — portability scenarios that SHOULD be covered (fixtures, not assertions-on-the-obvious):**
- Install onto a fixture `$HOME` that **already has a hand-written `~/.claude/CLAUDE.md`**
  → assert the user's content survives (PORT-01).
- Install onto a fixture `$HOME` with **pre-existing `settings.json` hooks** (any event)
  → assert they survive and the repo hooks are *added*, not substituted (PORT-02).
- Install onto a `$HOME` with **hand-added MCP servers + unknown top-level keys** in
  `.mcp.json` → assert preservation (regression guard for the one safe behavior).
- Install onto a `$HOME` with a **real `~/.cursor/skills` dir containing user skills**
  → assert user skills remain live (PORT-05).
- Install with a **same-named `~/.cursor/rules/principle-honesty.mdc`** present →
  assert it is backed up, not silently lost (PORT-06).
- **Idempotency:** run install twice → assert active files are byte-identical and the
  backup count does not grow unboundedly (PORT-07).
- Install on a `$HOME` **without lean-ctx on PATH** → assert no per-tool-call hook
  errors (PORT-08).
- A **Linux** CI lane running `install.sh` (not bootstrap) to catch BSD/GNU drift.

**To 03-gaps-and-bugs (cross-links, not owned here):** the `settings.json` hooks
replacement (PORT-02) is also a plain merge-contract bug; the hand-rolled JSON
extract/escape in `shell-guard.sh:24-27,57,76` is fragile (not OS-specific, so 03's
domain); `doctor.sh:40-50` reports MCP presence by grepping the file it just wrote,
so it cannot catch PORT-03 (a false-confidence gap for 03).

---

## H. Prioritized backlog

| ID | Title | Severity | Effort | Depends on |
|----|-------|----------|--------|------------|
| PORT-01 | Managed-block 3-way merge for `~/.claude/CLAUDE.md` (stop overwrite) | Critical | M | — |
| PORT-02 | Event-wise deep-merge of `settings.json` hooks (stop wholesale replace) | Critical | S | — |
| PORT-03 | Verify & correct Claude Code user-scope MCP path (`~/.claude/.mcp.json`?) | High | S (verify) / M (fix) | — |
| PORT-04 | Deliver Claude Desktop target or scope docs to "Claude Code" | High | S (docs) / L (Desktop) | PORT-03 |
| PORT-05 | Per-skill symlinks so user's own skills survive first install | High | M | — |
| PORT-08 | Render/gate lean-ctx hooks only when binary present | Med | S | — |
| PORT-06 | Back up (or namespace) Cursor rules/principles before overwrite | Med | S | — |
| PORT-07 | Single backup *directory* per run, collision-free, with retention | Med | M | — |
| PORT-09 | De-hardcode canonical path / clone URL from docs | Med | S | — |
| PORT-10 | Portable, link-free `AGENTS.portable.md` for project adoption | Med | S | — |
| PORT-11 | Drop machine-specific `PATH`/`NODE_PATH` from generated MCP | Low | S | — |
| PORT-12 | Move git-identity workaround out of the adoptable surface | Low | S | — |

**Effort:** S = a focused change in one file; M = touches a script + needs a fixture
test; L = new provider/OS code path.

**Cross-doc dependency summary:** PORT-01/02/03/05/07 are the merge/IO behaviors the
**Go binary (01)** should own natively; all the `install onto a populated $HOME`
fixtures are **test work for 05**; PORT-02 and the `shell-guard`/`doctor` fragilities
cross-link to **03**; sequencing (Desktop target, binary rollout) is **02**.

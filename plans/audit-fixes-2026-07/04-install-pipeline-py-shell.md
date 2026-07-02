# 04 — Install pipeline: Python / shell

**Owner:** one implementer (touches no Go — runs in parallel with plans 01–03).
**Files:** `core/memory/sync.py`, `providers/cursor/install.sh`,
`providers/claude/install.sh`, `bin/install.sh`, `providers/shared/merge-settings.py`,
`providers/shared/merge-mcp.py`, `providers/shared/safe_io.py`.

**Safety.** Every live repro uses a `HOME=$(mktemp -d)` sandbox. Never write to
the real `~/.claude` / `~/.cursor`.

---

## C1 — [BUG, high] fresh-machine install fails when `~/.claude/projects` absent

**Evidence.** `sync.py:90-92` returns **2** when the projects root doesn't exist
(i.e. Claude Code never run). `bin/install.sh:3` is `set -euo pipefail` and
lines `88-94` call `sync.py` unconditionally (`:91` dry-run, `:93` `--apply`)
with no guard, so exit 2 propagates: `bin/install.sh --provider all` on a fresh
HOME prints `EXIT=2`, "Install complete." never prints, and `bootstrap.sh` skips
`doctor`. Contradicts `docs/HOW-IT-WORKS.md:258` ("Fresh machine: clone,
`bash bin/install.sh --provider all`").

**Fix.** Treat a missing projects root as **zero active projects**: in
`sync.py`, return **0** with an informational stderr line when the root is
absent. (Belt-and-suspenders: also guard the call in `bin/install.sh` with
`[[ -d "$HOME/.claude/projects" ]]`, but the `sync.py` return-0 is the primary
fix so a direct `sync.py` run also degrades gracefully.)

**AC1.** `HOME=$(mktemp -d) bash bin/install.sh --provider all` → **exit 0**,
"Install complete." printed. **AC2.** `HOME=$(mktemp -d) python3
core/memory/sync.py --apply` → exit 0 with the informational message.
**AC3.** With a populated `~/.claude/projects`, sync still seeds as before
(regression guard).

---

## C2 — [BUG, high] malformed `~/.cursor/hooks.json` silently discarded

**Evidence.** `providers/cursor/install.sh:117-121` catches `JSONDecodeError`
and proceeds with `existing = {}`, dropping user-added hook events with exit 0 —
while the sibling `settings.json`/`mcp.json` merges hard-error and leave the
file untouched (`settings.go:27`, `mcpmerge.go:273`). The comment at `:97-98`
promises "Merge (not clobber)… preserving any event/key a user added by hand".

**Fix.** Replace the silent `except JSONDecodeError: existing = {}` with a hard
error mirroring the siblings: print `invalid JSON in <path>` to stderr and exit
non-zero, leaving the file untouched.

**AC4.** Seed a malformed `~/.cursor/hooks.json` with a user hook, run
`providers/cursor/install.sh` → **exit non-zero**, error names the file, the
live `hooks.json` is **unchanged** (user hook still present). **AC5.** A
valid-but-unusual `hooks.json` (user event present) still merges and preserves
the user event (regression guard).

---

## C4 — [BUG, high] Python JSON writers mangle non-ASCII user content

**Evidence.** `json.dumps` without `ensure_ascii=False` rewrites non-ASCII user
bytes to `\uXXXX`: `providers/cursor/install.sh:139` (hooks merge, unconditional
even when the Go binary is present), `:248`/`:277` (cursor eject),
`merge-settings.py:132`, `merge-mcp.py:298/306` (when the Go binary is absent).
The Go path preserves raw UTF-8 (`jsonorder` `SetEscapeHTML(false)`), so
alternating paths churns bytes and breaks Go↔Python parity. `parity_test.go:86,105`
compare **parsed** values, so it can't see the divergence.

**Fix.** Add `ensure_ascii=False` to every `json.dumps` that writes a user-owned
file: both embedded Python blocks in `providers/cursor/install.sh`,
`merge-settings.py`, `merge-mcp.py`. Extend one parity test to compare **raw
bytes** for a non-ASCII fixture (this touches `internal/installtest`, so
coordinate: add the byte-parity fixture in plan 03's GeneratedMD test or note it
here for the verifier to add — pick the Python-only proof if avoiding the Go
file: a shell repro comparing `bin/agentic merge-settings` vs
`python3 merge-settings.py` raw output on a `значение` fixture).

**AC6.** `python3 providers/shared/merge-settings.py` on a fixture with
`"значение"` writes **raw UTF-8** (`grep -c 'значение'` ≥ 1, `grep -c '\\u04'`
== 0). Same for `merge-mcp.py` and both cursor blocks. **AC7.** Byte-compare Go
vs Python output on the same non-ASCII input → identical bytes.

---

## C6-py — [RISK, medium] `safe_io.atomic_write_text` de-links a symlink

**Evidence.** `safe_io.py:35` `os.replace(tmp, path)` de-links a symlinked
target, same class as the Go writers (plan 03 C6-go).

**Fix.** Resolve `os.path.realpath(path)` before creating the temp file and
rename onto the resolved path (create the temp in the resolved dir), so a
symlinked destination survives. Guard the missing-target case.

**AC8.** A symlinked target passed to `atomic_write_text` stays a symlink; the
link target receives the new content.

---

## C7 — [RISK, high] backup-name mismatch strands user skills after install→eject

**Evidence.** `providers/claude/install.sh:59-64/75-80` back up an existing real
`~/.claude/skills` (and `agents`) to `<name>.bak.<epoch>`, but `agentic eject`
restores only `<name>.pre-agentic` (`lifecycle.go:30-31`, `:341-359`). After the
documented `install.sh` → `eject` flow, eject exits 0 leaving no `skills`/
`agents` dir and no warning — the user's own content is stranded under the
timestamped name and silently stops loading. The pure `inject`→`eject` path
restores correctly.

**Fix (shell side, keeps plan 03 disjoint).** Change
`providers/claude/install.sh` to back up to `skills.pre-agentic` /
`agents.pre-agentic` (the name eject already restores), matching the Go inject.
If a `.pre-agentic` already exists, do not overwrite it (preserve the earliest
real backup).

**AC9.** Repro: seed `~/.claude/skills/my-skill/SKILL.md`, run
`providers/claude/install.sh`, then `agentic eject` → `~/.claude/skills/my-skill/
SKILL.md` is **restored** (content intact), not stranded under a `.bak.*` name.

---

## D1 — [RISK, high] `sync.py` non-atomic writes → stuck 0-byte memory file

**Evidence.** `sync.py:116` writes per-project memory with plain
`Path.write_text` (truncate-then-write); a crash mid-write leaves a 0-byte file
that `existing_slugs()` (`:56-57`, presence-only) never re-seeds. `:73` rewrites
the live `MEMORY.md` index in place non-atomically too.

**Fix.** Use `providers/shared/safe_io.atomic_write_text` for both the seed
write (`:116`) and the index write (`:73`). (`safe_io` is imported by the other
providers/shared scripts; import it here too.)

**AC10.** A simulated crash mid-write (repro from `confirmed.json`
`sync.py:116`) leaves the previous content intact, not a 0-byte file; no
leftover temp files.

---

## D2 — [RISK, medium] `merge-mcp.py` config + sidecar are two separate writes

**Evidence.** `merge-mcp.py:306-307` writes the managed config then the sidecar
as two independent `atomic_write_text` calls; a crash between them leaves the
sidecar one run stale, which in a narrow race (user hand-re-adds a same-named
server before the next run) deletes that server. Self-heals otherwise.

**Fix (trace first, then decide).** This is the lowest-confidence fix in the
wave: the reordering's safety depends on `merge-mcp.py`'s reconciliation logic,
which the implementer **must trace before touching code**. Read how the next run
reconciles a server that is (a) in the config but (b) absent from the sidecar,
and vice versa. **Only if** writing the **sidecar first, then the config**
provably removes the harmful case (a crash leaves the sidecar listing a server
the config no longer manages → next run's pop is a harmless no-op) **without**
introducing a new one, apply the reorder + a one-line rationale comment.
**Otherwise** leave the code unchanged and add a "Known limitation" comment at
`merge-mcp.py:306` describing the crash-race and its self-heal, and record the
decision in the plan. Full two-file atomicity (a journal) is out of scope either
way.

**AC11.** Either: a crash-between-writes repro no longer deletes a same-named
hand-added server on the next run (reorder applied, with the trace written up in
the implementer's report); **or** a documented known-limitation comment with the
trace justifying why no safe reorder exists. Both are acceptable DONE states —
the unacceptable outcome is an unexplained reorder.

---

## mktemp cleanup — [DEBT] leaked temp file/dir on early exit

**Evidence.** `providers/claude/install.sh:166` `resolved="$(mktemp)"` is
cleaned only by an explicit `rm` at `:189`, unreachable if `merge-settings`
fails under `set -e`. (`bin/ci-check.sh:124`'s `mktemp -d` is analogous but is
owned by plan 01, which already edits that file.)

**Fix.** Add `trap 'rm -f "$resolved"' RETURN` inside `install_settings`
(matching `providers/claude/hooks/edit-lint.test.sh:9`).

**AC12.** Forcing `merge-settings` to fail leaves no leaked temp file.

---

## Plan-level acceptance

- `python3 providers/shared/selftest.py`, `python3 core/memory/lint.py` pass.
- `HOME=$(mktemp -d) bash bin/install.sh --provider all` → exit 0 end to end.
- Each repro captured before→after.
- Diff touches only the files named at the top.

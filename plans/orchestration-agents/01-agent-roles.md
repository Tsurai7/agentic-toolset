# Plan 01 — Agent role definitions + render + ci-check

Part of [`00-INDEX.md`](00-INDEX.md); design: [`DESIGN.md`](DESIGN.md) (Approach B).

**File scope (touch nothing else):**
- `core/agents/implementer.md`, `core/agents/doc-writer.md`, `core/agents/verifier.md`,
  `core/agents/researcher.md` (new)
- `providers/claude/install.sh` (add `link_agents`)
- `bin/ci-check.sh` (add agents section)
- `internal/lifecycle/lifecycle.go`, `internal/lifecycle/lifecycle_test.go` (agents
  awareness for inject/eject/status — change 4)

Do NOT commit. Do NOT touch the real `~/.claude` — verify installs against a fake HOME.

## Change 1 — four agent files (exact content)

Create `core/agents/` containing exactly the four files below, **verbatim**. No README.md
in this directory (Claude Code scans it for agent definitions; keep it clean — the
explanation lives in `ARCHITECTURE.md`/docs via plan 02).

### `core/agents/implementer.md`

```markdown
---
name: implementer
description: Executes a written implementation plan with hard acceptance criteria; smallest correct diff; verifies before reporting.
tools: Read, Grep, Glob, Bash, Edit, Write
model: sonnet
---

You implement exactly one written plan (a file path or inline spec the orchestrator
gives you), in the repo it names.

Read the whole plan first. The plan's acceptance criteria (AC) are the definition of
done — nothing else is. If an AC cannot be met as written, STOP and report the blocker;
do not improvise around it or silently reinterpret it.

Scope guard:
- Touch only the files the plan names. Every changed line must trace to a plan item.
- Smallest correct diff; match the surrounding style; no drive-by refactors or cleanups.
- Never run `git commit`, `git add`, or `git push` unless the plan explicitly says so.
  Leave changes in the working tree.

Environment:
- macOS; shell commands run through a compression hook — never strip or bypass it. Put
  complex logic in a script file and run `bash script.sh`.
- Prefer dedicated tools (Read, Grep, Glob, Edit) over shell equivalents.
- If a hook blocks a Read/Grep once, retry the same call once — it passes on retry.

Verification: run the plan's verification commands yourself before reporting and read
their actual output. A claim like "tests pass" requires fresh observed output.

Final report (your last message is parsed by an orchestrator — structure, not prose):
- STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- Per-AC verdict (pass/fail + one-line evidence: the command and what it printed)
- Files changed
- Deviations from the plan, if any, each with its reason
- What you did NOT verify

Report only what you observed. If something failed, say so plainly and show the output.
```

### `core/agents/doc-writer.md`

```markdown
---
name: doc-writer
description: Mechanical documentation edits from an explicit item list; never claims more than the diff shows.
tools: Read, Grep, Glob, Bash, Edit, Write
model: haiku
---

You execute a mechanical documentation task: an explicit list of items (file + exact
change) from the orchestrator.

Work item-by-item. Every changed line must trace to an item. If an item is ambiguous or
its target file has changed since the item was written, finish the unambiguous items,
then STOP on that item and report it instead of guessing.

Honesty rules (these override style):
- Never overstate. When a doc line states a number, an effect, or a status, copy it from
  the source the item names — verbatim, not paraphrased upward. If the source doesn't
  state it, don't write it.
- No intensifying adjectives ("dramatically", "significantly", "now fully") unless the
  item's source text contains them.
- Do not mark anything done/fixed/shipped that you did not see evidence for in this
  session.

Scope guard: touch only the files the items name; smallest diff; match existing style,
heading levels, and link formats; never `git commit`/`add`/`push`.

Environment: macOS; shell runs through a compression hook — never strip or bypass it;
prefer Read/Grep/Glob/Edit tools; if a hook blocks a Read once, retry it once.

Final report (parsed by an orchestrator): STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED |
NEEDS_CONTEXT; per-item verdict; files changed; items skipped and why; anything you did
not verify.
```

### `core/agents/verifier.md`

```markdown
---
name: verifier
description: Runs verification gates and checks acceptance criteria against the actual diff; changes nothing; reports pass/fail with observed output.
tools: Read, Grep, Glob, Bash
model: sonnet
---

You verify someone else's work. You never modify files — no edits, no `git add/commit/
checkout/restore`, no state-changing commands beyond what a check itself requires
(e.g. `go test` writing its cache is fine).

Input: a plan or AC list (file path or inline) and optionally gate commands. Default
gates for this config repo: `bash bin/ci-check.sh`, `go test ./... -count=1`,
`golangci-lint run`, `python3 evals/lint.py`, `python3 evals/selftest.py`.

Method — adversarial, not confirmatory:
1. Run the gates; capture exit codes and the failing lines, not just summaries.
2. Check every AC against actual state (read the file, run the named probe). An AC
   without observed evidence is FAIL, not "probably fine".
3. Hunt scope creep: `git status --porcelain` and `git diff --stat` — flag changed files
   the plan never named.
4. Try to falsify "done": think of the one probe that would break the claim, run it.

Environment: macOS; shell runs through a compression hook — never strip or bypass it; if
a hook blocks a Read/Grep once, retry the same call once.

Final report (parsed by an orchestrator):
- STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED (gates failing)
- Gate table: command → exit code → one-line evidence
- Per-AC verdict table: AC → PASS/FAIL → evidence (command or file:line)
- Out-of-scope changes found
- What you could not verify and why
```

### `core/agents/researcher.md`

```markdown
---
name: researcher
description: Web research with verified citations; every claim carries a source URL actually fetched during the session.
tools: Read, Grep, Glob, Bash, WebSearch, WebFetch, Edit, Write
model: sonnet
---

You research a question or refresh a document; every factual claim you produce is backed
by a source you actually opened.

Citation discipline (overrides speed):
- No claim without a source URL you fetched with WebFetch in this session. Search-result
  snippets are leads, not sources.
- Prefer primary sources (vendor docs/blogs, papers, the author's own post); mark
  secondary reporting as such.
- Date-stamp moving facts ("as of <month year>") — model names, prices, and limits drift
  monthly.
- If sources conflict or you cannot verify: say so explicitly and hedge. An honest
  "unverified" beats a confident guess.
- Quotation marks only around verbatim words that appear at the source; paraphrase
  accurately otherwise; no secondhand attribution.

When editing a repo document: preserve its structure, tone, and citation style; correct
visibly ("previously X; as of July 2026 Y (source)") rather than silently rewriting
history; never delete cited content unless you verified it is now wrong.

Scope guard: touch only files the task names; never `git commit`/`add`/`push`.

Environment: macOS; shell runs through a compression hook — never strip or bypass it;
prefer Read/Grep/Glob/Edit tools; retry a hook-blocked Read once.

Final report (parsed by an orchestrator): STATUS: DONE | DONE_WITH_CONCERNS | BLOCKED |
NEEDS_CONTEXT; claims verified (verdict + URL); claims you could NOT verify and what you
did with them; files changed.
```

## Change 2 — render in `providers/claude/install.sh`

Add a `link_agents()` function directly after `link_skills()` (same idiom, symlink the
whole directory), and call it right after `link_skills` in the main sequence:

```bash
link_agents() {
  local target="${HOME}/.claude/agents"
  local source="${AGENTIC_ROOT}/core/agents"
  run mkdir -p "${HOME}/.claude"
  if [[ -L "$target" ]]; then
    run rm "$target"
  elif [[ -d "$target" ]]; then
    log "backup existing $target"
    if [[ "$DRY_RUN" != "1" ]]; then
      mv "$target" "${target}.bak.$(date +%s)"
    fi
  fi
  run ln -sfn "$source" "$target"
  log "agents: $target -> $source"
}
```

Tier note: agents install on ALL tiers (they *reduce* cost; nothing weak-tier-specific).
Do not add tier gating.

## Change 3 — `bin/ci-check.sh` agents section

Add a new section after the "SKILL.md frontmatter" section, following the file's
`ok`/`err` idiom (adapt shape to shellcheck; keep behavior exactly):

```bash
echo "== agent definitions =="
# NB: agent descriptions must be plain single-line unquoted YAML — the sed
# extraction below (and Claude Code's own loader) assumes that shape.
while IFS= read -r f; do
  base="$(basename "$f" .md)"
  name_val="$(grep -m1 '^name:' "$f" | sed 's/^name:[[:space:]]*//')"
  desc_val="$(grep -m1 '^description:' "$f" | sed 's/^description:[[:space:]]*//')"
  model_val="$(grep -m1 '^model:' "$f" | sed 's/^model:[[:space:]]*//')"
  if head -1 "$f" | grep -q '^---$' && [[ -n "$name_val" && -n "$desc_val" ]]; then
    ok "$f frontmatter"
  else
    err "$f missing frontmatter name/description"
  fi
  if [[ "$name_val" == "$base" ]]; then ok "$f name matches filename"; else err "$f name '$name_val' != filename '$base'"; fi
  words=$(printf '%s\n' "$desc_val" | wc -w | tr -d ' ')
  if [[ "$words" -le 25 ]]; then ok "$f description ${words}w (cap 25)"; else err "$f description ${words}w exceeds 25-word cap"; fi
  case "$model_val" in
    haiku|sonnet|opus|fable|inherit) ok "$f model '$model_val'" ;;
    *) err "$f model '$model_val' not in {haiku,sonnet,opus,fable,inherit}" ;;
  esac
  if grep -q '^tools:' "$f"; then ok "$f tools allowlist present"; else err "$f tools allowlist missing"; fi
done < <(find core/agents -name '*.md' 2>/dev/null)
echo ""
```

The 25-word description cap is a design constraint (agent descriptions are loaded into
the orchestrator's context) — the check makes it mechanical.

## Change 4 — `internal/lifecycle` agents awareness

The Go path (`agentic inject|eject|status`) mirrors `install.sh` and must not go blind
to the new surface. Extend `internal/lifecycle/lifecycle.go`, mirroring the existing
skills semantics exactly:

- `const agentsBackup = "agents.pre-agentic"` (next to `skillsBackup`); an
  `agentsSource()` helper next to `skillsSource()`.
- Inject: link `Home/.claude/agents` → `Root/core/agents` with the same
  refresh-symlink / back-up-real-dir / refuse-to-overwrite-prior-backup behavior as
  `injectSkills`. Preferred shape: generalize `injectSkills`/`ejectSkills` into a shared
  parametrized helper (target name, source, backup name, log label) called for both
  "skills" and "agents", keeping the existing log labels (`skills: …`) byte-compatible
  so current tests stay green; a straight copy (`injectAgents`/`ejectAgents`) is
  acceptable if the generalization would churn existing tests.
- Eject: remove the agents symlink only if it points at our source; restore
  `agents.pre-agentic` if present — same as skills.
- `StatusReport`: add `Agents string` (`"linked" | "foreign" | "absent"`) with a JSON
  tag; include `r.Agents == "linked"` in the `Injected` conjunction; add an
  `agents          : %s` line to `Render`. Named consequence: a machine injected before
  this wave reports `PARTIAL` until re-inject — correct (the footprint definition grew);
  the wave-B live install re-links immediately on this machine.
- `validateRoot` stays as-is (checks `core/skills`; `core/agents` now exists in-repo).
- `lifecycle_test.go`: add agents cases mirroring the existing skills cases — inject
  creates the symlink; a pre-existing real dir is backed up and restored on eject;
  double-inject is idempotent; status reports linked/foreign/absent. Match the file's
  existing test style.

## Acceptance criteria

1. `ls core/agents/` → exactly the 4 files above; `diff` of each against the plan's
   verbatim block is empty (modulo trailing newline).
2. `bash -n providers/claude/install.sh` and `shellcheck -S warning` pass on both edited
   scripts.
3. Fake-HOME install: `HOME=$(mktemp -d) DRY_RUN=0 bash providers/claude/install.sh`
   (run from repo root; `claude` CLI may be absent — MCP step failing softly is fine as
   long as link steps ran) → `$HOME/.claude/agents` is a symlink to `<repo>/core/agents`
   and lists the 4 files. Re-run → same state, no `.bak.*` accretion for the symlink
   path. Third sub-case: fresh fake HOME, pre-seed `~/.claude/agents/` as a REAL dir
   containing a dummy `mine.md`, run install twice → exactly one `agents.bak.*` (holding
   `mine.md`) and a clean symlink at the end. NEVER run any of this against the real
   HOME.
4. `DRY_RUN=1 bash providers/claude/install.sh` prints the agents link plan and mutates
   nothing.
5. `bash bin/ci-check.sh` exits 0; the new "agent definitions" section prints OK lines
   for all four files (≥5 OK lines per file).
6. Negative probe: temporarily create `core/agents/broken.md` with `model: gpt-4` and no
   description → the section FAILs it → delete the probe file → section green again.
   (Show both runs' relevant output in the report; the final `git status` in AC 8 must
   confirm `core/agents/broken.md` no longer exists.)
7. Go path: `go test ./internal/lifecycle/... -count=1` green including the new agents
   cases; then `go test ./... -count=1` all packages ok and `golangci-lint run` clean.
   Test evidence must show: eject removes the agents symlink and restores a backed-up
   real dir; status reports the `agents` line.
8. `git status --porcelain` shows only: `core/agents/` (new), `providers/claude/install.sh`,
   `bin/ci-check.sh`, `internal/lifecycle/lifecycle.go`, `internal/lifecycle/lifecycle_test.go`
   — plus pre-existing dirty files it already showed before you started (list them once
   at start, confirm unchanged set at end; `core/agents/broken.md` must be absent).

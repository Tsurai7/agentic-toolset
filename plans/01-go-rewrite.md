# 01 — Go rewrite: a single `agentic` CLI

## Scope & ownership

This document is the concrete, buildable migration plan for replacing the repo's
**glue layer** — install orchestration, MCP merge, settings merge, and the
PreToolUse shell-guard hook — with one cross-platform `agentic` Go binary. The
mandate is fixed (a Go CLI is the target); this plan makes it buildable and
honest about where Go is *not* worth it.

What this doc covers:

- Rationale and honest cost/benefit, including what we will **not** port.
- The `agentic` CLI surface and a script→subcommand map.
- Go module / package layout and how config fragments are located at runtime.
- Behavior-preserving merge/install/hook semantics (the invariants that must not
  regress), with the implementation approach in Go.
- The shell-guard hook in Go (latency- and correctness-critical).
- Build, distribution, and bootstrap changes.
- Phased migration with A/B byte-verification and rollback.
- Go-specific test strategy (golden files, table tests, dry-run snapshots).
- Risks, open questions, and a prioritized backlog (`GO-NN`).

What this doc **defers** to siblings (referenced, not duplicated):

- **`plans/03-gaps-and-bugs.md`** owns the full defect catalog. I cite specific
  bugs only where the rewrite is the fix and where sequencing matters (the
  `$schema: null` emission, the over-broad heredoc bypass, non-atomic writes).
  The master plan must reconcile whether 03 patches these in shell first or lets
  the Go port subsume them — see *Migration* and *Risks*.
- **`plans/04-portability-review.md`** owns the portability argument for a static
  binary (Windows, no python3/bash on the hot path, PATH assumptions). I reference
  the single-binary win as motivation but do not enumerate platform gaps.
- **`plans/05-test-coverage.md`** owns the overall coverage strategy and the
  CI matrix. I own only the Go unit/golden/table tests for the ported code and
  cross-link to 05 for where they slot into CI.

All line citations below were read from the current tree on branch
`feature/value-evals-loop`.

---

## 1. Rationale & honest cost/benefit

### What we are replacing, and how big it is

The glue layer is small. Measured line counts of the migration surface:

| File | Lines | Role |
|------|-------|------|
| `bin/install.sh` | 76 | Arg parse, source `.env`, dispatch to providers |
| `providers/claude/install.sh` | 107 | Symlink skills, render `CLAUDE.md`, merge mcp+settings |
| `providers/cursor/install.sh` | 105 | Symlink skills/rules, copy hooks, render principles, merge mcp |
| `providers/shared/merge-mcp.py` | 116 | Collect fragments, resolve tools, substitute, merge |
| `providers/shared/merge-settings.py` | 49 | Merge hooks + permissions, preserve `env` |
| `providers/claude/hooks/shell-guard.sh` | 78 | PreToolUse Bash hook (3-rule precedence) |
| **Total (hot-path glue)** | **~531** | |
| `bin/doctor.sh` | 141 | Health check (read-only) |
| `bin/ci-check.sh` | 94 | Static checks (depends on Python + evals) |
| `bin/bootstrap.sh` | 92 | Dep install + run installer |

So the *core* port is ~530 lines, not 250. That matters for the over-engineering
judgement: it is large enough that the fragility and testability wins are real,
small enough that a Go rewrite is not a multi-week project.

### Where Go genuinely wins (per file, with the current pain cited)

1. **Real JSON parsing instead of grep/sed.** `shell-guard.sh:19-28` parses the
   hook envelope with `grep -oE` + `sed` unescaping. This is the textbook case
   for `encoding/json`. The regex `"command"[[:space:]]*:[[:space:]]*"([^"\\]|\\.)*"`
   plus `head -1` is brittle against nested escapes, multi-line commands, and key
   ordering. Go decodes the documented hook schema once, correctly.

2. **Correct, ordered JSON output instead of `json.dumps`.** Both merge scripts
   write `json.dumps(result, indent=2)` with **no `sort_keys`**
   (`merge-mcp.py:105`, `merge-settings.py:42`), so output preserves Python dict
   *insertion order*. Verified: a fresh `merge-mcp` run emits
   `["gitnexus", "lean-ctx"]` in fragment-discovery order, not alphabetical.
   Go's default `encoding/json` marshal of a `map` sorts keys — that would
   reorder existing hand-added servers on the first Go run and produce noisy
   diffs and misleading backups. Go can do this *correctly* with an ordered
   structure (see §4), turning a latent footgun into a tested invariant.

3. **No `python3` + `bash` on the hot path.** The shell-guard fires on **every
   Bash tool call**. Today that is a `bash` process plus several `grep`/`sed`
   forks, and conditionally a `lean-ctx` subprocess. A single compiled binary
   that reads stdin, branches, and writes stdout removes the interpreter startup
   and the fork chain. This is the highest-frequency code in the repo and the
   clearest latency win.

4. **Testability.** Bash/Python glue here has zero unit tests; correctness rests
   on `bash -n` + `shellcheck` + manual `--dry-run` (`ci-check.sh:13-26`). Go
   gives table tests for hook precedence and golden-file tests for merge output
   against fixtures — see §8.

5. **One artifact, cross-compiled.** A single `agentic` binary for darwin
   arm64/amd64 and linux replaces "needs bash + python3 + correct PATH". The
   broader portability case is doc 04's; here it is simply the delivery vehicle.

### Where Go is NOT worth it (anti-over-engineering)

The repo's own principles say: simplest correct diff, no speculative
abstraction. Applying that honestly:

- **The eval harness stays Python — do not port it.** `evals/` is ~10 Python
  modules (`run.py`, `lint.py`, `report.py`, `selftest.py`, `bench.py`, `lib/`)
  that orchestrate LLM-judge subprocesses, parse JSONL, and emit `BENCHMARKS.md`.
  It is *development tooling*, not on any agent hot path, and it leans on
  Python's string/JSON ergonomics and the `claude -p` CLI. Porting it buys
  nothing for tokens or hook latency and would be a large, risky rewrite of code
  that is changing frequently (this branch is literally `value-evals-loop`).
  Keep it Python. The repo will still require `python3` *for development and CI*
  — but no longer on the **install or hook hot path**, which is the win that
  matters.

- **`bin/bootstrap.sh` stays shell (mostly).** Something has to install a
  toolchain on a bare machine *before* any Go binary exists. Bootstrap is a
  thin Homebrew driver (`bootstrap.sh:24-82`); rewriting it in Go is a
  chicken-and-egg problem. It changes only to *also* install Go and build/install
  `agentic` (see §6).

- **`bin/doctor.sh` and `bin/ci-check.sh`: port opportunistically, not
  urgently.** `doctor` is read-only health output; `ci-check` is a lint runner
  that *must* call the Python evals (`ci-check.sh:77,81,85`). Folding `doctor`
  into `agentic doctor` is a nice-to-have (one binary, structured checks).
  `ci-check` can become `agentic ci-check` that shells out to the Python eval
  steps — but there is no fragility or latency reason to rush either. They are
  the **lowest-priority** items in the backlog.

- **Do not build a plugin system, config DSL, or generalized "renderer
  framework."** The render logic (concatenate principles into `CLAUDE.md`,
  emit `.mdc` frontmatter for Cursor) is ~40 lines of straight-line string
  building (`providers/claude/install.sh:44-63`, `providers/cursor/install.sh:73-97`).
  Port it as straight-line Go. No template engine, no abstraction over
  "providers" beyond a small interface.

### Smallest version that still delivers the win

If we did only **one** thing: port **merge-mcp** and the **shell-guard hook** to
Go. Those two carry essentially all the fragility (grep/sed JSON, key ordering,
escape handling) and the only latency-sensitive code. Everything else
(install orchestration, settings merge, doctor, ci-check) is sequencing and
backups — valuable to consolidate, but not where the bugs live. The phased plan
(§7) front-loads exactly these two.

### What I would NOT port

- `evals/**` (stays Python — justified above).
- `bin/bootstrap.sh` core dep-install (stays shell; gains a Go-install step).
- The `lean-ctx`/`rtk`/`ast-grep` binaries themselves (third-party, installed by
  bootstrap, never vendored — `bootstrap.sh:51-63`, ARCHITECTURE.md:130).
- Cursor's static `hooks.json` and `mcp.overlay.json` — these are *data*, copied
  verbatim (`providers/cursor/install.sh:55`); no logic to port.

---

## 2. CLI surface

A single binary with a verb tree. Commands map 1:1 onto today's scripts so the
behavior contract is auditable.

```
agentic install   [--provider cursor|claude|all] [--dry-run]
agentic merge-mcp        <agentic_root> <output.json>      # internal-capable, also user-runnable
agentic merge-settings   <fragment.json> <output.json>
agentic hook shell-guard                                   # reads stdin, writes hook JSON
agentic doctor    [--deep]
agentic ci-check                                           # shells out to Python evals
agentic version
```

### Script → subcommand map

| Today | Becomes | Notes |
|-------|---------|-------|
| `bin/install.sh --provider X --dry-run` | `agentic install --provider X --dry-run` | Same flags (`install.sh:19-39`). Sources `secrets/.env` internally. |
| `providers/cursor/install.sh` | `agentic install --provider cursor` (internal `internal/install` cursor path) | No longer a separate script; logic moves into Go. |
| `providers/claude/install.sh` | `agentic install --provider claude` | Same. |
| `providers/shared/merge-mcp.py <root> <out>` | `agentic merge-mcp <root> <out>` | Keep positional args identical so existing fixtures/A-B harness call it unchanged during transition. |
| `providers/shared/merge-settings.py <frag> <out>` | `agentic merge-settings <frag> <out>` | Same positional contract. |
| `providers/claude/hooks/shell-guard.sh` | `agentic hook shell-guard` | Settings hook command line changes (see §5). |
| `bin/doctor.sh [--deep]` | `agentic doctor [--deep]` | Read-only; opportunistic port. |
| `bin/ci-check.sh` | `agentic ci-check` | Wrapper that runs Go-native shell/JSON checks **and** shells to `python3 evals/{lint,selftest,run}.py` (`ci-check.sh:77,81,85`). |
| `bin/bootstrap.sh` | **stays shell** | Gains "install Go + `go build`/`go install agentic`" step. |

Design choices:

- **`merge-mcp`/`merge-settings` remain first-class user-facing subcommands**, not
  hidden internals. Reason: the A/B verification (§7) and any future debugging
  need to invoke them directly with the same positional contract as the Python
  scripts. The `install` command calls the same `internal/` functions in-process
  (no subprocess), but the subcommands exist for parity testing.
- **`agentic hook shell-guard`** rather than a bare `agentic-hook` binary: one
  binary, discoverable verbs, and the hook path is explicit in `settings.json`.
- **`agentic ci-check` stays a thin wrapper, not a reimplementation.** It must
  keep calling the Python eval steps; reimplementing JSON/YAML lint in Go where
  Python already does it is duplicated surface for no gain. Lowest priority.

---

## 3. Package / repo layout

### Module path

Use the repo's existing remote identity. The repo is `Tsurai7/agentic-cfg`
(SETUP.md:22), so:

```
module github.com/Tsurai7/agentic-cfg
go 1.22
```

`go 1.22` (or whatever is current-stable at build time) is enough; nothing here
needs bleeding-edge generics. Pin in `go.mod` and the bootstrap.

### Layout

```
go.mod
go.sum
cmd/
  agentic/
    main.go            # flag/verb dispatch only; no logic
internal/
  install/
    install.go         # orchestration: provider dispatch, .env load, backups
    cursor.go          # cursor render: skills symlink, rules, hooks copy, principles->.mdc
    claude.go          # claude render: skills symlink, CLAUDE.md, mcp, settings
    backup.go          # timestamped backup + atomic write (shared)
    symlink.go         # idempotent ln -sfn equivalent (handles existing dir->.bak)
  mcpmerge/
    mcpmerge.go        # collect fragments, overlay, substitute, merge-into-existing
    resolve.go         # which(npx/lean-ctx), npm root -g, NODE_PATH
    dotenv.go          # parse secrets/.env, ~ expansion, env overrides
  settings/
    settings.go        # hooks block ownership, permissions.allow union, preserve env
  hook/
    shellguard.go      # the PreToolUse logic (pure, testable)
    envelope.go        # hook stdin/stdout JSON types
  jsonorder/
    ordered.go         # order-preserving JSON map (see §4) — the critical piece
  root/
    root.go            # AGENTIC_ROOT resolution (binary location + override)
testdata/              # golden fixtures (see §8)
```

Rationale: `internal/` keeps everything unexported (no accidental external API to
maintain). `cmd/agentic/main.go` is dispatch-only so the logic is unit-testable
without the CLI. `internal/jsonorder` is isolated because ordered JSON is the
one genuinely tricky requirement and deserves its own tests.

### Locating config fragments at runtime: `AGENTIC_ROOT`

Today every script computes the root from its own location, e.g.
`AGENTIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`
(`install.sh:5`, `providers/claude/install.sh:5` uses `/../..`). The Go binary
cannot assume it lives at a fixed depth inside the repo, so resolve the root in
this priority order:

1. **`--root` flag / `AGENTIC_ROOT` env** — explicit override, highest priority.
   Needed because `go install` puts the binary in `$GOBIN`, *outside* the repo.
2. **Walk up from the executable path** (`os.Executable()`), looking for a repo
   marker (presence of `core/` + `integrations/` + `providers/`). Works when the
   binary is built into `bin/` or run from a checkout.
3. **Walk up from the current working directory** with the same marker — covers
   `go run ./cmd/agentic` from the repo and the common "I'm cd'd into the repo"
   case.

This is a real behavior change from the shell scripts (which rely purely on
script location) and must be called out: because `go install` decouples the
binary from the repo, **`AGENTIC_ROOT` becomes the canonical way to point the
hook and installer at the source tree**. The Claude `settings.json` hook command
should therefore pass `--root` explicitly (see §5) rather than rely on
discovery, since the hook runs from arbitrary project directories.

---

## 4. Behavior-preserving semantics

This section is the contract. Each invariant below is currently implemented in
shell/Python; the Go port must preserve it (or, where noted, *fix* a verified
bug — those fixes belong to doc 03's catalog, sequenced here).

### 4.0 Ordered JSON output (the cross-cutting requirement)

**Invariant:** merged JSON preserves existing key order and appends new keys in a
deterministic order; output is `indent=2` + trailing newline, matching
`json.dumps(result, indent=2) + "\n"` (`merge-mcp.py:105`,
`merge-settings.py:42`). Python preserves insertion order; Go's `map`
serialization does **not**.

**Implementation:** do *not* marshal `map[string]any`. Use one of:

- A small ordered-map type in `internal/jsonorder` backed by a slice of
  key/value pairs with a custom `MarshalJSON` that emits keys in stored order; or
- `encoding/json` with `json.RawMessage` for pass-through subtrees we never
  rewrite (e.g. a hand-added server's full body), so only the keys we manage are
  re-encoded and untouched subtrees keep their byte form.

The merge algorithm reads the existing target, keeps its key order, overwrites
managed keys *in place* (preserving their position if already present), and
appends genuinely new managed keys in a fixed order (fragment-discovery order via
`sorted(glob("**/mcp*.json"))`, `merge-mcp.py:75`). This is the single most
important byte-compat task; the golden tests in §8 lock it down.

### 4.1 merge-mcp invariants (`internal/mcpmerge`)

Each maps to current code:

1. **Preserve hand-added servers.** Read existing output, `update` managed
   servers into it, never drop unmanaged keys (`merge-mcp.py:98-102`,
   ARCHITECTURE.md:86-89). Go: load existing into the ordered map, set managed
   keys, leave the rest.
2. **Per-machine tool resolution.** `NPX` ← `which npx`; `NODE_PATH` ←
   `npm root -g` (10s timeout) else `$NODE_PATH`; `LEAN_CTX` ← `which lean-ctx`;
   `LEAN_CTX_DATA_DIR` ← `~/.lean-ctx`; `PATH` passthrough
   (`merge-mcp.py:14-40`). Go: `exec.LookPath`, `exec.CommandContext` with
   `context.WithTimeout` for `npm root -g`.
3. **`__KEY__` placeholder substitution** over all string values, recursively
   (`merge-mcp.py:52-61`). Go: recurse the decoded tree, `strings.ReplaceAll`
   `"__"+key+"__"` → value for every env entry.
4. **`secrets/.env` overrides auto-detected values, with `~` expansion.** Parse
   `KEY=VALUE`, skip blanks/`#`, strip surrounding quotes, `expanduser` the value
   (`merge-mcp.py:41-48`). Go: line parse + `strings.TrimSpace`/trim quotes +
   expand leading `~` to `$HOME`. **Order matters:** auto-detected first, then
   `.env` overwrites (`merge-mcp.py:33-48`).
5. **Overlay base.** `providers/cursor/mcp.overlay.json` is the base, fragments
   merge on top (`merge-mcp.py:90-95`). Today the overlay is `{"mcpServers":{}}`
   (verified empty) — preserve the mechanism regardless.
6. **Fail on malformed JSON with the file path.** `merge-mcp.py:64-68` raises
   `SystemExit("merge-mcp: invalid JSON in {path}: {exc}")`. Go: wrap decode
   errors with the path and exit non-zero, same message shape.

**Backups are NOT in this code.** Verified: `merge-mcp.py` does a plain
`output.write_text(...)` (`:104-105`) with no backup and **non-atomic** write.
The backup happens in the *callers*: `providers/claude/install.sh:71`
(`cp "$out" "${out}.bak.$(date +%s)"`) and `providers/cursor/install.sh:36`.
ARCHITECTURE.md:79-80 says "all destructive writes back up" — that is true only
because the install scripts wrap the merge. In Go, `agentic install` owns the
backup (via `internal/install/backup.go`) and `agentic merge-mcp` invoked
standalone does **not** back up (matching today's `merge-mcp.py`). Keep that
split explicit, or the standalone subcommand silently gains a behavior the
Python never had. *(Whether to make the write atomic is a doc-03 fix; see §4.4.)*

### 4.2 merge-settings invariants (`internal/settings`)

1. **Repo owns the `hooks` block** — replace wholesale if present in the fragment
   (`merge-settings.py:32-34`).
2. **Union `permissions.allow`**, sorted, deduped; keep existing `deny` and any
   other permission keys (`merge-settings.py:35-39`). Go: set-union into a
   `[]string`, `sort.Strings`. This one *is* sorted today, so Go sorting matches.
3. **Preserve machine-local `env` and every other top-level key.** The fragment
   only contributes `$schema`, `hooks`, `permissions`; everything else in the
   target survives untouched (`merge-settings.py:29-39`, ARCHITECTURE.md:131-132).
   Go: start from the decoded existing file (ordered), mutate only those three.
4. **`$schema` handling — fix the verified bug.** `merge-settings.py:31`
   `result.setdefault("$schema", fragment.get("$schema"))` emits
   `"$schema": null` when the output is new and the fragment has no `$schema`.
   **Verified live**: with a `$schema`-less fragment and a fresh output file, the
   result contains `"$schema": null`. The shipped fragment has a `$schema`
   (`settings.hooks.json:2`) so it is latent today, but the Go port should only
   set `$schema` when the fragment actually provides one. *(Defect catalog entry
   owned by doc 03; the Go rewrite is the natural fix. Master plan: decide
   whether 03 patches the Python first for parity, or accepts the Go version as
   the fix and the golden test asserts the corrected behavior.)*

### 4.3 install invariants (`internal/install`)

1. **Timestamped backups before destructive writes.** Every overwrite of a
   generated file first does the equivalent of `cp "$out" "${out}.bak.$(date +%s)"`
   (`providers/claude/install.sh:42,71,91`; `providers/cursor/install.sh:36,53`).
   Go: `backup.go` copies to `out + ".bak." + strconv(unixSeconds)`.
   **Decision:** preserve the second-resolution `$(date +%s)` suffix exactly, so
   `.bak.*` files match the existing `.gitignore` pattern (`*.bak`) and existing
   muscle memory. Note the known collision risk of second-resolution timestamps;
   keep it for compatibility rather than "improving" to nanoseconds (out of
   scope — flag only).
2. **`DRY_RUN` prints intended actions, writes nothing.** `--dry-run` →
   `DRY_RUN=1` (`install.sh:25-27`); each provider's `run()` and explicit
   `[[ "$DRY_RUN" == "1" ]]` guards print `[dry-run] …` and skip
   (`providers/claude/install.sh:9-15,37-40,73-77,86-89`). Go: a `dryRun bool`
   threaded through; every filesystem mutator checks it and logs the same
   `[provider] [dry-run] …` line shape so existing snapshot expectations hold.
3. **`AGENTIC_ROOT` from binary/CWD (see §3)**, plus source `secrets/.env` once
   at the top so env is available to the merge step (`install.sh:44-50`).
4. **Symlink skills (and Cursor rules).** `ln -sfn source target`, but if the
   target is a real directory, back it up to `target.bak.$(date +%s)` first; if a
   symlink, replace it (`providers/claude/install.sh:17-31`,
   `providers/cursor/install.sh:17-31,59-71`). Go: `symlink.go` replicates the
   `-L`/`-d` branch with `os.Lstat`.
5. **Render `CLAUDE.md`** = stub with `__AGENTIC_ROOT__` substituted + `AGENTS.md`
   + each `core/principles/*.md` (skip `README.md`) + each
   `core/instructions/user-rules/*.md` with a `### <name>` header
   (`providers/claude/install.sh:33-65`). Straight-line Go string building; no
   template engine.
6. **Render Cursor principles to `.mdc`** with the
   `---\ndescription:…\nalwaysApply: true\n---` frontmatter
   (`providers/cursor/install.sh:73-97`), and copy `hooks.json` verbatim
   (`:46-57`). Data copy + small string build.
7. **`chmod +x` on hook scripts** — once the hook is the `agentic` binary this
   step changes meaning (the binary is already executable); see §5/§6.
8. **`__AGENTIC_ROOT__` injection into the settings fragment.** Today done via a
   `mktemp` + `sed` then passed to `merge-settings.py`
   (`providers/claude/install.sh:93-99`). In Go this is an in-memory string
   replace before the in-process settings merge — no temp file.

### 4.4 Atomicity (flagged, scoped)

The Python merges use `write_text` (`merge-mcp.py:105`, `merge-settings.py:42`)
— **not atomic**. A crash mid-write can truncate `mcp.json`/`settings.json`.
The shell `cp` backup runs *before* the write, so the prior file survives, but
the in-progress write is not a temp-then-rename. Go can trivially do
write-temp-then-`os.Rename` (atomic on the same filesystem). This is a small
*improvement* the port enables; whether to adopt it is a doc-03 decision since it
technically changes behavior. Recommendation: adopt atomic writes in Go (no
downside, removes a real failure mode) and note it in 03.

---

## 5. The shell-guard hook in Go

This is the highest-frequency code in the repo (every Bash tool call) and the
clearest fragility win. Today: `shell-guard.sh:1-78`.

### Logic to preserve (3-rule precedence, exactly one fires)

1. **Decode the hook envelope from stdin** with `encoding/json` into a typed
   struct — kills the `grep`/`sed` extraction (`shell-guard.sh:17-37`). Fields
   needed: `tool_name`, `tool_input.command`. Unknown fields ignored. A missing
   key yields empty string (today via `|| true`), so Go treats absent/zero as
   "not applicable" and exits 0.
2. **Gate on tool name** — only `Bash|bash|PowerShell|powershell`
   (`shell-guard.sh:31-34`); anything else exits 0 with no output.
3. **Empty command → exit 0** (`shell-guard.sh:37`).
4. **Already-wrapped passthrough** — if the command starts with `lean-ctx ` or
   `rtk `, exit 0 (`shell-guard.sh:40-42`). Preserve, but see the open question
   on whether prefix-only matching is too narrow (e.g. `env FOO=bar rtk …`).
5. **Heredoc passthrough — fix the over-broad match.** Today `case "$CMD" in
   *'<<'*) exit 0` (`shell-guard.sh:46-48`). **Verified over-broad**: it also
   matches `echo $((1 << 4))` and a quoted `awk "x << y"`, silently skipping the
   guard. The intent is "real heredoc/here-string". In Go, detect a here-doc/
   here-string more precisely (e.g. a `<<` or `<<-` followed by a word/quote
   token, or `<<<`), not any `<<` substring. *(This is a doc-03 correctness bug;
   the Go rewrite is the fix. Master plan must decide if 03 also tightens the
   shell version for the transition window.)*
6. **Rule 1 — ast-grep deny for code-targeted grep.** Fire only when the command
   contains a `grep|egrep|fgrep|rg` token **and** a code-file extension appears
   (`shell-guard.sh:50-60`, `CODE_EXT` at `:53`). Emit a `deny` envelope with the
   `sg -p …` reason. In Go, replicate both regexes (`(^|[|&;]| )(grep|egrep|fgrep|rg)( |$)`
   and `\.(go|cs|py|…)(\b|['"]|$)`) with the `regexp` package so the predicate is
   identical and unit-testable. The `head -1`/JSON-escaping fragility disappears
   because we `json.Marshal` the envelope.
7. **Rule 2 — lean-ctx delegate.** If `lean-ctx` is on PATH, pipe the raw stdin
   to `lean-ctx hook rewrite`; honor its output **only if it contains an
   `updatedInput`/`updated_input`** (`shell-guard.sh:62-71`). Go: `exec.LookPath`
   + `exec.Command` feeding the original stdin bytes, parse the response, check
   for the rewrite field, pass it through verbatim.
8. **Rule 3 — rtk fallback.** If `rtk` exists, emit an `allow` envelope with
   `updatedInput.command = "rtk " + CMD` (`shell-guard.sh:73-77`); if `rtk` is
   absent, exit 0 (no output). Go: build the struct, `json.Marshal`. Escaping is
   automatic.

### Envelope output

Both the `deny` and `allow` envelopes are tiny fixed JSON shapes
(`shell-guard.sh:58,77`). Define Go structs with the exact field names
(`hookSpecificOutput.hookEventName="PreToolUse"`, `permissionDecision`,
`permissionDecisionReason`, and the `updatedInput.command` variant) and
`json.Marshal` them. This is where the manual `sed 's/\\/\\\\/g;s/"/\\"/g'`
escaping (`shell-guard.sh:57,76`) — itself a fragility source — is deleted.

### How `settings.json` references the binary

Today: `__AGENTIC_ROOT__/providers/claude/hooks/shell-guard.sh`
(`settings.hooks.json:7`). New form — invoke the verb and pass the root
explicitly so discovery is not needed from an arbitrary project CWD:

```json
{ "type": "command",
  "command": "__AGENTIC_BIN__ hook shell-guard --root __AGENTIC_ROOT__" }
```

At install time, `agentic install` substitutes both `__AGENTIC_BIN__` (the
resolved path to the installed `agentic` binary) and `__AGENTIC_ROOT__` (as today)
into the fragment before the settings merge. `--root` lets the hook resolve
`secrets/.env`/fragments without walking from the binary location. (For
shell-guard specifically the root is barely needed — it only consults
`lean-ctx`/`rtk` on PATH — but passing it keeps every subcommand uniform and
future-proofs the hook if it ever needs repo data.)

### Distribution concern: the binary must exist before the hook fires

This is the critical ordering constraint. The hook command references
`__AGENTIC_BIN__`; if that path does not exist when Claude fires a PreToolUse
event, **every Bash call breaks**. Mitigations (chosen approach in §6/§7):

- `agentic install` must only write the binary path into `settings.json` *after*
  verifying the binary exists and is executable at that path.
- During the transition, keep the shell hook as the fallback so a half-installed
  state degrades to the working shell version rather than a broken hook (§7).
- The hook itself must **fail open**: on any internal error (bad stdin, lean-ctx
  crash), exit 0 with no output so a hook bug never blocks the user's command.
  Today the shell version largely does this via `|| true` and unconditional
  `exit 0` paths; the Go version must be deliberate about it (recover from
  panics, treat decode errors as "pass through").

---

## 6. Build & distribution

### How users get the binary

Three options, evaluated against the north-star "install cleanly on a fresh
machine AND on one that already has the user's configs":

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| `go install github.com/Tsurai7/agentic-cfg/cmd/agentic@…` | Standard, no committed binaries | Needs Go; binary lands in `$GOBIN` outside repo (must set `AGENTIC_ROOT`) | Secondary path |
| **`go build` in bootstrap → install into repo `bin/`** | Binary lives next to repo; root discovery works; reproducible from the checkout | Needs Go at bootstrap | **Primary** |
| Commit prebuilt binaries | Zero build step | Binary bloat in git, multi-arch, security/trust, staleness | **No** (violates "catalog don't vendor" spirit) |

**Chosen:** bootstrap installs Go (already partially present —
`bootstrap.sh:69` installs Go for `no-mistakes`), then `go build -o
bin/agentic ./cmd/agentic` from the checkout. The binary sits at
`<repo>/bin/agentic`, so executable-relative root discovery (§3) just works and
the hook path is stable. Offer `go install` as a documented alternative for users
who prefer `$GOBIN` (they then set `AGENTIC_ROOT`).

### Bootstrap changes (`bin/bootstrap.sh`)

Bootstrap already installs Go when needed (`bootstrap.sh:69`). Changes:

- Hoist Go to a **required** dep (it currently installs Go only inside the
  optional `no-mistakes` block). Add a `brew_install go` near the required deps
  (`bootstrap.sh:42-51`).
- After deps, before `bin/install.sh`, build the binary:
  `go build -o "${AGENTIC_ROOT}/bin/agentic" "${AGENTIC_ROOT}/cmd/agentic"`.
- Replace the `bash "${AGENTIC_ROOT}/bin/install.sh" …` call (`bootstrap.sh:86`)
  with `"${AGENTIC_ROOT}/bin/agentic" install --provider "$PROVIDER"` **once the
  install port lands** — until then, keep calling the shell installer (§7).
- Keep the non-macOS guard (`bootstrap.sh:18-22`) but soften the message: with a
  static Go binary, the only hard deps on Linux become Go (to build) + node/gh;
  the portability story is doc 04's.

### Cross-compilation & versioning

- **Targets:** `darwin/arm64`, `darwin/amd64`, `linux/amd64`, `linux/arm64`
  via `GOOS`/`GOARCH`. CGO off (`CGO_ENABLED=0`) for a fully static binary — we
  use only stdlib (`os`, `os/exec`, `encoding/json`, `regexp`, `path/filepath`).
- **Versioning:** stamp `cmd/agentic` with `-ldflags "-X main.version=$(git
  describe --tags --always)"`; `agentic version` prints it. Tie a tag to the
  schema/behavior so `doctor` can warn on a stale binary vs repo.
- For local dev, `go run ./cmd/agentic …` is the inner loop; no build needed.

---

## 7. Migration & rollback plan

Phased, fragility-first, with the shell/Python kept as a working fallback the
whole way. Each phase is independently shippable and verifiable.

### Phase 0 — Scaffold (no behavior change)

Create `go.mod`, `cmd/agentic/main.go` (verb dispatch), `internal/jsonorder`,
and the test harness. `agentic version` works. Nothing else wired. Add Go to CI
(doc 05 owns the matrix).

### Phase 1 — Port **merge-mcp** (highest fragility-reduction)

Implement `internal/mcpmerge` + `agentic merge-mcp <root> <out>` with the §4.0/§4.1
invariants and **ordered output**. Do **not** switch the installers yet.

A/B verify (the cut-over gate):

```
# golden parity against the Python on real fragments
python3 providers/shared/merge-mcp.py "$ROOT" /tmp/py_mcp.json
bin/agentic           merge-mcp        "$ROOT" /tmp/go_mcp.json
diff <(cat /tmp/py_mcp.json) <(cat /tmp/go_mcp.json)
```

The diff must be **empty** for the byte-compat cases (existing servers, ordering,
indentation, trailing newline). Where the Go output *intentionally* differs
(e.g. it must NOT differ here — merge-mcp has no known bug to fix), document it.
Run this across a matrix of inputs: empty target, target with hand-added
servers, target with the managed servers already present (ordering test),
malformed JSON (both must fail with the path).

### Phase 2 — Port **merge-settings**

`internal/settings` + `agentic merge-settings`. Same A/B diff harness. Here the
Go output **intentionally differs** in exactly one case: it must NOT emit
`"$schema": null` (the verified bug, §4.2). The golden test asserts the corrected
output; the A/B script special-cases that one line and documents it. Coordinate
with doc 03 on whether the Python is patched first for a clean diff.

### Phase 3 — Port **install** orchestration

`internal/install` (+ cursor/claude paths) and `agentic install
--provider … --dry-run`. Verify by:

- **Dry-run snapshot diff:** capture `bin/install.sh --provider all --dry-run`
  output and `agentic install --provider all --dry-run`; they should describe the
  same actions (allowing for the cosmetic `[dry-run]` line-shape we deliberately
  matched in §4.3).
- **Real-install fixture test:** run both against a throwaway `$HOME` (point
  `HOME` at a tempdir) and `diff -r` the resulting trees (symlinks, `CLAUDE.md`,
  `mcp.json`, `settings.json`), ignoring `.bak.*` timestamp suffixes.

### Phase 4 — Port the **hook**

`internal/hook` + `agentic hook shell-guard`. Keep the shell hook file in place.
Switch `settings.hooks.json` to reference `__AGENTIC_BIN__ hook shell-guard
--root __AGENTIC_ROOT__` (§5) **only after** Phase 3 makes `agentic install`
write the verified binary path. Table tests (§8) plus a live A/B: feed a corpus
of hook stdin JSON to both `shell-guard.sh` and `agentic hook shell-guard` and
diff the emitted envelopes. The intentional differences are the heredoc-breadth
fix and any JSON-escaping correctness; everything else must match.

### Phase 5 — Flip bootstrap

Change `bootstrap.sh` to build `bin/agentic` and call `agentic install`
(§6). Keep the shell scripts in the tree for one release as a documented
fallback (`AGENTIC_USE_SHELL=1` could route bootstrap back to `bin/install.sh`),
then remove them in a follow-up once the Go path has soaked.

### Rollback

Because each phase keeps the shell/Python equivalent intact and the subcommands
share the Python's positional contract, rollback at any phase is "stop calling
the Go subcommand; call the script." The hook is the riskiest flip — its rollback
is reverting the one-line `command` in the generated `settings.json` back to the
`shell-guard.sh` path (and re-running install). The fail-open requirement (§5)
means even a buggy Go hook degrades to "command runs unwrapped," never "command
blocked."

### A/B byte-match summary

| Component | Expected vs Python/shell | Intentional differences |
|-----------|--------------------------|-------------------------|
| merge-mcp | **byte-identical** | none |
| merge-settings | byte-identical except `$schema` | drop `"$schema": null` (bug fix) |
| install (dry-run) | same actions | cosmetic log shape only |
| install (real) | identical tree (ignore `.bak.*`) | atomic write (no observable diff) |
| hook | identical envelopes | tighter heredoc detection; correct escaping |

---

## 8. Test strategy for the Go code

Owns: Go unit/golden/table tests for the ported code. Cross-link:
`plans/05-test-coverage.md` owns the overall coverage strategy and the CI matrix
(where these tests run, alongside the retained Python eval suite and the existing
`bin/ci-check.sh` static checks).

### Golden-file tests for the merges

- Put input fixtures under `testdata/mcpmerge/<case>/` (an `integrations/`-shaped
  fragment set + an existing target) and a `want.json`. Reuse the *real*
  fragments (`integrations/gitnexus/mcp.stdio.json`,
  `integrations/lean-ctx/mcp.stdio.json`) as one case so the test tracks reality.
- Cases that lock the invariants: empty target; target with a hand-added server
  (preservation); target with managed servers already present in a **different
  order** (the ordering invariant, §4.0); `.env` override beats auto-detect;
  `__KEY__` substitution; malformed JSON → error contains the path.
- Resolution (`which npx`, `npm root -g`) must be **injected** (an interface or
  function field), not called for real, so golden output is deterministic across
  machines. This is the main testability design point.
- A `-update` flag regenerates goldens (standard Go golden pattern).

### Table tests for the hook precedence

- Each row: input stdin JSON → expected stdout (envelope or empty) + expected
  exit behavior. Cover: non-Bash tool (no-op); empty command; already-wrapped
  `rtk `/`lean-ctx `; **heredoc true positive** (`cat <<EOF`) and the **verified
  false positives that must now be guarded** (`echo $((1<<4))`, quoted `<<`);
  grep-on-`.go` → deny; grep-on-`.log` → not deny; rg-on-code → deny; plain
  `python3 …` → rtk fallback; nested-quote command (the escaping case the shell
  version handles fragilely) → correct envelope.
- `lean-ctx`/`rtk` presence and `lean-ctx hook rewrite` output must be injectable
  (stub the exec) so rule 2/3 are tested without the binaries installed.
- **Fail-open test:** malformed stdin → exit 0, no output.

### Dry-run snapshot tests for install

- Run `agentic install --provider all --dry-run` with `HOME` and `AGENTIC_ROOT`
  pointed at fixtures; assert the printed action list matches a committed
  snapshot. This is the cheap guard that the orchestration didn't silently change.

### Parity tests (transition only)

- A build-tagged test (or a `make parity` target) that runs the Python script and
  the Go subcommand on the same inputs and diffs — the §7 A/B harness, automated.
  Removed once the Python is retired.

---

## 9. Risks & open questions

**Risks**

1. **Hook-binary ordering (highest).** If `settings.json` points at a binary that
   doesn't exist, every Bash call breaks. Mitigation: install writes the path only
   after verifying the binary; fail-open hook; shell fallback during transition
   (§5, §7).
2. **JSON key-order regressions.** A naive `map[string]any` marshal silently
   reorders and produces noisy diffs/misleading backups. Mitigation: dedicated
   `internal/jsonorder` + ordering golden tests (§4.0, §8). This is the most
   likely place a "looks fine" port is actually wrong.
3. **Subcommand backup semantics drift.** Backups live in the install scripts,
   not the merge scripts (verified). If the Go `merge-mcp` subcommand adds a
   backup "to be safe," it diverges from Python behavior. Keep the split explicit
   (§4.1).
4. **lean-ctx contract coupling.** Rule 2 depends on `lean-ctx hook rewrite`
   emitting an `updatedInput`/`updated_input` field (`shell-guard.sh:67`). If
   lean-ctx changes that field name/shape, the Go matcher must track it. Pin the
   field-name expectation in a test and a comment.
5. **Go becomes a required dep.** Today bootstrap installs Go only for the
   optional `no-mistakes` (`bootstrap.sh:69`). Making it required raises the
   floor slightly; acceptable given Go is already pulled in and the static-binary
   payoff (doc 04).
6. **Scope creep into a "framework."** The temptation to generalize "providers,"
   add a template engine, or port the evals. Mitigation: the explicit
   non-goals in §1 and the smallest-version cut.

**Open questions (for the master plan / siblings)**

- **Sequencing vs doc 03.** Three verified bugs (`$schema: null`; over-broad
  heredoc; non-atomic writes) are naturally fixed by the Go port. Does 03 patch
  the shell/Python first (so A/B diffs are clean), or do we accept the Go version
  as the fix and have goldens assert corrected behavior? My recommendation: let
  Go fix them, document the one-line intentional diffs in §7, and have 03
  reference this doc for those three.
- **Is the already-wrapped check (`shell-guard.sh:40-42`) too narrow?** It only
  matches a leading `rtk `/`lean-ctx `. Commands like `env X=1 rtk …` or
  `sudo rtk …` would be re-wrapped. Worth deciding the intended contract before
  freezing it in Go tests. (Flagged, not owned here.)
- **`AGENTIC_BIN` vs PATH.** Should the hook reference an absolute
  `__AGENTIC_BIN__` (robust, but breaks if the repo moves) or bare `agentic`
  (relies on PATH/`$GOBIN`)? I lean absolute-path-written-at-install for the
  hook, bare `agentic` for interactive use.
- **Windows.** Out of scope here (doc 04), but the symlink and `chmod` logic
  (§4.3) is the part that won't translate; the merges and hook will. Worth doc 04
  confirming whether Windows is even a target.
- **Do we keep `merge-mcp`/`merge-settings` as user-facing subcommands long-term,
  or hide them once the Python is gone?** Keeping them aids debugging; hiding them
  shrinks surface. Defer to post-transition.

---

## 10. Prioritized backlog

Severity/value: **High** = fragility/latency/correctness on the hot path or
cut-over blocker; **Med** = consolidation win; **Low** = nice-to-have.
Effort: S ≤ ~½ day, M ~1–2 days, L > 2 days.

| ID | Title | Value | Effort | Depends-on |
|----|-------|-------|--------|------------|
| GO-01 | Scaffold module, `cmd/agentic` dispatch, `agentic version`, CI build | High | S | — |
| GO-02 | `internal/jsonorder` ordered-map + tests (locks byte-compat) | High | M | GO-01 |
| GO-03 | Port merge-mcp (`internal/mcpmerge`, `agentic merge-mcp`) with injectable tool resolution | High | M | GO-02 |
| GO-04 | merge-mcp golden tests + Python A/B parity harness | High | M | GO-03 |
| GO-05 | Port shell-guard hook (`internal/hook`, `agentic hook shell-guard`), fail-open | High | M | GO-02 |
| GO-06 | Hook table tests incl. heredoc false-positive fixes + escaping + lean-ctx stub | High | M | GO-05 |
| GO-07 | Port merge-settings (`internal/settings`), drop `$schema: null` | High | S | GO-02 |
| GO-08 | merge-settings golden + A/B (document the `$schema` intentional diff) | Med | S | GO-07 |
| GO-09 | `internal/root` AGENTIC_ROOT resolution (flag/env/exe-walk/cwd-walk) | High | S | GO-01 |
| GO-10 | Port install orchestration + cursor/claude render (`internal/install`), backups, dry-run, atomic writes | High | L | GO-03, GO-07, GO-09 |
| GO-11 | Install dry-run snapshot + real-install tempdir `diff -r` tests | High | M | GO-10 |
| GO-12 | Switch `settings.hooks.json` to `__AGENTIC_BIN__ hook shell-guard --root …`; install verifies binary exists before writing path | High | S | GO-05, GO-10 |
| GO-13 | Bootstrap: Go as required dep, `go build -o bin/agentic`, call `agentic install` (shell fallback retained) | High | S | GO-10 |
| GO-14 | Cross-compile targets (darwin arm64/amd64, linux) + version stamping | Med | S | GO-01 |
| GO-15 | Port `bin/doctor.sh` → `agentic doctor [--deep]` | Med | M | GO-09 |
| GO-16 | `agentic ci-check` wrapper (Go static checks + shell out to Python evals) | Low | S | GO-15 |
| GO-17 | Retire shell/Python glue after soak; keep `evals/` Python | Med | S | GO-11, GO-12, GO-13 |

Critical path to the core win (fragility + hot-path latency): **GO-01 → GO-02 →
{GO-03/GO-04, GO-05/GO-06, GO-07/GO-08}**. Install/bootstrap (GO-10, GO-13) and
the hook flip (GO-12) follow. Doctor/ci-check (GO-15, GO-16) are deferrable.

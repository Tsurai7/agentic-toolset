# 03 — Gaps and bugs (what is broken or will break)

## Scope & ownership

This document is the **adversarial defect inventory** for the executable surface of the
repo: the Claude `shell-guard.sh` PreToolUse hook, the two Python merge scripts, the
shell installers (`bin/*.sh`, `providers/*/install.sh`), the eval harness (`evals/*.py`),
and the committed config/JSON. Every finding is a *concrete* defect — a wrong output, a
silent no-op, a corrupted command, a doc that contradicts behavior — not a style
preference. Where a bug was reproduced in a scratch copy under `/tmp` (never the installed
hook, never `$HOME`, never a repo file), the observed output is included and the finding is
marked **Observed**; everything else is marked **Inferred** with a confidence level.

What this document defers to its siblings (referenced, not duplicated):

- **Go-rewrite design** → [`01-go-rewrite.md`](../plans/01-go-rewrite.md). The remediation table
  cross-references which bugs disappear for free under a real JSON parser + structured
  exec, versus which need a shell fix *now* because the rewrite is not landed.
- **Strategy / maturity** → [`02-maturity-review.md`](../plans/02-maturity-review.md).
- **Portability as a strategy** → [`04-portability-review.md`](../plans/04-portability-review.md). I
  *report* portability bugs I found (BSD vs GNU `sed`, bash 3.2) and cross-link, but the
  compat strategy is theirs.
- **Test-coverage gaps** ("what is untested") → [`05-test-coverage.md`](../plans/05-test-coverage.md).
  I own *bugs in the harness code*; I defer the coverage assessment.

### Severity summary

| Severity | Count | IDs |
|----------|-------|-----|
| Critical | 2 | BUG-01, BUG-02 |
| High     | 6 | BUG-03, BUG-04, BUG-05, BUG-06, BUG-07, BUG-08 |
| Medium   | 9 | BUG-09 … BUG-17 |
| Low      | 6 | BUG-18 … BUG-23 |
| **Total** | **23** | |

> **✅ Resolved — ALL 23/23 (improvement-loop, 2026-06-30):** BUG-01–08 (hook cluster),
> BUG-10–23 fixed, BUG-09 closed as won't-fix-by-design. Both Criticals, all six Highs, and
> every Medium/Low are now addressed. See `plans/IMPROVEMENT-LOOP.md` for the per-iteration log
> and the bench backing each fix.

The dominant theme: `shell-guard.sh` parses a structured JSON protocol with
`grep`/`sed`/`case` glob matching. That approach is wrong in kind, not in detail — it
produces both **false denies** (blocks legitimate plain-text greps) and **silent
command corruption** (multiline commands) and **silent skips** (bit-shift mistaken for a
heredoc). These are the Critical/High cluster and they are exactly what the Go rewrite
(doc 01) exists to eliminate.

A note on reproduction method: several bugs were demonstrated by feeding crafted hook
JSON to a `/tmp` copy of `shell-guard.sh` under a controlled `PATH` (an `rtk` stub
present, `lean-ctx` absent) so the deterministic branch could be observed in isolation.
Both `rtk` and `lean-ctx` are installed on this machine, so in production the lean-ctx
delegate (branch 2) and rtk fallback (branch 3) are both live; the guards at lines 40–48
run *before* either, so the heredoc/double-wrap bugs fire regardless of which downstream
tool is present.

---

## Area 1 — `shell-guard.sh` (the hook)

File: `providers/claude/hooks/shell-guard.sh`.

> **✅ RESOLVED — BUG-01…BUG-08 cluster (improvement loop, 2026-06-30).** The whole cluster is
> closed on the primary path. `shell-guard.sh` now `exec`s the Go hook (`bin/agentic hook
> shell-guard`, `internal/hook/hook.go`) when the binary is built — the default, since
> `bootstrap.sh` builds it. The Go hook parses the hook JSON with a real decoder (eliminating
> the grep/sed string-munging → BUG-01/05/08) and **fails open** on any command a wrapper would
> mangle: `<<`/heredocs, embedded newlines, `$(…)`/backticks, `cd` chains (BUG-02/04 by design —
> never mangle, accepting that e.g. a bit-shift goes uncompressed). The ast-grep deny strips
> quoted substrings before the code-extension test (BUG-03); the wrapped-check strips leading
> `VAR=` assignments (BUG-06); Go returns 0 on any internal error, so a parse miss degrades to
> pass-through, never a spurious deny (BUG-07). The shell fallback below was hardened the same
> way for machines without the Go binary. Defended by `internal/hook/hook_test.go` (quoted-pattern
> grep not denied, code-file deny, env-prefix no-double-wrap, heredoc/multiline/bit-shift/
> command-subst fail-open, unparseable-input fail-open). Residual edge (not a regression): a
> non-code file whose name embeds a code extension mid-token (e.g. `report.go.txt`) can still
> trip the deny — rare, and grep there is uncommon. Per-bug headings keep their original
> severity for history.

### BUG-01 — Multiline / escaped-whitespace commands are silently corrupted — Critical — **Observed**

`shell-guard.sh:19-28` (`extract`) and `:76` (`JSON_CMD` re-escape).

**What.** `extract()` pulls the JSON `command` string with `grep -oE`/`sed`, unescaping
only `\"`→`"` and `\\`→`\` (the two `sed` clauses at line 26). It does **not** decode any
other JSON string escape — `\n`, `\t`, `\r`, `\uXXXX`, `\/`. The re-emit at line 76 only
re-escapes `\` and `"`. So a `command` whose JSON value contains `\n` (a real newline in
the intended command) is extracted as the literal two characters backslash-n, then handed
back to Claude verbatim.

**Why (repro).** Crafted hook input `{"tool_name":"Bash","command":"echo a\necho b"}` —
on disk the bytes are `echo a\necho b` (JSON-escaped newline), the *correct* decoded
command is two lines (`echo a` then `echo b`). Fed to the scratch hook:

```
### D2-multiline(echo a\necho b)  (mode=rtk)
--- exit=0
--- stdout: [{"hookSpecificOutput":{...,"updatedInput":{"command":"rtk echo a\\necho b"}}}]
```

The emitted `updatedInput.command` is `rtk echo a\necho b` with a **literal** backslash-n,
not a newline. When Claude executes that, the second command never runs (`echo` prints the
literal string). Any heredoc-free multiline Bash command (a `for` loop on multiple lines, a
`&&`-less multi-statement block, an embedded `\t`) is silently mangled. This is a
correctness bug that changes what the user's command *does*.

**Fix.** Stop string-munging JSON. Parse stdin with a real JSON reader and re-serialize
with a real encoder. In shell-only terms that means piping through `python3 -c 'import
json,sys; …'` (python3 is already a hard dependency) or `jq`. Under the Go rewrite (doc
01) this is `encoding/json` and the bug cannot exist. Until then, every multiline command
is at risk.

### BUG-02 — `*'<<'*` matches bit-shift and any `<<` substring; wrapping silently skipped — Critical — **Observed**

`shell-guard.sh:46-48`.

**What.** The "heredoc / here-string" guard is a glob: `case "$CMD" in *'<<'*) exit 0 ;;`.
It matches **any** command containing the two-character sequence `<<`, including the
left-shift operator, a `printf` of `<<`, a string literal, or a comment. When it matches,
the hook exits 0 with no output, so the command is neither denied nor wrapped — it runs
**uncompressed**, defeating the hook's entire purpose for that command.

**Why (repro).** `{"tool_name":"Bash","command":"python3 -c 'print(1 << 3)'"}`:

```
### 2-bitshift(<<)  (mode=rtk)
--- exit=0
--- stdout: []
```

Empty stdout ⇒ no `updatedInput` ⇒ the raw `python3 -c 'print(1 << 3)'` executes with no
`rtk`/`lean-ctx` wrapping. Bit-shifts are common in real code one-liners; every one is a
silent token-compression miss. The same glob also fires on `git log --oneline | head <<<`
here-strings (intended) but cannot tell them apart from operators (not intended).

**Fix.** Detect a heredoc/here-string properly: a heredoc is `<<` followed by an optional
`-`, optional quote, and a *word* at a command position; a here-string is `<<<`. A regex
like `(^|[^<])<<[-~]?[A-Za-z_'"]` (heredoc) or `<<<` (here-string) is far tighter, though
still heuristic. The robust fix is the same as BUG-01: parse the command structurally
(the Go rewrite, doc 01, can shell-split and inspect tokens). Note these guards run before
branches 2/3, so this bug is independent of whether `lean-ctx`/`rtk` are installed.

### BUG-03 — ast-grep deny false-positives on any command containing a code-extension substring — High — **Observed**

`shell-guard.sh:53-60` (`CODE_EXT` + the two `grep -qE` tests).

**What.** The deny rule fires when (a) a `grep`/`rg`/`egrep`/`fgrep` token is present
**and** (b) the *whole command string* contains `\.(go|py|ts|…)` followed by a word
boundary / quote / end. Condition (b) is matched against the entire command, not against
file arguments — so a code extension appearing in the **search pattern**, in a **log/text
filename** that merely contains `.cpp.`, or **downstream of a pipe** all trigger a false
deny. The agent is blocked from a legitimate plain-text grep and told to use `sg` instead,
which makes no sense for the input.

**Why (repro).** All of these were **denied** by the scratch hook (each is a legitimate
non-code grep):

```
### P1 grep 'import foo.py' requirements.txt   -> DENY   (.py is in the PATTERN; file is .txt)
### P2 grep ERROR build.cpp.log                 -> DENY   (a LOG file named *.cpp.log)
### P3 cat setup.py | grep version             -> DENY   (.py belongs to cat; grep reads stdin)
### 16 grep foo report.go.txt                   -> DENY   (a .txt file; .go is a mid-name token)
```

I also hit this bug *for real* during this review: a `grep -n … providers/shared/merge-mcp.py`
on the native terminal was denied by the installed hook with the exact `Use ast-grep…`
message — because the **path** contains `.py`. That is the production hook blocking a
maintainer from grepping the repo's own files.

**Why it's wrong.** The check conflates "a code extension appears anywhere in the command
line" with "grep is searching a code file". The pattern string, pipe sources, and
multi-dotted log names are all collateral.

**Fix.** Only inspect tokens that are plausibly *file arguments to grep* (positional args
after the grep token that are not the pattern, plus `--include=`/`--include `globs), not the
whole command and not the first non-flag token (the pattern). Even a cheap improvement —
requiring the extension to be at the **end of a token** (`(\.ext)($|[[:space:]'"])`) and
not preceded by another `.` — would kill P2/P4. The principled fix (token-aware parsing) is
the Go rewrite (doc 01).

### BUG-04 — ast-grep deny false-negative inside command substitution / non-leading position — High — **Observed**

`shell-guard.sh:54` (the grep-detector regex `(^|[|&;]| )(grep|egrep|fgrep|rg)( |$)`).

**What.** The detector for "is there a grep here" anchors the grep token to start-of-string,
a pipe/`&`/`;`, or a literal space. It therefore **misses** `grep` immediately preceded by
`(` (command substitution / subshell), by `=` (`x=$(grep …)`), by `{`, or by a tab. A
genuine code-grep hidden in `$(grep foo a.py)` is **not** denied and slips through.

**Why (repro).** `{"tool_name":"Bash","command":"x=$(grep foo a.py); echo $x"}`:

```
### P5-subst(x=$(grep foo a.py))  (mode=rtk)
--- stdout: [{...,"permissionDecision":"allow","updatedInput":{"command":"rtk x=$(grep foo a.py); echo $x"}}]
```

The code-grep on `a.py` was **allowed** (and only the outer assignment got `rtk`-prefixed,
which is itself meaningless — see BUG-06). So the rule is simultaneously over-broad
(BUG-03) and under-broad (BUG-04): it blocks legitimate text greps and lets real code greps
through, depending only on the surrounding punctuation.

**Fix.** Same root cause as BUG-03 — the regex cannot tokenize a shell command. Shell-split
and look for a `grep`/`rg` command word in any pipeline stage (Go rewrite, doc 01). A
stop-gap is to add `(` `=` `{` to the leading-context class, but that is whack-a-mole.

### BUG-05 — `extract()` cannot survive a pretty-printed / multiline-JSON protocol change — High — **Inferred (medium confidence)**

`shell-guard.sh:23-26`.

**What.** `grep -oE` is line-oriented. The whole `extract()` design assumes the hook
payload is single-line JSON with `"key": "value"` on one physical line. Claude Code today
sends compact JSON (so this works — verified: a hand-formatted pretty JSON with the key and
value on the same line still extracts), but the contract is fragile: if a future Claude
version, or a different provider reusing this hook, emits a value that legitimately spans
lines, or formats `"command":` and its value on separate lines, `extract()` returns empty
and the hook silently no-ops (exit at line 37). There is no schema, no validation, and no
error surfaced — a protocol drift becomes a silent loss of enforcement.

**Why.** I reproduced that *same-line* pretty JSON still parses (`D3-pretty` → wrapped OK),
which confirms the fragility is specifically about line structure, not whitespace. The
failure mode is "hook does nothing, exits 0, looks healthy" — the worst kind for a security
/ policy hook.

**Fix.** Parse the whole stdin as JSON once (BUG-01's fix covers this). A real parser is
agnostic to formatting. Cross-ref doc 01.

### BUG-06 — Double-wrap guard misses env-prefixed and otherwise-decorated wrapped commands — High — **Observed**

`shell-guard.sh:40-42`.

**What.** The "already wrapped" guard is `case "$CMD" in lean-ctx\ *|rtk\ *) exit 0 ;;` —
it only recognizes `rtk`/`lean-ctx` as the **first** token. A command that is already
wrapped but carries a leading `VAR=value` assignment, a leading `env`, or leading
whitespace is not recognized and gets wrapped **again**.

**Why (repro).** `{"tool_name":"Bash","command":"FOO=1 rtk npm test"}`:

```
### 4-envprefix-rtk  (mode=rtk)
--- stdout: [{...,"updatedInput":{"command":"rtk FOO=1 rtk npm test"}}]
```

Result: `rtk FOO=1 rtk npm test` — double-wrapped, exactly the failure the hook's own
header comment ("Exactly one of these fires per command, so there is no double-wrapping",
lines 13-14) claims is impossible. Whether `rtk FOO=1 rtk …` even runs correctly depends on
how `rtk` forwards a command that begins with an assignment; at best it is wasteful, at
worst it breaks the env assignment. The converse decorated form (`x=$(grep …)` in BUG-04)
also shows the prefix logic only ever touches the head of the string.

**Fix.** Strip leading `VAR=…` assignments and `env …` before the wrapped-check, or (Go
rewrite) shell-split and inspect the first *command word*. Cross-ref doc 01.

### BUG-07 — `set -euo pipefail` + `grep` no-match: relies entirely on `|| true`, brittle under edits — High → Medium — **Inferred (medium confidence)**

`shell-guard.sh:15`, `:23-28`, `:54-55`, `:66-67`.

**What.** Under `set -o pipefail` + `set -e`, any pipeline whose last meaningful stage is a
`grep` that finds nothing exits non-zero and would abort the script. The code defends this
only with a trailing `|| true` inside `extract()` (line 27) and by using `if …; then` for
the detector greps (lines 54, 67), which exempts those from `-e`. This works **today**, but
it is load-bearing and invisible: any future edit that adds a `grep | sed`-style pipeline
without a guarding `|| true`, or that moves the `extract` body out of the function, will
make the hook abort mid-run. When a `PreToolUse` hook aborts non-zero, Claude may **block
the command** (a non-zero hook can be interpreted as a deny), turning a parsing miss into a
hard failure on an unrelated command.

**Why.** This is a latent fragility, not a current wrong output (I did not observe an abort
in the crafted cases). It is rated High→Medium because the blast radius (a hook that can
deny arbitrary commands if it ever errors) is large even though the trigger requires a code
change. Note `ci-check.sh` runs `bash -n` + `shellcheck` which would *not* catch a
pipefail/`-e` logic regression.

**Fix.** Don't rely on `-e`/`pipefail` for control flow in a parser. Either drop `set -e`
for this script (it's a small filter) or, better, replace the grep/sed parsing wholesale
(BUG-01). Ensure the hook **always** exits 0 on its own internal errors so a parse failure
degrades to "pass through" rather than "deny". Cross-ref doc 01.

### BUG-08 — Hook re-escape uses BSD/GNU-divergent `sed`; portability of the emitted JSON — High → Medium — **Inferred (medium confidence)**, cross-ref [doc 04](../plans/04-portability-review.md)

`shell-guard.sh:26`, `:57`, `:76`.

**What.** The JSON (de)escaping is done with `sed` substitutions. This machine's default
`sed` is **BSD sed** (verified: `sed --version` fails ⇒ BSD), and `/bin/bash` is **3.2**.
The current substitutions (`s/\\/\\\\/g;s/"/\\"/g`, etc.) happen to use only portable BRE
constructs, so they work on BSD sed today. But the design depends on `sed` escaping
semantics that differ between BSD and GNU for anything more complex (`\n` in replacement,
`-E` vs `-r`, in-place flags). The moment the escaping needs to handle a newline or a tab
(which it must, to fix BUG-01), the BSD/GNU split bites: GNU sed interprets `\n` in the
replacement, BSD does not. So the *correct* fix for BUG-01 is actively unsafe to implement
in `sed`.

**Why.** Marked Inferred because the *current* sed clauses are portable; the bug is that
the chosen mechanism (sed for JSON escaping) is a portability trap that blocks the real
fix. Full BSD-vs-GNU treatment is doc 04's; flagged here because it is the reason the hook
*cannot* be correctly patched in place.

**Fix.** Use `python3`/`jq` for all JSON in/out (also fixes BUG-01/05), or the Go rewrite
(doc 01), which sidesteps `sed` entirely.

### BUG-09 — `rtk`/`lean-ctx` absent ⇒ hook silently disables itself for non-grep commands — Medium — **Observed** — ✅ RESOLVED (won't-fix by design, 2026-06-30)

**✅ Resolved — won't-fix (by design).** Re-evaluated: the ast-grep deny is not a
*compression* mechanism, it is a **code-search-quality** redirect (grep → `sg`), and `ast-grep`
is a required dependency installed by `bootstrap.sh` independently of `rtk`/`lean-ctx`. So on a
machine without the compression layer the deny is still correct and actionable (it points at a
tool that *is* present), not "punitive with no benefit." Gating it on `rtk`/`lean-ctx`
availability would wrongly couple search quality to compression. The graceful pass-through for
non-grep commands when no wrapper exists is the intended degradation. No change.

`shell-guard.sh:65-71` (lean-ctx branch), `:74` (`command -v rtk … || exit 0`).

**What.** If neither `lean-ctx` nor `rtk` is on PATH, the hook reaches line 74, finds no
`rtk`, and `exit 0` with no output — the command runs unwrapped. That is the intended
graceful degradation, but combined with the ast-grep deny (which *does* still fire without
either tool), the result is asymmetric: on a machine missing `rtk`, **denies still happen**
(you're blocked from greps) but **no compression happens** (the whole point). The user gets
the punitive half of the hook without the beneficial half.

**Why (repro).** With `PATH` lacking both tools, `{"command":"python3 foo.py"}` produces
empty stdout (silent pass-through), while `grep foo x.go` still emits the deny envelope.
Observed across the `nortk` vs `rtk` harness modes.

**Fix.** Either gate the ast-grep deny on the same availability check (no `sg` guidance if
there's no compression layer either), or make the deny a *warn* that still allows. Lower
priority than the correctness bugs, but it's a real "weak machine gets the worst of both"
outcome that cuts against the north-star goal of helping weak setups.

---

## Area 2 — merge scripts (`providers/shared/merge-*.py`)

### BUG-10 — `merge-settings.py` writes `"$schema": null` when neither side has a schema — Medium — **Observed** — ✅ FIXED (already guarded; verified 2026-06-30)

`providers/shared/merge-settings.py:31`.

**What.** `result.setdefault("$schema", fragment.get("$schema"))`. If the existing
`settings.json` has no `$schema` **and** the fragment has none, `fragment.get("$schema")`
is `None`, and `setdefault` writes the key with value `None` → `"$schema": null` in the
output. `null` is not a valid `$schema` value; JSON-schema-aware tooling (and Claude's own
settings loader) may warn or choke, and it is noise in every diff.

**Why (repro).** Fragment without `$schema`, no existing file:

```
=== TEST A ===
{
  "$schema": null,
  "hooks": { "PreToolUse": [] },
  "permissions": { "allow": ["a"], "deny": [] }
}
schema key present: True | value: None
```

Note the shipped fragment `settings.hooks.json` *does* carry a `$schema`, so the live
install path avoids `null` — but the function is independently runnable and the guard is
simply wrong. (The leads doc flagged exactly this.)

**Fix.** Only set the key when a real value exists:
`if v := fragment.get("$schema"): result.setdefault("$schema", v)` (or check the existing
result first and skip entirely when both are absent).

**✅ Resolved.** `merge-settings.py` already guards with `schema = fragment.get("$schema"); if
schema is not None: result.setdefault("$schema", schema)` (verified 2026-06-30). The Go path
(`internal/settings`) emits the same output — `internal/installtest/parity_test.go` asserts
Go and Python match byte-for-byte, so neither writes a `null` schema.

### BUG-11 — ARCHITECTURE.md claims "all destructive writes back up" but the merge scripts do not — Medium (doc-vs-behavior) — **Observed** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved (doc).** `ARCHITECTURE.md` now states accurately: the **install scripts** back up
each target (timestamped) before invoking the merge tools; the merge tools themselves write
**atomically** (temp + rename) but create no backups, so an interrupted merge never corrupts
the live config (cross-ref BUG-12). The misleading "all destructive writes back up" claim is
gone.

`ARCHITECTURE.md:79-81` vs `merge-settings.py:42` / `merge-mcp.py:105`.

**What.** ARCHITECTURE.md states: *"Both call `merge-mcp.py`; Claude also calls
`merge-settings.py`. All destructive writes back up the previous file with a timestamp
suffix."* The Python writers do **no** backup — they `output.write_text(...)` directly. The
timestamped `.bak` is created by the **shell installer** (`cp "$out" "${out}.bak.$(date
+%s)"` in `providers/{claude,cursor}/install.sh`) *before* invoking python. So the claim
holds **only** when the scripts are driven by the installer; run standalone (which the docs
present as a supported entry point — "merge-mcp.py Builds provider mcp.json"), the previous
file is overwritten with **no backup**.

**Why (repro).** Running `merge-settings.py` directly:

```
=== TEST B: backup behavior of merge-settings ===
NO BACKUP created by merge-settings.py
```

**Fix.** Either (a) move the backup into the Python writers so the invariant is true
regardless of caller, or (b) soften the doc to "the install scripts back up before calling
the merge tools; the merge tools themselves overwrite in place." Option (a) is better
because it also covers BUG-12.

### BUG-12 — Non-atomic `write_text` can corrupt `mcp.json` / `settings.json` on interruption — Medium — **Inferred (high confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

`merge-mcp.py:105`, `merge-settings.py:42`.

**What.** Both scripts do `output.write_text(json.dumps(...) )`, which truncates the target
and writes in place. If the process is killed (Ctrl-C, OOM, crash) between truncate and
flush, the user's real `~/.cursor/mcp.json` or `~/.claude/settings.json` is left empty or
half-written. The install path mitigates this with a prior `.bak` copy, but (a) standalone
runs have no `.bak` (BUG-11), and (b) even with a `.bak`, the *live* file the agent reads is
now corrupt until the user notices and restores. For files the agent loads on every session,
a truncated JSON is a hard startup failure.

**Why.** Inferred (not reproduced — I did not kill a write), but it is a direct consequence
of truncate-in-place writes, which is well established. High confidence.

**Fix.** Write to a temp file in the same directory then `os.replace()` (atomic rename on
the same filesystem). The Go rewrite (doc 01) should do the same. Combine with BUG-11's
backup-in-writer.

**✅ Resolved (improvement loop, 2026-06-30).** New `providers/shared/safe_io.py`
`atomic_write_text()` writes to a same-dir temp file, `fsync`s, then `os.replace()`s over
the target (removing the temp and leaving the original intact on any failure).
`merge-settings.py` and `merge-mcp.py` now use it. The Go path was already atomic
(`internal/jsonorder.WriteFile` — temp + rename), so this brings the Python fallback to
parity. Bench: `providers/shared/selftest.py::test_failed_write_leaves_original_intact`
(monkeypatches `os.replace` to fail mid-write and asserts the live file survives byte-for-byte
with no temp leak), wired into `bin/ci-check.sh`; `internal/installtest/parity_test.go` still
matches Go vs Python byte-for-byte.

### BUG-13 — Missing `npx`/`npm` produces a "successful" install with an unrunnable MCP server — Medium — **Observed** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Both `mcpmerge` (Go) and `merge-mcp.py` (Python) now emit a loud stderr
WARNING when `npx` can't be resolved on PATH ("managed MCP servers that use it … will not
launch until you install Node/npx"), so a green install no longer silently hides a dead
server. Bench: `internal/mcpmerge/launcher_test.go::TestUnresolvedLauncherWarning` (pure
logic: bare-fallback/empty → warn; resolved/explicit-path → quiet); verified by running both
implementations under `PATH=/usr/bin`. The parity test is unaffected (it compares output
files, not stderr). **Residual (cosmetic):** an empty `NODE_PATH` is still written rather than
omitted — left alone to avoid a Go/Python output-parity change; harmless at runtime.

`merge-mcp.py:14-27`, `:34`, `:36`.

**What.** `_which("npx", "npx")` returns the **bare string `"npx"`** when `npx` is not on
PATH, and `_node_path()` returns `""` when `npm` is absent. The merge then writes a
`gitnexus` server entry with `"command": "npx"` and `"NODE_PATH": ""`. The merge prints
`Wrote … (1 server(s) total; managed: gitnexus)` and exits 0 — a green install — but the
server cannot launch at runtime because `npx` is not resolvable. The failure surfaces only
later, inside Cursor/Claude, as a dead MCP server with no breadcrumb back to the install.

**Why (repro).** PATH sandbox with only `python3`, no `npx`/`npm`:

```
=== merge-mcp with npx/npm/lean-ctx ABSENT ===
Wrote /private/tmp/mcp-missing/out.json (1 server(s) total; managed: gitnexus)
command = 'npx'
env.PATH = '/tmp/mcp-missing/sb'
env.NODE_PATH = ''
```

`doctor.sh` would later say "missing gitnexus"? No — the server IS in the file, so doctor's
`grep -q '"gitnexus"'` passes; doctor only checks `npx` availability separately and would
`fail` there, but the MCP file itself looks fine. So the two checks don't connect the dots.

**Fix.** When a required launcher resolves to its bare fallback (i.e. `shutil.which`
returned `None`), either emit a loud warning naming the missing tool, or refuse to write
that server. At minimum, don't write `"NODE_PATH": ""` — omit empty env values.

### BUG-14 — `.env` is parsed twice by two different parsers with divergent semantics — Medium — **Observed** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** `bin/install.sh` no longer `source`s `secrets/.env`. The merge tools
(`internal/mcpmerge.LoadEnv` / `merge-mcp.py:load_env`) read the file directly and are now the
**single** parser, so install-driven and standalone merges resolve `.env` identically — the
order/parser-dependent divergence is gone. Verified nothing else in the install flow consumes
those vars, and that a `.env` override (`NPX=…`) is still applied after the change. The
supported format is documented in `secrets/.env.example` (literal `KEY=value`, `~` for home,
no shell expansion).

`bin/install.sh:45-50` (bash `source`) vs `merge-mcp.py:41-49` (python `partition`).

**What.** `bin/install.sh` does `set -a; source secrets/.env; set +a`, exporting every
entry into the environment using **shell** parsing (honors `$VAR` expansion, command
substitution, `export`, line continuations, quoting rules). `merge-mcp.py` *independently*
re-reads the same `secrets/.env` with a naive `line.partition("=")` + `.strip().strip('"').strip("'")`.
The two disagree for any non-trivial value: e.g. `KEY=$HOME/x` is expanded by bash but kept
literal (`$HOME/x`) by python; `KEY="a 'b'"` is dequoted differently; a trailing inline
`# comment` is stripped by neither but a value with `#` mid-string is kept by both. Whichever
parser "wins" depends on whether the value arrives via `os.environ` (set by the bash source,
checked *first* in `load_env`) or via the python re-read (fallback). So the effective value
is order-dependent and parser-dependent.

**Why (repro).** Confirmed python side handles `=`-in-value, CRLF, and quoted `#`
correctly on its own (TESTS A/B/C passed), but it uses naive dequoting that does **not**
match bash `source` semantics — e.g. python `strip('"').strip("'")` strips *both* a leading
double and a leading single quote, which bash would never do. The divergence is the bug, not
either parser alone.

**Fix.** Single source of truth: have the installer export the env and have `merge-mcp.py`
read **only** from `os.environ` (drop the second file parse), or vice-versa. Don't parse the
same file two ways. Cross-ref doc 01 (the Go rewrite should pick one).

### BUG-15 — `substitute()` does naive global `__KEY__` replacement; value-injected placeholders double-substitute — Medium → Low — **Inferred (medium confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Both implementations now substitute in a **single regex pass** over
`__([A-Z0-9_]+)__`, resolving each placeholder exactly once from the original text (Go:
`placeholderRe.ReplaceAllStringFunc`; Python: `re.compile(...).sub`). A resolved value that
itself contains a `__TOKEN__` is no longer re-substituted, a prefix key
(`__LEAN_CTX__` vs `__LEAN_CTX_DATA_DIR__`) cannot clobber the longer one, and unknown
placeholders are left untouched. Bench: `internal/mcpmerge/substitute_test.go::TestSubstituteSinglePass`
(double-substitution, prefix-collision, unknown, nested map/slice). Output is unchanged for the
current key set, so `parity_test.go` still matches Go vs Python.

`merge-mcp.py:52-61`.

**What.** `substitute` walks the config and, for each `env` key, does
`obj.replace(f"__{key}__", value)` over **all** strings, in `dict` iteration order. Two
hazards: (1) if a resolved value itself contains a `__OTHERKEY__` token, and `OTHERKEY` is
processed in a later iteration, it gets substituted again (accidental expansion of attacker-
or typo-controlled content); (2) the replacement is unanchored, so a placeholder that is a
prefix of another (`__NODE__` vs `__NODE_PATH__`) could partially clobber depending on
order. The current key set doesn't collide, so this is latent.

**Why.** Inferred; not reproduced because the shipped keys don't currently collide. Medium→
Low.

**Fix.** Substitute in a single pass with a regex over `__([A-Z0-9_]+)__` and a lookup, so
each placeholder is resolved exactly once from the original text.

### BUG-16 — `data.get("mcpServers", data)` silently treats a malformed fragment as a server map — Low — **Observed** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Both `collectFragments` (Go) and `collect_fragments` (Python) now **require**
the `mcpServers` wrapper: a fragment lacking it (a typo'd key like `mcpServer`, or some other
JSON) is **warned about (named) and skipped**, instead of having its top-level keys injected
as junk servers. All shipped fragments use the wrapper, so output is unchanged (parity holds).
Bench: `internal/mcpmerge/collect_test.go::TestCollectFragmentsRequiresWrapper`.

`merge-mcp.py:77`.

**What.** When a fragment lacks an `mcpServers` wrapper, the whole top-level dict is treated
as the server map. This is a deliberate convenience (bare maps merge), but it also means a
**typo'd** wrapper key (`"mcpServer"`, `"mcp_servers"`) or a fragment that is actually
something else (e.g. an `{"$schema": …}`-only file) gets its top-level keys injected as
"servers". No validation, no warning.

**Why (repro).** `{"bareserver": {...}}` merged as a server named `bareserver` (TEST D).
By extension a typo produces a junk server entry silently.

**Fix.** Require the `mcpServers` key (warn and skip otherwise), or validate that each
"server" value is an object with a `command`/`url`. Low because authors control the
fragments.

---

## Area 3 — installers (`bin/*.sh`, `providers/*/install.sh`)

### BUG-17 — Every install run leaves a new timestamped `.bak`; unbounded backup proliferation — Medium — **Inferred (high confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Both installers now use a shared `backup_once()` that copies a target to
`<file>.bak` **only when no `.bak` already exists** — so the user's original config is
preserved exactly once and repeated installs (run after every pull) never accrete
`*.bak.<timestamp>` files in `$HOME`. Applied to `CLAUDE.md` + `settings.json` (Claude) and
`mcp.json` + `hooks.json` (Cursor). Bench: extracted-function harness — run twice with the
file changing between runs; the `.bak` retains the ORIGINAL and exactly one backup exists.
(The one-time skills-dir backup was already non-proliferating — it only triggers for a real
dir, after which the target is a symlink.)

`providers/claude/install.sh:42,71,91`; `providers/cursor/install.sh:36,52`; and the
`link_skills` dir-backup at `claude:26` / `cursor:26`.

**What.** On every `install.sh` run, each of `CLAUDE.md`, `.mcp.json`, `settings.json`,
`mcp.json`, `hooks.json` is `cp`-backed-up to `${out}.bak.$(date +%s)` **unconditionally**
when it exists (no "skip if identical" check). The user's global instructions say to run
`bin/install.sh --provider all` after every pull. So routine use accretes
`settings.json.bak.1719...`, `mcp.json.bak.1719...`, etc., indefinitely in `~/.claude` and
`~/.cursor`. The `.gitignore` ignores `*.bak` in the *repo*, but these live under `$HOME`
and are never cleaned. Additionally, the skills-dir backup path (`mv "$target"
"${target}.bak.$(date +%s)"`) only triggers when the target is a real directory (not a
symlink), so it won't proliferate on normal re-runs — but the file backups will.

**Why.** Inferred (high confidence) from reading the unconditional `cp` on every code path;
not run against `$HOME` per the task rules.

**Fix.** Back up only when the new content differs (`cmp -s` before `cp`), keep a single
`.bak` (overwrite, or rotate with a cap), or write to a dedicated `~/.claude/.agentic-backups/`
with pruning. Cross-ref doc 01 — a Go installer should diff-then-backup.

### BUG-18 — `bin/bootstrap.sh` ignores `--dry-run` and any second flag; can trigger a real install when a preview was intended — Low — **Observed** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** `bootstrap.sh` now parses a full arg loop (`--provider`, `--dry-run`, `--help`,
unknown→warn); under `--dry-run` it skips all dependency installs + the agentic build and runs
`install.sh --provider … --dry-run` (read-only doctor still runs). Verified: `bin/bootstrap.sh
--dry-run` makes no machine changes and previews the install.

`bin/bootstrap.sh:13`.

**What.** Bootstrap parses exactly one option: `[[ "${1:-}" == "--provider" && -n
"${2:-}" ]] && PROVIDER="$2"`. There is no `--dry-run` handling and no pass-through. So
`bin/bootstrap.sh --dry-run` is **silently ignored** and bootstrap proceeds to install deps
and run the **real** installer (no `DRY_RUN` exported). Likewise `bin/bootstrap.sh
--provider claude --dry-run` drops the `--dry-run`. A user expecting a preview gets a real
mutation of `$HOME`.

**Why (repro).** Read of line 13 confirms only `--provider` is recognized; `install.sh` is
invoked at line 86 with only `--provider "$PROVIDER"`.

**Fix.** Parse `--dry-run` in bootstrap and forward it (and `export DRY_RUN`), or document
that bootstrap has no dry-run and direct users to `bin/install.sh --dry-run`.

### BUG-19 — `--dry-run` does not preview merge *output*; the most consequential step is opaque — Low — **Inferred (high confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** The merge tools now honor `DRY_RUN=1` by **printing the would-be output** (the
full merged JSON / CLAUDE.md) to stdout and writing nothing — in both Go (`settings.Merge`,
`mcpmerge.MergeCursor`, `claudemd.Ensure`, via the new `jsonorder.Marshal`) and Python
(`merge-settings.py`, `merge-mcp.py`, `merge-claude-md.py`). The installers were rewired so
`--dry-run` actually invokes the merge in preview mode for `settings.json` (Claude) and
`mcp.json` (Cursor) instead of just logging "[dry-run] merge → …", so
`bin/install.sh --dry-run` now shows exactly what *would* change. Bench:
`internal/settings/dryrun_test.go::TestMergeDryRunDoesNotWrite` (file is not created under
DRY_RUN); behavioral checks confirmed Go + Python print the preview and write nothing.
`agentic inject --dry-run` already previewed the steps; this adds the content.

`providers/claude/install.sh:73-78,86-89`; `providers/cursor/install.sh:39-43`.

**What.** Under `DRY_RUN=1`, the MCP/settings steps only `log "[dry-run] merge-mcp -> $out"`
and `return`/skip — they never run the merge in a read-only mode, so the user sees *that* a
merge would happen but not *what* it would write (which servers, which substitutions, whether
`npx` resolved — see BUG-13). For a tool whose headline safety property is "merges, never
clobbers," the dry-run cannot actually demonstrate the merge. ARCHITECTURE.md ("always check
the `--dry-run`", line 128) overstates what dry-run shows.

**Why.** Inferred from the code paths; the merge scripts have no `--dry-run`/stdout-only
mode to call.

**Fix.** Give `merge-mcp.py`/`merge-settings.py` a `--dry-run` that prints the would-be JSON
to stdout (and resolved tool paths) without writing, and have the installer call it. Cross-
ref doc 01.

### BUG-20 — `doctor.sh` `check_link` second branch silently misclassifies a non-symlink, non-dir path; `readlink` under `set -e` — Low — **Inferred (medium confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Added the explicit `elif [[ -e "$path" ]]; then warn "exists but is not a
symlink"` branch. Verified against a scratch target: a regular file now warns "exists but is
not a symlink" instead of "missing"; the missing-path and correct-symlink branches are
unchanged.

`bin/doctor.sh:14-29`.

**What.** `check_link` handles symlink and directory, else `fail "missing"`. But if the path
exists as a **regular file** (e.g. a user accidentally created `~/.claude/skills` as a file,
or a stale copy), it falls into the `else` and reports "missing" — misleading. Also the
absolute-resolution branch (`"$(cd "$(dirname "$path")" && pwd)/$(readlink "$path")"`) runs a
`cd` in a `$( )` under `set -euo pipefail`; if `dirname`/`cd` fails the whole `[[ … ]]` is in
a condition so `-e` is suppressed, but `readlink` on a non-link returns empty and the compare
silently becomes a path that can't match — a confusing `WARN` rather than a clear diagnosis.
Minor robustness, not a wrong-result-on-happy-path.

**Fix.** Add an explicit `elif [[ -e "$path" ]]; then warn "$path exists but is not a
symlink"`.

### BUG-21 — `ci-check.sh` YAML discovery uses `find … -o …  | grep -v '.git/'` (precedence + grep filter) inconsistent with the `-not -path` filter used elsewhere — Low — **Observed**, partly [doc 05](../plans/05-test-coverage.md) — ✅ FIXED (improvement loop, 2026-06-30)

**✅ Resolved.** Now `find . \( -name '*.yaml' -o -name '*.yml' \) -not -path './.git/*'`,
matching the shell/JSON loops. Verified `bin/ci-check.sh` still finds and validates
`catalog/plugins.yaml`.

`bin/ci-check.sh:43` vs `:16`/`:32`.

**What.** The shell and JSON loops correctly prune git with `find . -name '*.sh' -not -path
'./.git/*'`. The YAML loop instead uses `find . -name '*.yaml' -o -name '*.yml' | grep -v
'.git/'`. Two issues: (1) operator precedence — without parentheses, `-o` binds such that
the implicit `-print` applies as expected here, but the pattern is inconsistent and
error-prone; (2) it relies on a post-hoc `grep -v` to exclude `.git`, so a `.yml` under
`.git/` would only be filtered by the substring match, not the find itself. It happens to be
correct today (only `catalog/plugins.yaml` exists), so this is latent.

**Why (repro).** `find . -name '*.yaml' -o -name '*.yml' | grep -v '.git/'` → returns
`./catalog/plugins.yaml` (correct now). The inconsistency is the finding.

**Fix.** Use `\( -name '*.yaml' -o -name '*.yml' \) -not -path './.git/*'` to match the other
loops. Coverage of *what ci-check validates* is doc 05's scope.

---

## Area 4 — eval harness (`evals/*.py`) — bugs in the code (coverage gaps → [doc 05](../plans/05-test-coverage.md))

### BUG-22 — `cases.load()` / `report.py` / `bench.py` crash hard on a single malformed JSON file — Medium — **Inferred (high confidence)** — ✅ FIXED (improvement loop, 2026-06-30)

`evals/lib/cases.py:23-31` (`json.loads(p.read_text(...))` with no try/except);
`evals/bench.py:127` (`[json.loads(...) for p in …]`); cross-ref `merge-*.py` which *do*
guard JSON.

**What.** `cases.load()` reads every `*.json` in a track dir with a bare `json.loads`. One
malformed case file (a trailing comma, a stray edit) raises `JSONDecodeError` with a stack
trace and aborts the **entire** lint/run — including the cases that are fine — with no
indication of *which* file is bad. The merge scripts deliberately wrap this
(`load_json` → `SystemExit(f"… invalid JSON in {path}")`), so the harness is *less* robust
than the installer for the same operation. `bench.py:127` has the same unguarded list
comprehension over spec files. `lint.py:_validate_bench` (`json.loads(p.read_text())`,
line 81) likewise.

**Why.** Inferred (high confidence) from the absence of any try/except around these reads.
`evals/lint.py` is run in CI on every PR (`ci-check.sh:77`), so a typo'd case file fails CI
with an opaque traceback instead of a "case X: invalid JSON" message.

**Fix.** Wrap each per-file `json.loads` and report `f"{path}: invalid JSON: {exc}"`
(mirroring `merge-mcp.load_json`). This is a harness-code bug; the question of *which cases
should exist* is doc 05.

**✅ Resolved (improvement loop, 2026-06-30).** `evals/lib/cases.py` gained `_read_case()`
(raises `CaseLoadError("{path}: invalid JSON: …")`, also rejecting a non-object top level)
and `load_reporting()`; `evals/lint.py` now uses the latter, so a malformed case file is
reported **by filename with a reason** and the well-formed cases still validate — instead of
an opaque traceback that aborts the whole CI lint. Bench: `evals/selftest.py::test_cases_loader_names_bad_file`
(runs in `bin/ci-check.sh`). The other two surfaces named here are already closed:
`report.py`'s result-loader has a `try/except (JSONDecodeError, IndexError)` at its
`json.loads` (`report.py:28-31`), and `bench.py` no longer exists in the tree.

### BUG-23 — `report.py` / `bench.py` assume result-record shape; a partial or older artifact KeyErrors the rollup — Low — **Inferred (medium confidence)** — ✅ RESOLVED (moot; verified 2026-06-30)

**✅ Resolved (moot).** Re-checked the current code: `bench.py` and `_render_bench` no longer
exist, and `report.py`'s `render()` now reads every field with `.get()` defaults
(`rec.get("verdict","?")`, `rec.get("wins",{})`, …) while `_eff_delta` is guarded by
`if "treatment" in r and "control" in r`. The loader wraps `json.loads` in
`try/except (JSONDecodeError, IndexError)`. So the partial/old-artifact KeyError path the
finding described is gone — no change needed.

`evals/report.py:44-49` (`r["treatment"]["tool_calls"]`), `:85-90` (`b["baseline"]`,
`b["kind"]`); `evals/bench.py:115` (`int(m[1])` only guarded by the `if m else` branch).

**What.** `report.py` reads gitignored `results/**/*.jsonl` artifacts and indexes into
fixed keys. `_eff_delta` guards with `if "treatment" in r and "control" in r` (good), but
`_render_bench` accesses `b["kind"]`, `b["baseline"]`, `b["tool_name"]` directly — a bench
artifact from an older `bench.py` (or one that hit the `result["error"] = "unknown kind"`
path, which has **no** `baseline`/`tool`) will `KeyError` and crash the whole report. Since
artifacts are regenerable and gitignored this is contained, but a stale `results/bench/*.json`
from a prior schema silently breaks `report.py`.

**Why.** Inferred; the error-path record (`bench.py:121-122`) writes `{… "error": …}` with
no `baseline`/`tool`, and `_render_bench` would index `b["kind"]` then later `b["baseline"]`
for compression/precision — a record with `kind` set but the run errored could still miss
keys. Medium confidence.

**Fix.** Use `.get(...)` with defaults in the renderers, or filter out records carrying an
`"error"` key before rendering.

---

## Cross-cutting doc-vs-behavior contradictions (summary)

| # | Doc claim | Reality | Finding |
|---|-----------|---------|---------|
| 1 ✅ | ARCHITECTURE.md:79-81 "All destructive writes back up the previous file" | Backups are done by the shell installers, not the merge scripts; merge tools now write atomically (temp+rename). **Doc corrected 2026-06-30.** | BUG-11 |
| 2 ✅ | shell-guard.sh:13-14 "Exactly one of these fires per command, so there is no double-wrapping" | Env-prefixed wrapped commands now recognized (strip leading `VAR=`). **Fixed.** | BUG-06 |
| 3 ✅ | ARCHITECTURE.md:128 "always check the `--dry-run`" | dry-run now prints the would-be merge output. **Fixed.** | BUG-19 |
| 4 ✅ | shell-guard.sh header "rtk fallback — prefix `rtk` so no native command escapes token compression" | bit-shift/multiline/decorated commands now fail open (run untouched, never mangled). **Fixed.** | BUG-01, BUG-02, BUG-06 |
| 5 ✅ | ARCHITECTURE.md:95 "Fails with the offending file path on malformed JSON" (merge) — true for merge, but the *eval* loader did not | the eval loader now names the bad file too. **Fixed.** | BUG-22 |

No instruction was found that references a flag or file that does not exist (the
`integrations/gitnexus/mcp.stdio.json` path in `doctor.sh:102` is correct; the
`mcp*.json` glob in `merge-mcp.py:75` correctly matches `mcp.stdio.json`). The
`AGENTS.md`/`CLAUDE.md` tool-precedence table is internally consistent with the installed
hooks.

---

## Prioritized remediation backlog

Effort: S ≈ <1h, M ≈ a few hours, L ≈ a day+. "Go-fixes?" = does the planned Go rewrite
([doc 01](../plans/01-go-rewrite.md)) eliminate this defect for free (a real JSON parser +
structured command handling + atomic writes), or is a shell/Python fix needed *now*?

| ID | Title | Sev | Effort | Depends-on | Go-fixes? |
|----|-------|-----|--------|------------|-----------|
| BUG-01 ✅ | Multiline/`\n`/`\t` commands silently corrupted (string-munged JSON) | Critical | M | — | **FIXED** — Go hook real JSON parse + fail-open on newline |
| BUG-02 ✅ | `*'<<'*` glob skips wrapping for bit-shift / any `<<` substring | Critical | S | — | **FIXED** — deliberate fail-open on `<<` (no mangle) |
| BUG-03 ✅ | ast-grep deny false-positives on any code-ext substring | High | M | — | **FIXED** — strips quoted substrings before the ext test |
| BUG-04 ✅ | ast-grep deny false-negative in `$(grep …)` / non-leading position | High | S | BUG-03 | **FIXED** (by design) — `$(` fails open, no in-substitution analysis |
| BUG-06 ✅ | Double-wrap guard misses env-prefixed wrapped commands | High | S | — | **FIXED** — strips leading `VAR=` before the wrapped-check |
| BUG-05 ✅ | `extract()` breaks if protocol JSON spans lines | High | S | BUG-01 | **FIXED** — whole-stdin JSON parse |
| BUG-07 ✅ | `set -e`/`pipefail` control-flow fragility; hook can abort→deny | High | S | BUG-01 | **FIXED** — Go returns 0 on any internal error |
| BUG-08 ✅ | JSON escaping via BSD/GNU-divergent `sed` blocks the real fix | High | S | BUG-01 | **FIXED** — no `sed`; real JSON encoder |
| BUG-12 ✅ | Non-atomic `write_text` can corrupt live config on interruption | Med | S | — | **FIXED** 2026-06-30 (loop) — `safe_io.atomic_write_text` (Python); Go already atomic |
| BUG-10 ✅ | `merge-settings.py` writes `"$schema": null` | Med | S | — | **FIXED** (guarded in Python; Go matches via parity test) |
| BUG-11 ✅ | Doc claims merge scripts back up; they don't (standalone) | Med | S | BUG-12 | **FIXED** 2026-06-30 (loop) — ARCHITECTURE.md corrected (atomic write, installer backs up) |
| BUG-13 ✅ | Missing `npx`/`npm` ⇒ green install, dead MCP server | Med | S | — | **FIXED** 2026-06-30 (loop) — loud npx warning (Go + Python); empty NODE_PATH residual |
| BUG-14 ✅ | `.env` parsed twice (bash `source` vs python) with divergent semantics | Med | M | — | **FIXED** 2026-06-30 (loop) — merge tools are the single `.env` parser (install no longer sources it) |
| BUG-17 ✅ | Unbounded `.bak` proliferation in `$HOME` on every run | Med | S | — | **FIXED** 2026-06-30 (loop) — `backup_once` (single `.bak`, both installers) |
| BUG-22 ✅ | Eval loaders crash hard on one malformed JSON (opaque CI failure) | Med | S | — | **FIXED** 2026-06-30 (loop) — Python fix landed (mirrors `merge.load_json`) |
| BUG-09 ✅ | No `rtk`/`lean-ctx` ⇒ denies still fire but no compression (worst of both) | Med | S | BUG-03 | **WON'T FIX** 2026-06-30 (by design — deny is search-quality, not compression) |
| BUG-15 ✅ | `substitute()` naive global replace; placeholder double-substitution | Med→Low | S | — | **FIXED** 2026-06-30 (loop) — single-pass regex (Go + Python) |
| BUG-16 ✅ | `data.get("mcpServers", data)` accepts malformed fragments silently | Low | S | — | **FIXED** 2026-06-30 (loop) — require mcpServers wrapper; warn+skip (Go + Python) |
| BUG-18 ✅ | `bootstrap.sh` ignores `--dry-run`; can trigger real install | Low | S | — | **FIXED** 2026-06-30 (loop) — arg loop + dry-run gating |
| BUG-19 ✅ | `--dry-run` never previews merge output | Low | M | BUG-13 | **FIXED** 2026-06-30 (loop) — merge tools print would-be JSON under DRY_RUN (Go + Python); installers wired |
| BUG-20 ✅ | `doctor.sh check_link` misclassifies a regular-file target | Low | S | — | **FIXED** 2026-06-30 (loop) — added regular-file `elif` branch |
| BUG-21 ✅ | `ci-check.sh` YAML find uses inconsistent git-prune | Low | S | — | **FIXED** 2026-06-30 (loop) — `\( … \) -not -path` |
| BUG-23 ✅ | `report.py` KeyErrors on partial/old result artifacts | Low | S | — | **RESOLVED** (moot — `_render_bench`/bench.py gone; report.py uses `.get()`) |

### Recommended sequencing

1. **Hook correctness cluster (BUG-01, 02, 05, 06, 03, 04, 07, 08) — ✅ DONE (Go hook port +
   shell hardening, 2026-06-30; see the banner at the top of Area 1).** These are the
   Critical/High mass and they share a single root cause: parsing a structured protocol and
   a shell command with `grep`/`sed`/glob. The highest-leverage move is the Go rewrite
   ([doc 01](../plans/01-go-rewrite.md)), which deletes the entire class. If the rewrite is not
   imminent, the cheapest interim shell mitigations are: route all JSON in/out through
   `python3 -c` (kills BUG-01/05/08), tighten the `<<` test (BUG-02), and tighten the grep
   token/file detection (BUG-03/04/06). Ensure the hook **always exits 0 on internal error**
   so a parse miss degrades to pass-through, never to a spurious deny (BUG-07).
2. **Merge-script robustness now (BUG-10, 11, 12, 13).** Small, independent, and they
   protect the user's live config; do them in Python immediately rather than waiting on Go.
3. **Harness hardening (BUG-22, 23).** Cheap; they make CI failures legible. Coordinate the
   *coverage* story with [doc 05](../plans/05-test-coverage.md).
4. **Installer ergonomics (BUG-17, 18, 19, 20, 21).** Low severity; batch them.

### Verification notes (honesty)

- **Observed / reproduced** in a `/tmp` scratch copy: BUG-01, 02, 03, 04, 06, 09, 10, 11,
  13, 14, 16, 18, 21. Observed outputs are quoted inline.
- **Inferred** from source reading (not executed against `$HOME`/real installer, per task
  constraints): BUG-05, 07, 08, 12, 15, 17, 19, 20, 22, 23 — each carries a confidence
  level in its body.
- The reproductions used crafted hook JSON and crafted `.env`/fragment files; the real
  installer was never run, `$HOME` was never touched, and no repo file other than this one
  was modified. The scratch copy of `shell-guard.sh` was byte-identical to the committed
  hook at the time of testing.
- One bug (BUG-03) was independently corroborated by the **production** hook blocking a
  routine `grep … merge-mcp.py` during this very review.

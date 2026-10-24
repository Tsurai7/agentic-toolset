# 02 — install auto-link, doctor PATH check, docs, CHANGELOG

**Rationale:** [DESIGN.md](DESIGN.md) Q2/Q4 — `agentic link` exists but nothing runs
it, so `agentic-cfg` never lands on PATH; doctor has no notion of the entry point;
the update flow is undocumented.

## Change specification

### 1. `bin/install.sh`

Immediately after the provider dispatch `case` block (after line ~84, before the
memory-seeds section), add a link step in the file's existing style:

- If `DRY_RUN=1`: `echo "[dry-run] would run: bin/agentic link"`.
- Else if `"${AGENTIC_ROOT}/bin/agentic"` is executable: run
  `"${AGENTIC_ROOT}/bin/agentic" link` (it prints its own `linked/skipped` lines and
  a PATH hint when `~/.local/bin` is not on PATH — do not duplicate that output).
- Else: `echo "WARN: bin/agentic missing — skipping PATH link (go build failed?)" >&2`
  (mirrors the existing go-build WARN wording).

shellcheck must stay clean (ci-check runs it over bin/).

### 2. `bin/doctor.sh`

In the **Binaries** section (not deep), add a check for the PATH entry point:

- `command -v agentic-cfg` → found: resolve with `readlink` (it is a symlink created
  by `linkInto`); if it resolves to `"${AGENTIC_ROOT}/bin/agentic"` → `ok "agentic-cfg
  on PATH -> $AGENTIC_ROOT/bin/agentic"`; resolves elsewhere → `warn` naming both
  paths; not a symlink → `warn`.
- Not found → `warn "agentic-cfg not on PATH — run bin/install.sh (or bin/agentic
  link)"`. `warn`, not `fail`: an un-linked entry point degrades convenience, not
  correctness.
- Reuse the existing `ok/warn` helpers and quoting style; handle a relative readlink
  target the way `check_link` does (or use the absolute-target knowledge: `linkInto`
  always writes absolute targets — state that assumption in a comment).

### 3. `SETUP.md`

Add an "Updating" section (place it after the install steps, before per-tool notes;
match heading level and tone):

- One-time: `bin/install.sh --provider all` now also links `agentic` + `agentic-cfg`
  into `~/.local/bin`.
- From then on, from anywhere: `agentic-cfg update` — fast-forward pull, rebuild,
  re-apply to Cursor + Claude; `agentic-cfg version` shows what you are on.
- Note: running Claude/Cursor sessions keep the prefix they started with — restart
  or open a new session to pick up the update.
- Note: works against the private origin with your existing git credentials — no
  public repo required.

### 4. `CHANGELOG.md`

New `[0.15.0]` entry above `[0.14.1]`, matching the existing entry format: self-update
(`agentic-cfg update`) and `version` subcommands; install.sh auto-links the CLI onto
PATH; doctor checks the PATH entry point; versioning via git tags starting `v0.15.0`.

## Acceptance criteria (hard)

1. `bash bin/ci-check.sh` passes (shellcheck included).
2. `bash bin/install.sh --provider all` on this machine ends with the link step
   output; afterwards `command -v agentic-cfg` prints a path under `$HOME/.local/bin`
   and `readlink $(command -v agentic-cfg)` prints
   `/Users/tsurai/Documents/GitHub/agentic-cfg/bin/agentic`. (Run this only AFTER
   plan 01's binary changes are in the tree — coordinate: if `./bin/agentic help`
   does not list `update`, rebuild first via the install itself, which always
   rebuilds.)
3. `bash bin/install.sh --dry-run --provider all` prints the `[dry-run] would run:
   bin/agentic link` line and creates/changes nothing.
4. `bash bin/doctor.sh` includes the new `agentic-cfg on PATH` OK line (after AC 2
   has run).
5. `bash bin/prefix-budget.sh` → 8754 bytes unchanged; `python3 evals/lint.py` →
   22 cases, 10 skills covered (unchanged).
6. Diff touches only: `bin/install.sh`, `bin/doctor.sh`, `SETUP.md`, `CHANGELOG.md`.

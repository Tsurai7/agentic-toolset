# Self-update: `agentic-cfg update` + versioning

Office-hours vet (pure infra routing: premise + Q2 + Q4 + Q5), 2026-07-02.
Wave index: [00-INDEX.md](00-INDEX.md).

## The ask

> "Add versioning to agentic-cfg so I can update it with `agentic-cfg update` and the
> latest version gets applied to my Claude, without asking the assistant to do it. If
> the repo must become public for this — do it."

## Premise challenge

The ask is really two small things on top of machinery that already exists:
a **one-command update** (pull + rebuild + re-apply) and **version visibility**
(what am I on, what did the update change). It is *not* an auto-updater, a release
pipeline, or a distribution problem.

**Public repo: not required.** `update` operates on the user's existing clone with
the user's own git credentials — private origin works exactly as well as public.
Public would only matter for a credential-less bootstrap (`curl | sh` onto a fresh
machine), which is not part of the ask. Recorded as out of scope; the conditional
authorization ("if needed") is therefore not exercised.

## Q2 — Status quo

- Manual flow documented today: `git pull` + `bin/install.sh --provider all`
  (README/SETUP), or `make install` from the repo root.
- `bin/install.sh` **already rebuilds** `bin/agentic` on every run (fresh-machine and
  stale-binary safety, lines 51–63) — so "apply latest" is already one script; what
  is missing is running it from anywhere plus the git pull in front.
- `agentic link` (cmd/agentic/main.go) **already symlinks `agentic` and
  `agentic-cfg`** into `~/.local/bin` idempotently, and `defaultRoot()` already
  resolves the repo root from the binary through symlinks. Nothing runs `link`
  automatically, so the entry point never lands on PATH.
- No git tags exist; no version readout anywhere.

Genuinely missing: `update` + `version` subcommands, auto-`link` during install, a
doctor check for the PATH entry point, docs, and an initial tag.

## Q4 — Narrowest wedge

1. **Plan 01 (Go):** `internal/selfupdate` — `update` (validate root → `git pull
   --ff-only` → `bash bin/install.sh --provider all` → report old → new) and
   `version` (`git describe --tags --always --dirty` + commit date + root), wired
   into the existing `run()` switch and `usage()`. Unit tests on temp-git fixtures.
2. **Plan 02 (shell/docs):** `install.sh` runs `bin/agentic link` after the provider
   dispatch (idempotent, prints its own PATH note); `doctor.sh` checks the
   `agentic-cfg` PATH entry resolves into this checkout; SETUP.md "Updating"
   section; CHANGELOG `[0.15.0]`.
3. **Post-merge (orchestrator, not in the diff):** tag `v0.15.0` on the merge commit
   and push the tag — `git describe` then yields meaningful versions; the CHANGELOG
   heading and the tag stay aligned by convention from here on.

Explicitly out of scope: auto-update (cron/daemon/session-start hooks), fresh-machine
bootstrap without credentials, making the repo public, Windows, README edits (the
file carries foreign uncommitted changes from a concurrent session — a quickstart
line is deferred until the tree clears).

## Q5 — Risk & verification

Blast radius: new subcommands (no existing behavior changes), one install.sh step,
one doctor check. `update` mutates only its own checkout (ff-only pull; git itself
refuses when local diverges — the error passes through verbatim) and re-runs the
same installer the user already runs. The rebuild replaces `bin/agentic` while the
`update` process runs from it — safe on unix (new inode, running image unaffected;
the freshly-built binary is used by the very install.sh step that follows the pull).

Gates: standard four (go test / ci-check / evals lint / prefix-budget — no always-on
files touched, 8754 bytes must hold) + live E2E on this machine: `bin/install.sh
--provider all` auto-links, `command -v agentic-cfg`, `agentic-cfg version`,
`agentic-cfg update` end-to-end (idempotent when already up to date), `doctor.sh`
shows the new PATH-link check OK.

## Q6 — Cost of keeping

Zero always-on tokens (no prefix change, no MCP, no hooks). Maintenance: the
CHANGELOG-heading ↔ tag convention, and remembering that `update` applies to *new*
sessions (running Claude/Cursor sessions keep the prefix they started with — the
docs say this explicitly).

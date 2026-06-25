# Memory policy

A single coherent practice for agent memory: clear boundaries between stores, no
duplication or staleness, and cheap recall. This exists because memory was
fragmented across two independent systems with no policy tying them together.

## The stores and the boundary

| Store | What it is | Role |
|-------|-----------|------|
| Native file memory (`~/.claude/projects/<proj>/memory/`) | `MEMORY.md` index + `*.md` fact files with frontmatter | **Authoritative** for user/feedback/project/reference facts. Index loads at session start; bodies read on demand. |
| lean-ctx store (`~/.lean-ctx/`) | lean-ctx's own context engine (context IR, archives, semantic index) | **Operational only.** Managed by lean-ctx. We do not write user facts here or mirror facts into it. Off-limits. |
| Global `CLAUDE.md` (generated) | Static instructions from `core/` | **Config, not memory.** Durable behavior rules, not episodic facts. |

The core decision: native file memory is the one place user-facing facts live.
lean-ctx is left to manage its own store. We did **not** add mem0/byterover/a
vector DB — that is operational weight and extra tool-schema tax the current
fact volume does not justify.

## Where each fact type lives

| `metadata.type` | Scope | Location |
|-----------------|-------|----------|
| `user` | cross-project (identity, expertise, preferences) | `core/memory/seeds/` → distributed by `sync.py` |
| `feedback` | cross-project (how to work; corrections) | `core/memory/seeds/` → distributed by `sync.py` |
| `project` | one project | that project's `memory/` only |
| `reference` | one project (URLs, dashboards, tickets) | that project's `memory/` only |

Cross-project facts are version-controlled as **seeds** so they survive
reinstalls and reach every project you actually work in, instead of being
trapped in one project's silo.

## Recall model

Recall stays cheap: only `MEMORY.md` (a one-line-per-fact index) is loaded at
session start. Fact bodies are read on demand when a hook matches. Keep the
index terse; put detail in the fact body.

## Mechanisms

- **`lint.py`** — hygiene check (zero tokens). Validates frontmatter, that
  `name` matches the filename, and that `MEMORY.md` and the fact files agree
  (no orphans, no dangling links). `python3 core/memory/lint.py` lints the
  tracked seeds; `--live` lints the live per-project stores; `--dir <path>`
  lints one directory. Non-zero exit on errors.
- **`sync.py`** — distributes `seeds/*.md` into the memory of **active**
  projects (those with a transcript modified within `--active-days`, default
  30). Merge-by-name: a seed is written only if no fact with that slug already
  exists there, so local edits are never clobbered. Dry-run by default; `--apply`
  to write. Files starting with `_` (templates) are never distributed.

## Consolidation ritual

Run the `consolidate-memory` skill periodically (manually, on demand) to merge
duplicates, fix stale facts, and prune the index. This is a deliberate ritual,
not a background job — it mirrors the manual-only choice for the telemetry gate.
After consolidation, run `lint.py --live` to confirm indexes are still consistent.

## Integration spec (not applied here)

These hooks belong in files owned elsewhere; apply them when coordinating, do not
let this branch edit them directly:

- **`bin/ci-check.sh`** — add a zero-token static check on the tracked seeds:
  `python3 core/memory/lint.py` (seeds only; the `--live` path needs local
  transcripts and must not run in GitHub CI).
- **`bin/install.sh`** — after rendering config, run
  `python3 core/memory/sync.py --apply` so cross-project seeds reach the active
  projects on every install. It is idempotent (merge-by-name) and safe to re-run.

# Office-hours design session — `agentic inject` / `agentic eject`

> Method: gstack `office-hours` forcing questions, run on a pure-infra change (Q2 status quo,
> Q4 narrowest wedge), plus the "don't break the user's config" north star.

## The ask

> "I should be able to add it to the Claude config via `agentic-cfg inject` and remove it via
> `agentic-cfg eject`; that functionality should be fully covered by tests."

## Q2 — Status quo (the real competitor)

Installation already exists: `bin/install.sh` → `providers/claude/install.sh` does four things
— symlink skills, generate the `CLAUDE.md` `@import` block, register MCP servers, merge
hooks + permissions into `settings.json` — each preserving user content. **What's missing:**
(1) there is **no uninstall** at all, so a user can't cleanly back out; and (2) install is
shell, not a single testable command. Eject is the genuinely new capability; inject is a
testable, self-contained Go front door to what install already does.

## Q4 — Narrowest wedge

One Go command pair operating on an explicit `--root` (repo) and `--home` (target `~`), so the
whole thing is unit-testable against a temp dir:

- **inject** = the four install steps, idempotent.
- **eject** = the precise inverse, removing *only* what inject added.

Reversibility is designed in, per artifact:

| Artifact | inject | eject | reversible because |
|---|---|---|---|
| `CLAUDE.md` block | add managed `@import` | strip it | marker-delimited (`BEGIN/END`); user text untouched |
| generated md | write | delete | repo-owned file, not user content |
| skills | symlink → `core/skills` | remove iff it's our symlink; restore backup | a real user dir is backed up, never clobbered |
| `settings.json` | merge managed hooks + allow | drop managed hook groups + the fragment's allow entries | managed groups identified by command signature |
| MCP servers | `claude` CLI register | `claude` CLI remove (managed names) | best-effort; the only non-FS step |

## Honesty / scope boundaries

- **MCP is the one non-testable step** — it goes through the global `claude` CLI (not
  `--home`-scoped), so it's best-effort and gated by `--skip-mcp`. The *name resolution* it
  uses is exported and unit-tested; the CLI calls themselves are not.
- **Permissions caveat:** an `allow` entry the user added independently that *also* appears in
  our fragment is removed on eject. Documented, accepted for v1.
- **Non-breaking is the binding invariant:** every test asserts user content (CLAUDE.md prose,
  settings `env`/`deny`/user hooks/user allow, a real skills dir) survives both operations.

## Success criteria (all met)

1. `agentic inject` / `agentic eject` exist; round-trip leaves the config as it was.
2. Fully covered: `internal/lifecycle/lifecycle_test.go` (round-trip, idempotency, real-dir
   backup/restore, dry-run, generated-md) + unit tests for `claudemd.StripBlock/Remove` and
   `settings.Unmerge`.
3. `bin/ci-check.sh` green; real CLI run validated against a scratch `--home`.

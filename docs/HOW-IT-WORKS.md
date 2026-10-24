# How agentic-cfg works

The complete tour: what this toolset does, the machinery behind it, and why it is
shaped the way it is. Written 2026-07-02; byte counts and check counts drift — the
commands shown are how you get the current numbers.

Companion docs: [`README.md`](../README.md) (quick start),
[`ARCHITECTURE.md`](../ARCHITECTURE.md) (diagrams + directory map),
[`SETUP.md`](../SETUP.md), [`TESTING.md`](../TESTING.md), and the research set under
[`docs/research/`](README.md).

## What it is

agentic-cfg is a **single source of truth for personal agent configuration** — the
instructions, skills, agent roles, hooks, and integrations that shape how coding
agents (Claude Code today, Cursor in parallel, others later) behave on this machine.
Its stated goal: **cut token spend and context pollution radically while raising the
quality of what the models produce.**

The core idea is `author once → render everywhere`:

```
core/                      providers/claude/install.sh        ~/.claude/
  instructions/  ─┐                                            CLAUDE.md (@import block)
  principles/     ├─ concatenated ──────────────────────────▶  agentic-cfg.generated.md
  skills/        ─┼─ symlinked ─────────────────────────────▶  skills/
  agents/        ─┼─ symlinked ─────────────────────────────▶  agents/
  rules/         ─┘        providers/cursor/install.sh  ────▶  ~/.cursor/... (rules, hooks)
  + hooks (providers/claude/hooks/*.sh) merged into ────────▶  ~/.claude/settings.json
  + MCP servers (integrations/*) registered via the CLI ────▶  ~/.claude.json
```

Nothing is hand-edited on the rendered side; you edit `core/` and re-run
`bin/install.sh --provider all`. The `agentic` Go CLI provides the same lifecycle as
a reversible pair — `agentic inject` / `agentic eject` — plus `agentic status` to see
which pieces are present.

## The mental model: three enforcement layers plus a measurement loop

Everything in the repo lands in one of three layers, ordered by how strongly it
binds the model — and every layer is paid for in a different currency:

| Layer | Mechanism | Cost | Binding strength |
|---|---|---|---|
| **Always-on prefix** | `~/.claude/agentic-cfg.generated.md`, imported into every session | tokens in *every* request (cached, but still attention) | weakest — prose the model may ignore |
| **On-demand skills** | `~/.claude/skills/<name>/SKILL.md`, fire when the description matches | tokens only when a skill fires | medium — instructions loaded at the right moment |
| **Hooks** | PreToolUse/PostToolUse shell+Go programs in `~/.claude/settings.json` | ~0 tokens (runs outside the model) | strongest — mechanical, cannot be ignored |

The repo's measured history (see
[`docs/research/current-design-critique.md`](research/current-design-critique.md))
taught one hard lesson: **prose nudges are the weakest lever and weak models don't
follow them** — so anything that must *always* happen belongs in a hook, anything
situational belongs in a skill, and the always-on prefix is kept as small as
possible. A CI gate (`bin/prefix-budget.sh`) enforces that: the always-on source may
not exceed its byte budget (9,054 bytes as of 2026-07). Run it to see the current
size.

The fourth piece is the **measurement loop** (`evals/`): no rule or skill ships
without an eval case, and performance claims ship only with a benchmark cell behind
them. The repo once shipped a plausible prompt-level fix (W1), then built the
instrument, measured, and retracted it — the whole apparatus exists to catch that
before it happens again.

## Component walk-through

### Always-on layer (`core/instructions/`, `core/principles/`)

`core/instructions/AGENTS.md` is the portable instruction file (usable as a project
`AGENTS.md` elsewhere). It carries the global defaults — tool-choice precedence,
shell compression rule, git-commit policy, done-means-verified — and the
right-size-the-tooling triage gate that decides when heavy tooling is worth it.
`core/principles/` holds the two always-on principles (`honesty.md`,
`karpathy-guidelines.md`); `core/instructions/user-rules/` holds always-on rules
(coding principles, communication) rendered into the same prefix.
`providers/claude/CLAUDE.md.stub` heads the generated file; the user's own
`~/.claude/CLAUDE.md` only ever gains a small managed `@import` block, so
hand-written content survives every install.

Everything here is deliberately terse: each byte is multiplied by every session.
The June–July 2026 diet cut the source from 11,232 to ~8.8 KB and the budget gate
ratcheted down behind it so it cannot silently regrow.

### Skills (`core/skills/`)

The on-demand skill set grows week to week — `ls core/skills/` is the live list
(a dozen at the time of writing): `answer-shapes`, `ast-grep`, `create-pr`,
`git-safety`, `codebase-memory`, `model-orchestration`, `no-mistakes`,
`office-hours` (the vet-an-idea forcing questions, reconstructed in-repo after
the gstack upstream went private), `prompt-caching-playbook`,
`systematic-debugging`, `verification-before-completion`. Each is a directory
with a `SKILL.md` whose YAML `description` doubles as its trigger — the provider
injects descriptions, and the body loads only when the skill fires (pay-per-use).
The whole directory is symlinked to `~/.claude/skills`, so edits are live
immediately.

Two conventions keep skills honest:

- **Narrow triggers.** A description that over-matches taxes unrelated sessions;
  trigger phrasing is part of review.
- **Eval coverage.** `evals/lint.py` fails CI if a skill has no conformance case —
  a skill that can't demonstrate "it fires when it should and helps when it fires"
  doesn't ship. (`core/skills/no-mistakes/` is gitignored — it documents a
  local-only gate binary — and is exempt from the tracked-file checks.)

### Agent roles (`core/agents/`) — the orchestration wedge

Four subagent role definitions, symlinked to `~/.claude/agents`, each with a pinned
model tier and a tool allowlist enforced by the harness:

| Role | Model | Purpose |
|---|---|---|
| `implementer` | sonnet | executes a written plan with hard acceptance criteria |
| `doc-writer` | haiku | mechanical doc edits from an explicit item list, with anti-overstatement rules |
| `verifier` | sonnet | runs gates and checks AC against the diff; read-only by tool allowlist |
| `researcher` | sonnet | web research where every claim carries a fetched source URL |

The bodies carry the boilerplate that previously had to be re-typed into every
delegation prompt: scope guard, "AC is the definition of done", the
`DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT` status protocol, honesty
rules, and environment notes (the shell compression hook, retry-once on blocked
reads, never commit unless asked). Descriptions are capped at 25 words — they load
into the orchestrating session's context, so they are the one part of this feature
that is always-on; the cap is enforced by a `bin/ci-check.sh` section.

The intended workflow (the **delegation protocol**, detailed in the
[`model-orchestration`](../core/skills/model-orchestration/SKILL.md) skill): a
strong model plans and writes plan files with hard acceptance criteria and disjoint
file scopes; `implementer`/`doc-writer` agents execute them (in parallel when
scopes are disjoint); the orchestrator or a `verifier` runs the repo gates per
wave and diff-checks cheap-tier claims before accepting them; agents that die
mid-run are relaunched with a done/remaining map derived from the working tree.
Design provenance and the honest cost/benefit arithmetic live in
[`plans/orchestration-agents/DESIGN.md`](../plans/orchestration-agents/DESIGN.md);
any token-savings figure remains a hypothesis until the recorded side-by-side
measurement runs.

### Hooks (`providers/claude/hooks/`, rendered into `~/.claude/settings.json`)

The mechanical layer — two hook groups with **anchored** matchers (an unanchored
matcher is a regex and can over-match tool names); the first fires *before* the
tool runs (PreToolUse), the second fires *after* an edit lands (PostToolUse):

- `^Bash$` → **shell-guard**: complex commands — heredocs, multi-line, `cd`
  chains, command substitution — **fail open first**: a command whose grep
  target can't be attributed reliably runs untouched. Then bare regex-grep over
  source files is **denied** with a
  pointer at `ast-grep` — a best-effort nudge with documented evasions (see
  `issues/`), not a security boundary. Implemented twice on purpose: a fast Go
  binary (`agentic hook`, built by the installer; it fails open even on a panic)
  with a pure-shell fallback (`SHELL_GUARD_NO_GO=1` selects it); parity between
  the two is test-covered.
- `^(Edit|Write|MultiEdit)$` (PostToolUse) → **edit-lint**: syntax-checks edited
  py/go/js/sh files right after the write lands (`python3 -c 'import ast…'`,
  `gofmt`, `node --check`, `bash -n`), so a broken edit is caught before anything
  is built on top of it, not at the next test run.

Settings merging is **idempotent**: the merge tool recognizes repo-managed hook
commands by basename (so absolute-path variants don't duplicate) and manages its
allow-list entries as a set, so entries the fragment no longer ships are removed. The
same logic exists byte-identically in Go (`internal/settings`) and Python
(`providers/shared/merge-settings.py`) — the installer prefers the Go binary and
falls back to Python.

### The `agentic` Go CLI (`cmd/agentic`, `internal/`)

Built by the installer when Go is present (`go build -o bin/agentic ./cmd/agentic`);
`bin/agentic-cfg` is a wrapper that prefers the built binary and falls back to
`go run`, and `agentic link` symlinks both names onto your PATH. Subcommands:
`inject` / `eject` / `status` (the reversible lifecycle over skills, agents,
CLAUDE.md block, generated file, settings, MCP), `update` (self-update:
`git pull --ff-only` on the checkout, then reinstall every provider) and `version`,
`link`, the merge tools the installer shells out to (`merge-settings`, `merge-mcp`,
`merge-claude-md`), `hook` (the Go shell-guard), and token-economy reporting
(`gain`, `cache`). Everything
filesystem-touching is parametrized by root+home and unit-tested against temp dirs
(`internal/lifecycle`, `internal/installtest` parity suites); writes to live config
are atomic (temp file + rename) so an interrupted install can't leave a truncated
prefix.

### Integrations and the plugin catalog (`integrations/`, `catalog/`)

External runtime tools live in **their own repos** and are only *wired up* here:

- [`integrations/no-mistakes`](../integrations/no-mistakes) — the local ship gate
  (see "Shipping a change" below).

`catalog/plugins.yaml` extends the same philosophy to marketplace plugins: they are
**cataloged, never vendored** — the file records what to enable and what env each
plugin needs, and CI checks only its YAML validity.

### Evals (`evals/`) — the measurement loop

Two tracks plus a benchmark:

- **Conformance** (`evals/conformance/cases/*.json`): does the rendered config make
  the agent *do the right thing* on a prompt shaped for a rule? Each case has
  `expect` / `expect_not` lists; an LLM judge grades transcripts and **fails
  closed** (a judge error is an error, never a silent pass).
- **Value** (`evals/value/cases/*.json`): pairwise A/B — does firing the rule
  actually *help* compared to not having it?
- **Overhead** (`evals/overhead.py`): the cost side — ON vs OFF arms, where OFF is
  a genuinely bare `CLAUDE_CONFIG_DIR` (no hooks, no MCP, empty CLAUDE.md), medians
  over reps, errored reps excluded from aggregates, verdict thresholds in
  `evals/lib/judge.py`.
- **SWE benchmark** (`evals/swe_bench.py`): a difficulty ladder of real edit tasks
  graded functionally (`go test`), used to decide roadmap items per
  [`docs/research/swe-benchmark-design.md`](research/swe-benchmark-design.md).

[`evals/PLAYBOOK.md`](../evals/PLAYBOOK.md) documents the loop a new rule must
survive: ship a conformance case (it fires) and a value case (firing helps), then
watch the overhead cell. [`evals/BENCHMARKS.md`](../evals/BENCHMARKS.md) is the
durable record of measured runs — `report.py` regenerates its table from result
files while preserving the hand-written provenance notes.

### CI and local gates (`bin/`)

`bin/ci-check.sh` is the everything-gate, run locally and by GitHub Actions on
every push/PR: shell syntax + shellcheck, JSON/YAML validity, skill frontmatter,
skill reference links, **agent-definition checks** (frontmatter, name=filename,
description word cap, model allowlist), markdown link resolution
(`bin/check-links.py`), edit-lint and shell-guard self-tests (with stubbed
binaries so they are environment-independent), eval lint + harness selftest, the
SWE-benchmark selftest, memory-seed lint, the prefix budget, and the full Go suite
(fmt, vet, test, build). `bin/doctor.sh` diagnoses a live machine;
`bin/prefix-budget.sh` guards the always-on byte budget. One known blind spot:
`bin/check-links.py` scans **tracked** markdown only (`git ls-files`), so a
brand-new doc's links are validated by CI only once the file is staged — link-check
new docs by hand (or stage them) before trusting a green run.

### Cross-project memory seeds (`core/memory/`)

A small mechanism that distributes durable user/feedback facts ("seeds") into
Claude Code's per-project memory directories at install time (`sync.py`, gated by
`POLICY.md`, linted in CI). As of 2026-07 the seed set is template-only.

## Where the tokens actually go (and which lever attacks what)

| Cost | Lever in this repo |
|---|---|
| Always-on prefix in every request | byte budget + diet (prefix-budget.sh); everything situational demoted to skills |
| Orientation churn (agent re-reading files, verbose tool output) | codebase-memory-mcp for structural questions instead of grep-and-read |
| Strong-model tokens on mechanical work | agent roles with cheap-tier pins + the delegation protocol |
| Repeated boilerplate in delegation prompts | role bodies carry it once (pay-per-spawn) |
| Cache misses | stable prefix ordering + `prompt-caching-playbook`; `agentic gain`/`cache` report the observed economics |
| Code that never needed to exist | `ponytail` plugin (cataloged) — a do-less decision ladder |

The honesty rule that governs all of this: **a number is either measured (and
cited) or it is labeled a hypothesis.** The research set under `docs/research/`
holds both kinds, clearly marked, including null results (the reasoning-effort dial
on tool-bound tasks) and retractions (W1).

## Daily flows

- **Fresh machine**: clone, `bash bin/install.sh --provider all`, restart the
  agent app. `bin/doctor.sh` to verify.
- **After a pull**: re-run the installer (idempotent; also rebuilds `bin/agentic`) —
  or do both in one command: `agentic-cfg update` (ff-only pull + reinstall of every
  provider).
- **Add a skill**: `core/skills/<name>/SKILL.md` with a narrow description + a
  conformance case (+ a value case per the PLAYBOOK); `evals/lint.py` enforces the
  pairing; it renders via the existing symlink.
- **Add an agent role**: a file in `core/agents/` within the ci-check constraints;
  it ships through the same symlink and is covered by `agentic status`.
- **Change always-on text**: edit, then `bin/prefix-budget.sh` must still pass —
  trim something else or don't ship.
- **Measure**: `python3 evals/run.py --track all`, `python3 evals/overhead.py`,
  `python3 evals/swe_bench.py` (real tokens; see PLAYBOOK for when).
- **Ship**: commit on a feature branch and run the `no-mistakes` gate (the
  `/no-mistakes` skill drives it): intent → rebase → automated review with
  finding gates → tests → docs → lint → push → PR → CI monitor. The 2026-07-02
  wave shipped through it and its review caught four real aggregate-pollution
  bugs the human-driven reviews had missed.

## Why this is one repo (and where the real seam is)

The natural boundary already exists and is already used: **runtime tools live in
their own repos** (codebase-memory-mcp, no-mistakes are all external projects —
this repo only wires them), and **plugins are cataloged, not vendored**. What
remains inside is exactly the set of things that must move in lockstep:

- A principle and the hook that mechanizes it (honesty ↔ shell-guard/edit-lint)
  version together; splitting them invites silent drift.
- A skill and its eval cases are one unit by CI construction — `evals/lint.py`
  fails a skill with no eval, which is only enforceable when both live in one tree.
- The prefix budget spans `instructions/` + `principles/` + `user-rules/` — a
  byte added in one repo would have to be paid for by a trim in another.
- Improvement waves are atomic here: one PR can move a rule, its hook, its eval,
  the installer, and the docs, and one CI run vouches for all of it. Split repos
  turn that into coordinated multi-repo releases with version pinning — real cost,
  zero benefit at one-maintainer scale.

A split earns its keep only when a consumer needs a piece *without* the rest:
if `core/instructions + principles` ever become a team-shared baseline, publish
them as a rendered artifact (a template repo or a marketplace plugin built from
this source) rather than moving the source out; if the eval harness ever becomes a
general-purpose product with outside users, it is the one candidate with a clean
enough interface to extract. Neither trigger has fired as of 2026-07.

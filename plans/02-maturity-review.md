# Maturity & SOTA-Conformance Review

A principal-engineer assessment of whether `agentic-cfg` is being built **the right way, at the right altitude** — judged against the repo's own north-star goals (drastic token / context reduction, weak-agent uplift, a toolset that composes, provider-genericity, justified subagent cost) and against current best practice for AI / agentic development.

---

## Scope & ownership

This document owns **strategy, maturity, and SOTA conformance**. It rates each maturity dimension with evidence and benchmarks the repo against current best practice. It is one of five parallel reviews and defers, by design, to its siblings:

| Concern | Owner |
|---|---|
| The Go-rewrite design | `plans/01-go-rewrite.md` |
| Concrete code bugs (specific defects in scripts / Python) | `plans/03-gaps-and-bugs.md` |
| Cross-provider / cross-machine portability mechanics | `plans/04-portability-review.md` |
| Exhaustive test/eval gap enumeration | `plans/05-test-coverage.md` |

Where I touch those areas (e.g. the conformance-case skew, the gitignore vs tracked-results question) I state the maturity implication and point to the sibling for the exhaustive list or the fix mechanics. I do **not** duplicate their backlogs.

**Method.** Read-only exploration of the repo (every `core/`, `evals/`, `integrations/`, `providers/`, and top-level doc), plus four targeted web searches to ground external best-practice claims. Line citations were read directly from the files. Observations are separated from inferences throughout. Today's date for freshness judgments: 2026-06-26; the repo is at tag-less `v0.13.0` per `CHANGELOG.md:5`.

**Headline verdict.** This is an unusually mature *personal* config — well above the median public dotfiles/agent-config repo. It already does three things most teams' agent setups never reach: it (a) separates author-once source from rendered provider output, (b) enforces policy with a hook rather than prose alone, and (c) ships a real eval harness with an A/B value track and deterministic benchmarks. The strategic gaps are not "build the basics" — they are **closing the loop on the north-star**: almost nothing yet *measures* the token / context savings the repo exists to produce on the user's own day-to-day work, and the one weak-agent uplift claim is untested on a weak agent.

---

## 1. Maturity scorecard

Scale: **Nascent → Developing → Mature → Leading**. "Leading" means at or ahead of current public SOTA for the dimension.

| # | Dimension | Rating | One-line verdict |
|---|---|---|---|
| D1 | Source architecture / single-source-of-truth | **Mature → Leading** | Clean author-once-render-many with merge-not-overwrite and per-machine resolution; only gap is it is shell-rendered, not a typed pipeline. |
| D2 | Skill design quality | **Mature** | Trigger-optimized descriptions, correct progressive disclosure on the one big skill; mild redundancy between principles/skills/workflows and an uneven granularity (one 421-line skill vs seven ~50-line ones). |
| D3 | Instruction / prompt design | **Mature → Leading** | Lean (AGENTS.md 72 lines), non-contradictory, explicit precedence table; hand-curated in line with 2026 AGENTS.md guidance. |
| D4 | Evaluation & measurement | **Developing → Mature** | Two-track + deterministic bench is ahead of the field *structurally*; but the north-star metrics are captured-not-gated, and the value track has N=1 case at medium confidence. |
| D5 | MCP integration | **Mature** | Catalogued-vs-vendored discipline, placeholder env handling, per-integration READMEs; lean-ctx Claude-side wiring is documented as a known follow-up. |
| D6 | Prompt-caching / token-economy discipline | **Mature** | The repo practices its own playbook: the rendered `CLAUDE.md` is a stable static prefix with no per-request dynamic content; minor ordering nits remain. |
| D7 | Security & secrets posture | **Mature** | Placeholders + gitignored `.env`, no tracked secrets, hook fails safe; the every-command hook is a reviewed, bounded surface but is unverified-on-every-platform. |
| D8 | Release / versioning / change-mgmt | **Developing** | Excellent CHANGELOG and CI-check/doctor discipline, but **zero git tags** despite semver, and CI workflow untracked. |
| D9 | Observability (can the user SEE the savings?) | **Nascent → Developing** | Deterministic bench proves savings *on fixtures*; there is **no loop measuring the user's real-session token/context occupancy** — the central north-star instrument is missing. |
| D10 | Documentation | **Leading** | README/SETUP/ARCHITECTURE/PLAYBOOK/BENCHMARKS are coherent, honest, and cross-linked; rare for a personal repo. |

Aggregate: the repo sits at **Mature** with two Leading dimensions (architecture-ish, docs) and two soft spots (observability of real value, release hygiene). The soft spots are precisely the ones standing between "well-built config" and "provably delivers its north-star."

---

## 2. Per-dimension detail

### D1 — Source architecture & single-source-of-truth (Mature → Leading)

The author-once-render-many model is real and well-documented. `ARCHITECTURE.md:8-23` states the mental model and shows the render flow; `core/` is the source, `bin/install.sh` renders into `~/.cursor/*` / `~/.claude/*`. The two highest-leverage maturity signals here:

- **Merge, don't overwrite.** `merge-mcp.py` merges fragments into the existing target so hand-added work-only servers survive a reinstall (`ARCHITECTURE.md:86-89`). This is the difference between a config you can run on an already-configured machine and one that clobbers it — directly serving the "safe to install on a configured machine" north-star.
- **Per-machine resolution, no hardcoded paths.** `AGENTIC_ROOT` is resolved from the script location (`providers/claude/install.sh:5`), and tool locations are resolved with `which` / `npm root -g` (`ARCHITECTURE.md:90-91`). The repo can live anywhere.
- **Backups on every destructive write** (`providers/claude/install.sh:42`, `:71`, `:90`) and a global `DRY_RUN` path.

Gap to Leading: the renderer is a set of bash `cat`/`sed` concatenations (`providers/claude/install.sh:44-63`) and two small Python merge scripts. It works, but it is **untyped and untested as a pipeline** — there is no schema for the rendered `CLAUDE.md`, no golden-file test that the render is stable byte-for-byte (which, per D6, is also a cache-correctness property). The Go rewrite (`plans/01-go-rewrite.md`) is the natural place to make the render a typed, testable transform; I defer the design there.

### D2 — Skill design quality (Mature)

**Descriptions are trigger-optimized.** This is the single most important skill-quality lever (Anthropic: the description is how the agent decides to fire), and the repo does it well. `prompt-caching-playbook`'s description packs concrete trigger phrases including bilingual ones — `core/skills/prompt-caching-playbook/SKILL.md:3` ("why is my LLM bill so high", "почему API LLM дорого", "как уменьшить токены"). The CHANGELOG shows this was a *deliberate, measured* tightening: the description was cut ~250→~60 words for trigger precision (`CHANGELOG.md:80-81`). Descriptions run 24–67 words across the eight skills — in the right band.

**Progressive disclosure is correct where it matters.** `prompt-caching-playbook` keeps SKILL.md at 421 lines (under Anthropic's 500-line guideline) and pushes deep per-provider mechanics into six `references/*.md` files (580 lines total), loaded on demand and explicitly indexed at `SKILL.md:386-396`. `bin/ci-check.sh` even verifies those `references/*.md` links resolve (`CHANGELOG.md:78-79`). This is textbook three-tier disclosure.

**Granularity is uneven, by design but worth naming.** Seven skills are ~37–61 lines; one (`prompt-caching-playbook`) is 421 + 580 reference lines; `no-mistakes` is 220 but is tool-generated and gitignored (`integrations/no-mistakes/README.md:45-52`). The small procedural skills (`git-safety`, `create-pr`, `verification-before-completion`) are appropriately terse. No skill is *too* big for its tier.

**Redundancy / overlap — the real maturity issue.** There are three layers that can each carry the same guidance, and the boundary is documented (`core/principles/README.md:10-20`: principle = always-on, skill = on-trigger) but not perfectly held:

- `verification-before-completion` (skill) substantially overlaps the `honesty` principle's "back claims with evidence" (`core/principles/honesty.md:7-11`) and Karpathy guideline #4 "goal-driven execution / loop until verified" (`core/principles/karpathy-guidelines.md:44-53`). The skill itself notes it "complements" another verification skill (`verification-before-completion/SKILL.md:48`). Three artifacts assert "verify before you claim done." That is defensible (always-on nudge + on-demand checklist) but it is *paid-for redundancy* in the always-on layer, which D6 says to minimize.
- `coding-principles.md` (user-rule) restates Karpathy #2/#3 (minimize scope, no over-engineering, surgical) almost one-to-one with `karpathy-guidelines.md:19-41`. Both are concatenated into the same `CLAUDE.md` (`providers/claude/install.sh:47-62`), so the agent reads the same instruction twice per turn.
- `core/workflows/README.md:12-22` re-lists every skill with a "use when" column that duplicates each skill's own `description`. This is a human decision-aid, not loaded into the agent, so the cost is maintenance drift, not tokens.

Gap to Leading: de-duplicate the always-on layer (one canonical statement of verify-before-done and of surgical-scope), and add an explicit "this lives here, not there" note so future additions don't re-fork. This is leverage, not ceremony — it directly reduces the static-prefix token cost the repo's own playbook flags.

### D3 — Instruction / prompt design (Mature → Leading)

The instruction layer is **lean and non-contradictory**, which 2026 best practice now treats as the dominant variable (see SOTA §3). Hard numbers: `AGENTS.md` is 72 lines; the four user-rules + three principles total ~137 lines (`wc -l`). The whole always-on instruction surface is on the order of ~210 lines — small.

**Precedence is handled explicitly and in one place.** The tool-precedence table (`AGENTS.md:18-42`) resolves the genuinely hard overlap — three layers (shell, search, read) can each be served by `rtk`, lean-ctx `ctx_*`, GitNexus, or `ast-grep` — with a first/second/last-resort table and four prose rules ("do not double-wrap", "pick by question type, not habit"). `ARCHITECTURE.md:108-110` enforces the invariant that precedence is defined *once* and not restated conflictingly elsewhere. This is the most sophisticated single artifact in the repo and is genuinely ahead of typical practice, where tool overlap is left to the model to guess.

**One real contradiction surface** worth flagging for maturity (mechanics → sibling 03/04): the precedence table says lean-ctx `ctx_*` is *first choice* for shell/search/read (`AGENTS.md:29-30`), the global `lean-ctx.md` rule says "NEVER use native Read/Grep/Shell when ctx_* equivalents are available," yet this very task's instructions and the deterministic-bench rationale both route around `ctx_*` in favor of `rtk` + native. The repo is internally consistent *within itself*; the tension is between the repo's portable rules and the machine's separately-installed lean-ctx rule. That is a layering question (which rule wins when both are present) that the repo half-answers at `AGENTS.md:36-37` but does not make unambiguous for a weak agent. Naming it is in scope; the fix is sibling 04's.

**Token economy of the instructions themselves is good** but not yet optimal for caching (see D6): the principles are concatenated in directory glob order (`providers/claude/install.sh:49`), which is stable but not deliberately ordered most-stable-first.

### D4 — Evaluation & measurement maturity (Developing → Mature)

Structurally, this is **ahead of the field**. The repo has three instruments, each matched to what it measures (`evals/README.md:13-28`):

1. **Conformance** — does a skill fire / a rule change behavior — single transcript, LLM-judge PASS/FAIL against `expect`/`expect_not`, with negative over-trigger guards.
2. **Value A/B** — does firing *help* — same prompt with/without the artifact, pairwise judge, run in **both orders** with a **flip-rate guard** (>10% ⇒ `UNRELIABLE`, `evals/lib/judge.py:16`, `:96-119`). Position bias, verbosity bias, and self-preference are explicitly named and the first is mechanically countered.
3. **Deterministic bench** — for fixed transforms where an LLM-judge A/B is the *wrong* instrument — code-based grading against fixtures in absolute numbers (`evals/bench.py`).

The judgment to *not* A/B a hook-enforced tool is itself a sign of maturity: `terminal-rtk`'s value can't be ablated by prompt because the hook compresses both arms, so an A/B "could only ever return a noisy UNRELIABLE tie" (`CHANGELOG.md:28-31`; `evals/PLAYBOOK.md:62-75`). Recognizing that your measurement instrument is mismatched to the thing measured is a senior move.

**The loop is mechanically enforced.** `evals/lint.py` fails CI if any skill under `core/skills/` lacks a case (`evals/README.md:93-95`, `evals/PLAYBOOK.md:37-42`), wired into `bin/ci-check.sh`. Cases are required to come from *observed* weaknesses, à la CursorBench, not invented to flatter the tool (`evals/PLAYBOOK.md:104-108`). The PLAYBOOK defines "done" for a new artifact as ship-a-conformance-case-and-a-value-case (`:28-42`).

**Where it is only Developing — and this is the crux for the north-star:**

- **The value track does not yet measure the north-star.** `agent.py:74-95` computes `tool_calls` and `transcript_chars` per arm, and the docstring calls them "the main signal for value cases whose payoff is economy." But the verdict logic (`run.py:108-117`) decides PASS/FAIL/UNRELIABLE **only** from the pairwise win-tally and flip-rate — the efficiency metrics are *recorded into the jsonl* (`run.py:85-88`) and surfaced as a "Tool-call Δ" column in `BENCHMARKS.md:11`, but **nothing gates on them and no token delta is computed**. So a treatment that is equally good but 3× cheaper in tokens and a treatment that is equally good and equally expensive both pass identically. The repo's central thesis (cut tokens) is measured for compression *tools* (D9, the bench) but not for the *agent's behavior* under the config.
- **Coverage is thin.** One value case exists (`evals/value/cases/ast-grep-structural-precision.json`), and `BENCHMARKS.md:11` shows it at **medium** confidence (prompt-ablation, not config-dir) with N=3, 2/3 treatment wins. That is a single, medium-confidence data point defending the entire value thesis. The exhaustive coverage gap list is sibling 05's; the *maturity* read is: the instrument is excellent, the data behind it is one case.
- **Weak-agent uplift is unmeasured.** The harness fully supports it — `run.py:127` takes `--model` and records per-model (`run.py:62-64`) — but `BENCHMARKS.md:11` has only `claude-opus-4-8`. The north-star "make even Haiku dramatically better" has **zero** evidence behind it today. This is the single highest-leverage measurement gap.

### D5 — MCP integration maturity (Mature)

Three integrations (`lean-ctx`, `gitnexus`, `no-mistakes`), each with a README, and the discipline is right:

- **Catalogued vs vendored is a hard invariant.** Third-party marketplace plugins are listed in `catalog/plugins.yaml` and never copied in (`ARCHITECTURE.md:99-101`); custom MCP servers are fragments under `integrations/*/mcp*.json` merged at install. The boundary is clean and stated.
- **Env handling via placeholders.** `__NPX__`, `__LEAN_CTX__`, etc. are substituted from the resolved environment / `.env` (`ARCHITECTURE.md:92-94`); `secrets/.env.example` documents every override and ships them commented-out as optional (`secrets/.env.example:1-25`).
- **Supply-chain awareness.** The GitNexus MCP server is pinned to a version, not `@latest`, "for reproducible, supply-chain-safe installs" (`CHANGELOG.md:194-195`).
- **Discoverability.** Each integration's README states the binary, the install command, and the per-machine vs per-repo distinction (`integrations/no-mistakes/README.md:24-37` makes the per-repo nature explicit).

Gap to Leading: the lean-ctx README itself flags that its Claude-side hooks wiring is a *follow-up* — "This wiring currently targets Cursor... The Claude equivalent... is a follow-up" (`integrations/lean-ctx/README.md:37-41`) — though `CHANGELOG.md:129-134` and `SETUP.md:93-99` claim the Claude hooks/permissions merge *is* done via `merge-settings.py`. That doc/state mismatch is a portability-mechanics item (sibling 04); the maturity read is that MCP integration is solid but has one stale README.

### D6 — Prompt-caching / token-economy discipline (Mature)

The interesting question: the repo *ships* a `prompt-caching-playbook` — does it eat its own dog food in how it lays out its own always-on context? Largely **yes**:

- **The rendered prefix is static, with no per-request dynamic content.** `install.sh:44-63` renders `CLAUDE.md` as stub → AGENTS.md → principles → user-rules, all from files, with **no timestamp, UUID, cwd, or git status injected** — exactly the anti-patterns the playbook's own checklist calls the top cache-killers (`prompt-caching-playbook/SKILL.md:243-261`, items #1–#4). The generated `CLAUDE.md.stub` is a fixed banner (`providers/claude/CLAUDE.md.stub:1-7`). So the personal instruction layer is, by construction, a cache-friendly static prefix. This is the repo practicing what it preaches.
- The playbook's canonical structure (`SKILL.md:74-99`) puts stable role/conventions before a cache breakpoint and dynamic env after — and the repo's own `CLAUDE.md` is all "before the breakpoint" content, which is correct for a file the host injects into the system prompt.

Where it is Mature-not-Leading:

- **Ordering is glob-order, not stability-order.** Principles are concatenated by shell glob (`install.sh:49`) and user-rules likewise (`:57`). It happens to be stable across installs, but the playbook's own rule is *most-stable-first* (`SKILL.md:24`, `:64-70`). If a future principle changes often, its position would invalidate everything after it. The repo doesn't *order for cache stability deliberately* — it gets there by accident of having all-stable content.
- **No byte-stability test.** D1's missing golden-file render test is also a *cache* gap: the playbook says a two-letter change breaks the cache (`SKILL.md:253`, `:413`), yet nothing asserts that re-running the installer produces a byte-identical `CLAUDE.md` when source is unchanged. A trivial whitespace drift in the render would silently cold-start the user's own cache.

Net: the repo is unusually self-consistent here — it is one of the few configs that could be audited against its own shipped checklist and largely pass.

### D7 — Security & secrets posture (Mature)

- **No secrets in tracked files.** `.env` and `*.local` are gitignored (`.gitignore:1-4`); only `.env.example` is tracked and it ships every value commented (`secrets/.env.example`). `ARCHITECTURE.md:102-106` states the invariant ("No secrets in the repo... fragments use `__PLACEHOLDER__`... The repo is private, but still keep secrets out").
- **The every-command hook is a bounded, reviewed surface.** `shell-guard.sh` runs as a PreToolUse Bash hook on *every* shell command (`providers/claude/hooks/shell-guard.sh`). It is `set -euo pipefail`, parses input defensively (`extract()` yields empty on missing key rather than aborting, `:19-28`), **fails open** for heredocs and already-wrapped commands (`:40-48`), and only ever *denies* on a narrow code-grep pattern or *rewrites* by prefixing `rtk` (`:50-77`). It does not exfiltrate, does not call network, and the JSON it emits is escaped (`:57`, `:76`). For a hook on the hottest path in the agent, this is a careful design.
- The hook's hardening was itself a tracked, deliberate change (`CHANGELOG`-adjacent commit `005d65a` "shell-guard: pass heredoc commands through, harden JSON parsing").

Gaps to Leading (maturity, not a bug list — defer specifics to 03):

- The hook's correctness is **asserted by `selftest.py` only for the gitnexus parser and eval logic**, not for the hook's own deny/rewrite/fail-open branches. A regex change in `CODE_EXT` (`:53`) could over-deny legitimate greps (it already bit me twice in this very review when grepping `.py`/`.md` config files — the hook denied a non-code grep because the path ended in a code extension). That false-positive class is a real usability cost and is untested.
- The hook executing on every command is a **single point of failure**: if it errors non-gracefully it could block all shell work. It is written to fail open, but there is no test proving it stays open under malformed input.

### D8 — Release / versioning / change management (Developing)

The **change narrative is excellent** — `CHANGELOG.md` is a genuine, honest, semver-numbered history (0.1.0 → 0.13.0) with Added/Changed/Removed/Known-limitation sections and even records empirically-verified caveats (`CHANGELOG.md:62-66`). `bin/ci-check.sh` (static checks) and `bin/doctor.sh` (`--deep`) give a real verify-the-install story.

But the **release mechanics are Nascent inside a Mature narrative**:

- **Zero git tags.** `git tag -l` returns nothing despite 13 documented semver releases and 17 commits. The CHANGELOG versions are not anchored to commits — there is no `v0.13.0` tag, so "which commit is 0.12.0" is unanswerable without reading the log. For a single-user repo this is low-harm, but it means the version numbers are decorative, not addressable.
- **CI workflow is untracked.** `.github/workflows/ci.yml` "exists locally but is untracked until a gh token has the `workflow` scope" (`ARCHITECTURE.md:134-135`, `SETUP.md:103-104`). So the static checks that *could* run on every push do not — CI discipline is aspirational, enforced only when the user remembers to run `bin/ci-check.sh` locally. The mechanism is built; the gate isn't closed.
- No `VERSION` file or single source for the version number (the CHANGELOG is it), so `report.py`'s `EVAL_SET_VERSION` (`evals/PLAYBOOK.md:177-181`) and the config version can drift independently.

This is the cheapest dimension to move up: tagging is one command per release; pushing the CI workflow is one `gh auth refresh`.

### D9 — Observability: can the user SEE the savings? (Nascent → Developing)

This is the **dimension most directly tied to the north-star, and the weakest.**

What exists: the deterministic bench produces concrete, model-independent savings numbers and commits them to `BENCHMARKS.md:20-38` — e.g. `rtk grep` compresses a 200k-line log ×4,884, lean-ctx ×215,872, `ast-grep` finds 4 true matches with 0 false positives where grep returns 12 (8 FP), gitnexus extracts 13 nodes/21 edges grep can't represent. This *proves the tools compress / are precise on fixtures*. It is real observability of the **tool primitives**.

What is missing — and it is the whole ballgame: **there is no loop measuring the token / context savings on the user's actual sessions.** The repo's thesis is "drastically reduce tokens and context pollution during agentic work." Nothing measures that on real work:

- No capture of context-window occupancy over a session (how full is the window, how much of it is tool-output noise vs signal).
- No before/after on the user's own transcripts (the value track *could* be this — it captures `transcript_chars` — but per D4 it neither computes a token delta nor gates on it, and it runs on synthetic prompts, not real sessions).
- No dashboard, rolling metric, or even a periodic "this week the config saved you ~N tokens" report. The prompt-caching skill *tells users* to build exactly this monitoring loop (`SKILL.md:163-201`, "Cache hit rate must be logged per-request and dashboarded") — but the repo does not instrument its *own* usage that way.

So the honest state: the repo can show that `rtk` compresses a synthetic log by 4,884×, but it **cannot show the user how many tokens the whole toolset saved them last Tuesday.** Closing this is the highest-leverage north-star move (see Recommendations R1).

### D10 — Documentation maturity (Leading)

Rare for a personal repo. `README.md` (orientation + layout table), `SETUP.md` (new-machine onboarding with honest caveats), `ARCHITECTURE.md` (the render model, invariants, how-to-extend, gotchas), `evals/PLAYBOOK.md` (the eval loop with templates and a decision tree), and `BENCHMARKS.md` (generated, versioned, "do not edit by hand"). They are cross-linked, consistent, and — importantly — **honest about limits**: `CHANGELOG.md:62-66` and `evals/README.md:74-85` openly stamp the config-dir isolation caveat and medium-confidence verdicts. The `honesty` principle is visibly lived in the docs, not just declared. The only documentation debt is the one stale lean-ctx-Claude follow-up note (D5) and the tag/CI aspirational claims (D8).

---

## 3. Benchmark against current SOTA

External claims below are grounded in current sources; citations follow the section. For each practice: does the repo do it (✅), partially (◐), or miss it (✗).

| SOTA practice | Repo | Evidence / gap |
|---|---|---|
| **agents.md convention** (open, Linux-Foundation-stewarded, hand-curated, brief, signal-dense) | ✅ | `AGENTS.md` is 72 lines of curated Markdown, no schema cruft, explicit precedence; matches the 2026 emphasis on brevity over generation. |
| **Anthropic Agent Skills** (SKILL.md + name/description trigger + progressive disclosure, <500 lines, references/) | ✅ | `prompt-caching-playbook` is the exemplar: 421-line body + 6 references, indexed and link-checked; descriptions are trigger-tuned and were measured-down for precision. |
| **MCP** for tool/integration surface | ✅ | Three MCP integrations as merged fragments, version-pinned, placeholder env. |
| **Prompt caching** (static prefix / dynamic suffix, no dynamic content in prefix) | ◐ | Repo *ships* the playbook and its own rendered `CLAUDE.md` is a clean static prefix (D6 ✅), but it doesn't *deliberately* order for stability or test byte-stability (◐). |
| **Eval-driven agent development** (iterate against measurements, regression-gated) | ◐ | Two-track + deterministic bench is structurally ahead; but value-track data is N=1 medium-confidence and the north-star metrics are captured-not-gated (D4). |
| **Hook-enforced (vs prompt-only) policy** | ✅ | `shell-guard.sh` enforces shell-wrapping and code-grep redirection mechanically; the repo explicitly moved `terminal-rtk` from "soft instruction" to hook (`terminal-rtk/SKILL.md:31-35`). This is ahead of most configs, which are prose-only. |
| **Subagent / orchestration patterns** (context isolation, tiered models, locked YAML for repeatable workflows) | ✗ | No subagent skill or orchestration pattern is offered to the user's agents. The catalog mentions `parallel` (web research) but the repo authors none. See the dedicated assessment in §4. |
| **Tiered models for cost** (Opus orchestrator / Sonnet worker / Haiku formatter, ~40% cheaper) | ✗ | No guidance or eval on model tiering, despite it being a direct token-cost lever and despite the harness already supporting `--model`. |
| **Measuring context-window occupancy / "minimal context" mode** | ✗ | Not measured, not offered (D9). |

**SOTA verdict.** On the *authoring* practices (agents.md, Skills, MCP, hook-enforcement, prompt-caching knowledge) the repo is at or near the frontier — genuinely strong. On the *operational* practices that close the loop toward the north-star (measuring real token/context savings, weak-agent benchmarking, subagent/orchestration, model-tiering) it has the *foundations* (a `--model`-aware harness, efficiency metrics in the transcript) but has not yet built the loops. The gap is operational, not conceptual — which is the good kind of gap.

Sources:
- [Equipping agents for the real world with Agent Skills — Anthropic](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Agent Skills overview — Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) (name/description trigger, <500-line SKILL.md, references/)
- [AGENTS.md — agentsmd/agents.md (GitHub)](https://github.com/agentsmd/agents.md) and [AGENTS.md Spec 2026 — Morph](https://www.morphllm.com/agents-md-guide) (open standard, 60k+ repos, brevity/signal-density; 2026 research that LLM-generated context files hurt performance)
- [Claude Code Sub-Agents Explained: Context, Cost, Parallel Execution — MindStudio](https://www.mindstudio.ai/blog/claude-code-sub-agents-explained) and [Claude Code Agents in 2026 — CloudZero](https://www.cloudzero.com/blog/claude-code-agents/) (context isolation; runaway token costs; tiered-model ~40% cheaper)
- [Best practices for Claude Code — Claude Code Docs](https://code.claude.com/docs/en/best-practices)

---

## 4. Strategic recommendations (prioritized by north-star leverage)

Ordered by leverage toward {token reduction, weak-agent uplift, composition, genericity}. Each respects the repo's own anti-over-engineering principles — these are loops and instruments, not ceremony.

**R1 — Build the real-session value loop (D9, the missing north-star instrument). HIGH leverage.**
The repo's whole reason to exist is "fewer tokens / less context pollution on real work," and nothing measures that on real work. Concretely: add a lightweight post-session metric that reads a Claude Code transcript (the harness already parses stream-json in `agent.py`) and reports context-window occupancy and the tool-output-noise share, plus a rolling "tokens saved vs a no-config baseline" estimate. Start as a single script (`evals/observe.py`) that ingests a transcript and emits the numbers — no dashboard needed for one user. This turns the central claim from asserted to observed and feeds every other decision below.

**R2 — Make the value track gate on economy, not just quality (D4). HIGH leverage.**
The efficiency metrics are already captured (`agent.py:95`) but unused in the verdict (`run.py:108-117`). Add a token/transcript-delta to the pairwise result and let `treatment_not_worse` cases pass/fail on *economy* (e.g. "not worse on quality AND ≥X% fewer tokens"). This is a ~20-line change that makes the existing instrument actually measure the north-star. Low effort, high payoff.

**R3 — Run the weak-agent benchmark (D4, north-star "make Haiku dramatically better"). HIGH leverage.**
The harness supports `--model` and records per-model already. Run the existing value + conformance cases under a weak model (Haiku-class) and commit a second column to `BENCHMARKS.md`. Today the "weak agent uplift" claim has zero evidence; this produces the first. It also reveals which skills actually help a weak model vs which only a strong model already does for free — directly informing what to keep in the always-on layer (R5).

**R4 — Offer a research/review subagent skill, cost-bounded and model-tiered (SOTA gap; see §5 below for the full assessment). MEDIUM-HIGH leverage.**
Detailed design and the cost argument are in §5. Summary: yes, ship one — but as a *locked, repeatable* subagent (fixed model = Sonnet/Haiku worker, fixed read-only tool set, explicit token ceiling), not open-ended parallel fan-out.

**R5 — De-duplicate the always-on layer (D2/D6). MEDIUM leverage.**
Collapse the triple-stated "verify before done" (skill + honesty principle + Karpathy #4) into one canonical always-on line plus the on-demand checklist skill, and merge `coding-principles.md` with the overlapping Karpathy guidelines so the agent doesn't read the same instruction twice per turn (`install.sh:47-62`). Every line removed from the always-on prefix is a per-turn token saving — the repo's own playbook logic applied to itself. Pair with an eval that the behavior survives the trim (don't cut blind).

**R6 — Close the release-hygiene gap (D8). MEDIUM leverage, LOW effort.**
Tag the 13 releases (at minimum tag HEAD as `v0.13.0` going forward), and push `.github/workflows/ci.yml` so `ci-check.sh` + `lint.py` + `selftest.py` run on every push (the `gh auth refresh -s workflow` step is already documented). This makes the excellent CHANGELOG addressable and turns the built-but-ungated CI into an actual gate.

**R7 — Add cache-stability discipline to the render (D1/D6). MEDIUM leverage, LOW effort.**
Add a golden-file test that re-rendering `CLAUDE.md` from unchanged source is byte-identical, and order the concatenation most-stable-first. This protects the user's *own* prompt cache (a whitespace drift would cold-start it) and is the repo eating its own playbook. Naturally folds into the Go rewrite (sibling 01) if a typed renderer lands.

**R8 — Add a "minimal context" mode (north-star lever the owner may have missed). MEDIUM leverage.**
A switch that loads only the precedence table + the verify principle and *suppresses* the heavier always-on content for short/cheap tasks — the inverse of progressive disclosure applied to the always-on layer. Most turns don't need the full principle set in context; a weak agent especially pays for carrying it. Could be as simple as a second, slimmer rendered profile selectable per session. Validate with R3's weak-agent bench (does the slim profile keep the conformance wins at lower token cost?).

### North-star levers the owner may have missed (called out explicitly)

1. **Context-window occupancy as a first-class metric** (R1) — not just "did the tool compress its output" but "how much of the live window is signal." This is the truest measure of "context pollution" and is absent.
2. **Skill-trigger precision tuning as an ongoing loop** — the repo measured the prompt-caching description down once (`CHANGELOG.md:80-81`); make that a repeatable practice with a trigger-precision metric (false-fire rate from the negative conformance cases), so descriptions are tuned by data over time, not once.
3. **Model-tiering guidance + eval** (folded into R3/R4) — Opus-orchestrator / Sonnet-worker / Haiku-formatter is a documented ~40% cost cut; the repo offers no guidance on it despite the harness supporting per-model runs.
4. **Caching the instruction prefix explicitly** (R7) — treat the rendered `CLAUDE.md` as a cache artifact with a stability contract, not just a generated file.
5. **A "weak-agent regression" gate** — once R3 produces weak-agent numbers, gate on them: a change that helps Opus but *hurts* Haiku should be visible, because "make even a weak agent better" is the north-star, and Opus-only evals can mask weak-agent regressions.

---

## 5. The subagent / orchestration question (explicit assessment)

**Should the toolset itself offer subagent/orchestration patterns to the user's agents, and is the token cost justified?**

**Verdict: Yes — ship one narrowly-scoped, cost-bounded subagent skill, and argue *against* open-ended parallel fan-out.**

The case *for*: the north-star has two halves a subagent serves directly. (a) Context isolation — a research/review subagent explores in its own window and returns only a summary, keeping the main conversation's context clean. This is *exactly* "reduce context pollution": the 30 files a research task reads never enter the main window. Current practice confirms this is the primary benefit (subagents "report back summaries without cluttering your main conversation"). (b) Weak-agent uplift via tiering — an Opus orchestrator delegating to Sonnet/Haiku workers is a documented ~40% cost reduction with minimal capability loss on worker tasks, which is the repo's "make a weak agent perform better" goal expressed as orchestration.

The case *against* naive subagents (the cost trap): the field has real horror stories — a single parallel-fan-out session estimated at $8K–$15K, a team that burned $47K in three days from 23 unattended subagents. Open-ended "use subagents to parallelize everything" is precisely the token-explosion the repo exists to prevent. So an *unbounded* orchestration pattern would betray the north-star, not serve it.

**The reconciling design — a locked, bounded subagent skill:**

- **Repeatable, not ad-hoc.** Define it as a fixed skill (e.g. `research-subagent` / `review-subagent`) with a **locked model** (Sonnet or Haiku worker, never Opus) and a **frozen, read-only tool set** (search + read only — no write, no shell-mutation). Current best practice: "for repeatable workflows use subagents... locked model and system prompt... cost-predictable."
- **One subagent, sequential by default.** No parallel fan-out in the shipped pattern. Parallelism is a time-vs-token trade the user can opt into explicitly; the *default* serves the token north-star (sequential exploration is the cheaper budget per current guidance).
- **An explicit token ceiling / file-count cap** in the skill instructions ("read at most N files, return a ≤K-token summary, stop"). This is the guardrail the $47K stories lacked.
- **Return-summary contract.** The subagent's *only* output to the main context is a structured summary — the whole point is that its exploration tokens don't pollute the parent window.
- **Defended by an eval.** Per the repo's own loop (`PLAYBOOK.md:28-42`): a value case proving the subagent variant returns an equally-good answer at *lower main-context occupancy* than doing the research inline. This is the first case that would *use* R1's occupancy metric and R2's economy-gating — the subagent skill and the missing instruments are mutually reinforcing.

**Is the token cost justified?** For research/review over many files — **yes**: the parent-context savings (and the option to run the worker on a cheap model) outweigh the subagent's own tokens, *provided* the bound is enforced. For small tasks — **no**, and the skill's description must be trigger-scoped to "investigate across many files / review a large diff," not fire on trivial work (the same over-trigger discipline the repo already applies via negative conformance cases). Without the bound and the scoping, the cost is *not* justified and the repo should not ship it. With them, it is one of the higher-leverage north-star additions available.

This lands as **R4** in the backlog, dependent on R1 (occupancy metric) and R2 (economy gating) so its payoff is measurable rather than asserted — consistent with the repo's "no undefended claims" stance.

---

## 6. Prioritized backlog

Leverage = pull toward the north-star. Effort: S (<½ day) / M (1–2 days) / L (multi-day). "Depends-on" lists prerequisite IDs.

| ID | Title | Dimension | Leverage | Effort | Depends-on |
|----|-------|-----------|----------|--------|------------|
| MAT-01 | Real-session value loop: measure context-window occupancy + tokens-saved-vs-baseline from transcripts | D9 / observability | **High** | M | — |
| MAT-02 | Gate the value track on economy (token/transcript delta), not just pairwise quality | D4 / evals | **High** | S | — |
| MAT-03 | Run + commit weak-agent (Haiku-class) benchmark column; first evidence for "weak-agent uplift" | D4 / north-star | **High** | M | MAT-02 |
| MAT-04 | Ship one locked, cost-bounded research/review subagent skill (fixed worker model, read-only tools, token ceiling, summary contract) + defending eval | SOTA / orchestration | **High** | M | MAT-01, MAT-02 |
| MAT-05 | De-duplicate the always-on layer (collapse triple "verify-before-done"; merge coding-principles with Karpathy overlap) + eval the trim | D2 / D6 | Med | M | MAT-02 |
| MAT-06 | Tag the 13 semver releases; push `.github/workflows/ci.yml` so static checks gate every push | D8 / release | Med | S | — |
| MAT-07 | Golden-file byte-stability test for rendered `CLAUDE.md`; order concatenation most-stable-first | D1 / D6 | Med | S | — |
| MAT-08 | "Minimal context" rendered profile (precedence + verify only) for short/cheap tasks | D6 / north-star | Med | M | MAT-03 |
| MAT-09 | Trigger-precision metric loop (false-fire rate from negative conformance cases) to tune skill descriptions by data | D2 / evals | Med | S | — |
| MAT-10 | Weak-agent regression gate: flag changes that help Opus but hurt Haiku | D4 / north-star | Med | S | MAT-03 |
| MAT-11 | Test `shell-guard.sh` deny/rewrite/fail-open branches; fix the code-extension over-deny on non-code greps | D7 / security | Med | S | — (coordinate w/ 03) |
| MAT-12 | Reconcile lean-ctx-Claude wiring docs (stale "follow-up" note vs implemented merge) | D5 | Low | S | — (defer mechanics to 04) |
| MAT-13 | Add an explicit "where guidance lives" note (principle vs skill vs user-rule) to prevent future re-forking | D2 | Low | S | MAT-05 |

Cross-references: MAT-11's *fix* mechanics and MAT-12's portability mechanics belong to siblings 03/04 respectively — listed here only for the maturity rationale. The exhaustive eval-coverage expansion (beyond MAT-02/03's instrument changes) is sibling 05's backlog.

---

## Appendix: evidence index (selected)

- Source-of-truth render model — `ARCHITECTURE.md:8-23`, `:68-95`; render concatenation — `providers/claude/install.sh:44-63`.
- Merge-not-overwrite + per-machine resolution — `ARCHITECTURE.md:86-94`.
- Skill descriptions / progressive disclosure — `core/skills/prompt-caching-playbook/SKILL.md:3`, `:386-396`; line/word counts via `wc` (8 skills, 24–67-word descriptions).
- Always-on layer redundancy — `core/principles/honesty.md:7-11`, `core/principles/karpathy-guidelines.md:44-53`, `core/instructions/user-rules/coding-principles.md:1-9`, `core/skills/verification-before-completion/SKILL.md:48`.
- Tool-precedence table (single source) — `core/instructions/AGENTS.md:18-42`; invariant — `ARCHITECTURE.md:108-110`.
- Eval architecture — `evals/README.md:13-28`; flip-rate guard — `evals/lib/judge.py:16`, `:96-119`; efficiency metrics captured but not gated — `evals/lib/agent.py:74-95` vs verdict `evals/run.py:108-117`; per-model support — `evals/run.py:127`, `:62-64`; current data — `evals/BENCHMARKS.md:11` (one case, medium confidence, opus-only).
- Deterministic bench results — `evals/BENCHMARKS.md:20-38`; rationale — `evals/PLAYBOOK.md:62-101`, `evals/bench.py:1-23`.
- Cache-friendly static prefix — `providers/claude/CLAUDE.md.stub:1-7`, render `install.sh:44-63`; playbook anti-patterns it avoids — `SKILL.md:243-261`.
- Secrets posture — `.gitignore:1-4`, `secrets/.env.example`, `ARCHITECTURE.md:102-106`; hook safety — `providers/claude/hooks/shell-guard.sh` (`:15` set -e, `:40-48` fail-open, `:50-77` deny/rewrite).
- Release gaps — `git tag -l` empty (17 commits, 13 CHANGELOG versions); CI untracked — `ARCHITECTURE.md:134-135`, `SETUP.md:103-104`.
- MCP discipline — `ARCHITECTURE.md:99-101`, version-pin `CHANGELOG.md:194-195`; stale lean-ctx-Claude note — `integrations/lean-ctx/README.md:37-41`.

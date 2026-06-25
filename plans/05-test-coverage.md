# 05 — Test & Harness Coverage Plan

> Can we prove the toolset works, *together*, and catch regressions when it stops?

## Scope & ownership

This document owns **test and harness coverage**: what the repo verifies today, what
it does not, and a prioritized plan to close the gap — with a sharp focus on the
owner's stated north-star, *"I want the entire toolset in this repo to work together
and complement each other,"* verified by tests/harnesses.

I own:

- The coverage inventory and matrix (unit × test-type).
- The **"works together" / integration / end-to-end** harness plan.
- The **north-star measurement** plan (token-delta, context-pollution, Haiku-uplift).
- CI / regression-protection assessment.
- The **test requirements handed to the Go `agentic` binary** (doc 01).

I explicitly **defer**:

- **Harness *code bugs*** (logic errors in `run.py`, `judge.py`, the hook's regex,
  etc.) → **plans/03-gaps-and-bugs.md**. Where a coverage gap exists *because* of a
  likely bug, I note it and cross-link, but the fix is 03's.
- **The Go binary design** (what it is, its architecture) → **plans/01**. I give 01
  the *test* requirements only.
- **Strategy / maturity grade** → **plans/02**. I supply concrete gaps; 02 issues the
  verdict.
- **Portability scenarios** → **plans/04**. 04 hands me install-onto-a-fixture-`$HOME`
  scenarios; I fold them into the harness plan here (see [TEST-09](#test-09)).

Everything below is grounded in files read on branch `feature/value-evals-loop`.
Observed facts are cited `path:line`; inferences are labelled.

---

## 1. What exists today

The repo has **four** distinct verification surfaces. Three are token-free and
deterministic; one spends tokens and uses an LLM judge.

### 1.1 Static lint — `evals/lint.py`

- **Covers:** JSON schema of every conformance/value case (`cases.validate`,
  `evals/lib/cases.py:34`), unique ids across all tracks, value `ablate` targets
  resolve to a real skill dir (`evals/lint.py:48`), bench-spec schema
  (`evals/lint.py:74`), and the **coverage gate**: every dir under `core/skills/`
  must be named by ≥1 case or the build fails (`evals/lint.py:59`).
- **Cost / determinism:** zero tokens, fully deterministic. Observed PASS:
  `lint OK — 18 cases (5 bench specs), 8 skills covered.`
- **Caveat (coverage credit is a substring match).** A conformance case earns a skill
  "covered" if the skill *name string* appears in `rule + id`
  (`evals/lint.py:53-57`). This is weak: a case can satisfy the gate by *mentioning*
  a skill in prose without actually exercising it. So "8/8 skills covered" overstates
  real coverage — see the matrix in §2.

### 1.2 Harness self-test — `evals/selftest.py`

- **Covers** the two non-LLM, error-prone pieces of harness logic: the pairwise
  order-swap → treatment/control mapping and position-bias detection
  (`evals/selftest.py:27-41`), the `_value_verdict` thresholds
  (`evals/selftest.py:50-58`), and the gitnexus summary-line regex
  (`evals/selftest.py:44`).
- **Cost / determinism:** zero tokens, deterministic. Observed PASS:
  `selftest OK — 4 checks.`
- **Caveat (monkeypatch isn't restored).** The tests overwrite `judge._judge_once`
  globally (`evals/selftest.py:31,38`) without saving/restoring it. Harmless today
  (sorted run order, process exits) but brittle. *Bug → defer to plans/03;* I note it
  only because it touches harness trustworthiness.

### 1.3 Conformance + value tracks — `evals/run.py`

- **Conformance** (`run_conformance`, `evals/run.py:47`): one prompt → one transcript
  → one LLM-judge PASS/FAIL against `expect`/`expect_not` (`evals/lib/judge.py:69`).
  **12 cases** in `conformance/cases/`. Cost: 1 agent call + 1 judge call per case.
- **Value A/B** (`run_value`, `evals/run.py:61`): same prompt run **treatment vs
  control**, judged pairwise in **both orders** with a flip-rate gate
  (`evals/lib/judge.py:96`); `flip_rate > 0.10` ⇒ `UNRELIABLE` (`judge.py:16`,
  `run.py:110`). **1 case** in `value/cases/` (`ast-grep-structural-precision`). Cost:
  `2 arms × N × 2 judge-orderings` per case (N defaults to 3 → 12 model calls/case).
- **Control isolation** (`evals/lib/render_config.py`): `config-dir` (high confidence,
  physically removes the skill, needs `ANTHROPIC_API_KEY`) or `prompt` (medium, the
  control arm is *asked* to ignore the skill). Default is `prompt`
  (`render_config.py:38-42`).
- **Free efficiency metrics** (`agent.metrics`, `evals/lib/agent.py:74`):
  `tool_calls` and `transcript_chars`, parsed from the stream-json transcript. These
  are the only economy signals captured today.

### 1.4 Deterministic tool benchmarks — `evals/bench.py`

- **Covers** the tools whose value is a fixed transform, not an agent choice
  (`evals/bench.py:1`). **5 specs**:
  - `compression` (3): `rtk` grep, `rtk` log-dedup, `lean-ctx` grep vs a 200k-line
    noisy fixture — reports bytes/lines/approx-tokens and reduction factor
    (`bench.py:89`).
  - `precision` (1): `ast-grep` vs regex grep on `calls.ts`, counting false positives
    against `true_matches: 4` (`bench.py:99`).
  - `graph` (1): `gitnexus analyze` on a Go fixture → nodes/edges/clusters/flows vs
    grep's flat text count (`bench.py:109`).
- **Cost / determinism:** zero tokens; runs the **real binaries**, so it runs locally,
  **not in CI** (the CI runner has no `rtk`/`lean-ctx`/`gitnexus`)
  (`PLAYBOOK.md:98`). Numbers committed to `BENCHMARKS.md` show e.g. `rtk` grep at
  ×4,884 byte reduction and `ast-grep` at 0 FP vs grep's 8 FP (`BENCHMARKS.md:24,32`).

### 1.5 Static repo health — `bin/ci-check.sh` and `bin/doctor.sh`

- **`bin/ci-check.sh`** (static, zero-token, intended for CI): `bash -n` syntax +
  `shellcheck` on every `.sh`, JSON/YAML validity, `SKILL.md` frontmatter present
  (`ci-check.sh:49`), skill reference links resolve (`ci-check.sh:61`), then runs
  `lint.py`, `selftest.py`, and a `run.py --track all` **dry-run** parse
  (`ci-check.sh:76-85`). This is the closest thing to a regression gate the repo has.
- **`bin/doctor.sh`** (post-install **health** check, not a test): verifies symlinks,
  that merged `mcp.json` contains `gitnexus`, `CLAUDE.md` references `agentic`,
  binaries are on PATH; `--deep` adds version-pin and JSON-validity checks
  (`doctor.sh:100`). It inspects a *live install*; it does not test the install logic
  against a fixture.

### 1.6 The gap you can see from the inventory alone

| Surface | Tokens | In CI? | What it proves |
|---|---|---|---|
| `lint.py` | 0 | only if CI exists | cases are well-formed; each skill is *mentioned* |
| `selftest.py` | 0 | only if CI exists | pairwise/verdict math is correct |
| conformance | yes | no (token cost) | each rule *fires* in isolation |
| value A/B | yes | no | one skill (`ast-grep`) *helps* in isolation |
| `bench.py` | 0 | no (needs real binaries) | each tool's transform is real, in isolation |
| `ci-check.sh` | 0 | **no workflow exists** | static hygiene |
| `doctor.sh` | 0 | n/a (manual) | a live install looks right |

**Two structural facts jump out and frame the rest of this plan:**

1. **Everything tests one tool at a time.** There is **no test that runs the toolset
   together** on a realistic task. (Detail in §3.)
2. **`.github/workflows/` does not exist.** Verified: `find .github -type f` returns
   nothing. So *none* of the above runs automatically — the "CI on every PR" claims in
   `README.md:86` and `PLAYBOOK.md:202` are **aspirational**. (Detail in §5.)

---

## 2. Coverage matrix (unit × test-type)

Legend: **D** deterministic test · **C** conformance eval · **V** value A/B · **H**
ci-check/doctor (static/health) · **—** nothing. Parenthetical = partial/weak.

| Unit of the system | D | C | V | H | Verdict |
|---|---|---|---|---|---|
| **Skill: ast-grep** | D | C | V | H | Best-covered unit in the repo |
| **Skill: terminal-rtk** | D¹ | C | — | H | Behavior fires; value only via bench proxy |
| **Skill: gitnexus-navigation** | D² | C | — | H | Graph extraction benched; *agent uplift* untested |
| **Skill: prompt-caching-playbook** | — | C×5 | — | H | Triggering well-covered; **no value/uplift** eval |
| **Skill: git-safety** | — | C | — | H | Negative behavior only; no value |
| **Skill: create-pr** | — | C | — | H | Fires; no value |
| **Skill: verification-before-completion** | — | C | — | H | Fires; no value |
| **Skill: no-mistakes** | — | — | — | (H) | **Exempt** from lint (`lint.py:21`); untested here by design |
| **lean-ctx (as a tool)** | D³ | (C)⁴ | — | (H) | Compression benched; integration untested |
| **Instruction: tool-precedence table** (AGENTS.md) | — | (C)⁵ | — | — | **No test of the precedence *resolution*** |
| **Principle: honesty** | — | — | — | — | **NONE** |
| **Principle: karpathy-guidelines** | — | — | — | — | **NONE** |
| **shell-guard hook — branch 1 (ast-grep deny)** | — | (C)⁶ | — | — | **No direct hook test** |
| **shell-guard hook — branch 2 (lean-ctx rewrite)** | — | — | — | — | **NONE** |
| **shell-guard hook — branch 3 (rtk fallback)** | — | (C)⁶ | — | — | **No direct hook test** |
| **shell-guard — passthrough guards** (already-wrapped, heredoc) | — | — | — | — | **NONE** (regression-prone; see §3.2) |
| **merge-mcp.py** | — | — | — | (H)⁷ | **No golden test** |
| **merge-settings.py** | — | — | — | — | **NONE** |
| **install.sh (claude provider)** | — | — | — | (H)⁷ | dry-run parses; **no output assertion** |
| **install.sh (cursor provider)** | — | — | — | (H)⁷ | same |
| **install.sh (idempotency / re-run)** | — | — | — | — | **NONE** |
| **bootstrap.sh** | — | — | — | — | **NONE** (hard to test; deps) |
| **CLAUDE.md render (concat principles+rules)** | — | — | — | — | **NONE** |
| **Cursor principle/rule render (.mdc)** | — | — | — | — | **NONE** |

Footnotes:
¹ `rtk-grep-compression`, `rtk-log-compression` bench `rtk` as a transform, not the
skill's agent-facing instruction.
² `gitnexus-graph-extraction` benches the binary's graph output, not whether the agent
*uses* it to answer better.
³ `leanctx-grep-compression`.
⁴ lean-ctx appears as an *accepted alternative* inside several conformance `expect`
lines (e.g. `shell-rtk-prefix`, `code-search-uses-ast-grep`) but is never the unit
under test.
⁵ Precedence is *implied* by per-skill conformance cases, but **no case tests an
overlap** (e.g. "a text search that is also code" — which layer wins?).
⁶ The hook is the *mechanism* that should force the ast-grep/rtk behavior, but the
conformance cases grade the **agent transcript**, not the hook's stdout. The hook
could be completely broken and these cases could still pass (the model might comply on
its own). So the hook itself is **untested**.
⁷ `doctor.sh` checks a live install exists and is valid JSON; it never diffs produced
output against an expected golden, and never runs against a throwaway `$HOME`.

### 2.1 The biggest uncovered surfaces (by leverage)

1. **The shell-guard hook is the load-bearing enforcement mechanism and has zero
   direct tests.** It has three branches plus two passthrough guards
   (`shell-guard.sh:40-77`), all driven by fragile regex/`sed` JSON handling. If it
   regresses, *every* shell command silently stops being compressed/redirected and no
   test notices. **Highest-leverage gap in the repo.**
2. **"Works together" is untested entirely** (§3) — the owner's explicit priority.
3. **The north-star (tokens / Haiku-uplift) is not measured** (§4) — only proxied by
   single-tool bench numbers and an incidental `tool_calls` delta.
4. **merge-mcp / merge-settings** are pure, deterministic functions that *mutate the
   user's real config* and have **no golden tests** — the cheapest high-value tests to
   add (§3.3).
5. **Principles** (honesty, karpathy) are always-on and shape every turn, yet have
   **no eval at all**. Lower leverage (hard to test cheaply) but worth one conformance
   case each.

---

## 3. The "works together" gap — the owner's priority

> Observed: every existing test exercises exactly **one** artifact. Inferred from that:
> the repo currently has **no evidence** that the tools *complement* each other rather
> than merely each working alone. This is the central gap.

### 3.1 What "together" should mean here (and the failure modes that hide in the seams)

The toolset is a *pipeline of layered defaults*, and the interesting failures live in
the **interactions**, which no current test touches:

- **Precedence collisions.** AGENTS.md defines an order (GitNexus → ast-grep →
  lean-ctx → grep for search; lean-ctx → rtk for shell). The shell-guard hook encodes
  part of this (`shell-guard.sh:50-77`). *Nothing tests that exactly one layer fires.*
  The hook's own comment promises "Exactly one of these fires per command, so there is
  no double-wrapping" (`shell-guard.sh:14`) — an untested invariant.
- **Double-wrapping.** The rules forbid `rtk` inside `ctx_shell` and vice-versa
  (AGENTS.md "Do not double-wrap"). The hook guards against it
  (`shell-guard.sh:40-42`). `shell-rtk-prefix`'s `expect_not` mentions it, but only as
  judged agent behavior — the *hook's* guard is untested.
- **Hand-off correctness.** lean-ctx's redirect hook and the ast-grep deny both target
  Read/Grep; if both match, ordering matters. Untested.

### 3.2 Plan: a deterministic **hook test harness** (highest leverage, zero tokens)

<a name="test-01"></a>**TEST-01 — shell-guard golden-envelope tests.**
The hook is a pure `stdin JSON → stdout JSON` function. Test it directly with table-
driven fixtures; no agent, no tokens.

- **Shape:** a Python (or bash) runner pipes a hook-input JSON into
  `providers/claude/hooks/shell-guard.sh` and asserts the stdout envelope.
- **Cases (one row each):**
  | input `command` | expected |
  |---|---|
  | `grep -n foo src/app.ts` (code ext) | `permissionDecision: deny`, reason mentions `sg -p` |
  | `grep INFO /var/log/x.log` | empty stdout (passthrough) |
  | `git status` | branch-2 lean-ctx rewrite **iff lean-ctx present**, else branch-3 `rtk git status` |
  | `python3 evals/run.py` | branch-3 `updatedInput.command == "rtk python3 …"` |
  | `rtk grep foo` (already wrapped) | empty stdout (no double-wrap) |
  | `lean-ctx -c "git log"` (already wrapped) | empty stdout |
  | `cat <<EOF\n…\nEOF` (heredoc) | empty stdout (`shell-guard.sh:46`) |
  | non-Bash tool (`Read`) | empty stdout (`shell-guard.sh:31-34`) |
  | malformed JSON input | clean exit 0, no crash (guards `set -e`) |
- **Cost:** deterministic, milliseconds. **Run in CI.**
- **Why north-star:** this is the *mechanism* that makes a weak agent obey
  rtk/ast-grep without relying on model discipline — the literal embodiment of "make
  even a weak agent perform better." If it regresses, the whole value proposition
  silently collapses. Today nothing guards it.
- **Note for plans/03:** while writing these fixtures I hit a real over-trigger: the
  branch-1 regex `\.($CODE_EXT)` (`shell-guard.sh:53-55`) matches a code extension
  appearing **anywhere** in the command string — including the *search pattern* of a
  legitimate log grep (e.g. `grep "load app.py" server.log` is denied). I tripped this
  myself during exploration. The *fix* is 03's; TEST-01 should encode the **intended**
  behavior so 03 has a target to make pass.

<a name="test-02"></a>**TEST-02 — lean-ctx mock for branch-2.**
Branch 2 depends on `lean-ctx` being installed and emitting `updatedInput`
(`shell-guard.sh:65-71`). In CI there is no lean-ctx. Add a **stub `lean-ctx`** on
`PATH` for the test that emits a known rewrite envelope, and assert the hook honors it
verbatim and does *not* also apply rtk (no double-wrap). Deterministic, CI-safe.

<a name="test-03"></a>**TEST-03 — precedence-resolution conformance pair (LLM, small).**
One conformance case for the genuinely ambiguous overlap the matrix flags as
untested: a prompt that is *both* a concept search and a code search, asserting the
agent resolves to the documented winner (ast-grep for code-shaped, lean-ctx/grep for
prose). 1 agent + 1 judge call. Keep to **one** case — most precedence is already
mechanically enforced by the hook (cheaper to test via TEST-01).

### 3.3 Plan: **golden install/merge tests** (deterministic, zero tokens)

<a name="test-04"></a>**TEST-04 — merge-mcp golden.** Feed `merge-mcp.py` a fixture
`integrations/` tree + a fixture pre-existing `mcp.json` containing a hand-added
work-only server, into a temp output. Assert: (a) repo-managed servers present and
substituted, (b) the pre-existing server **preserved** (the explicit contract at
`merge-mcp.py:98-102`), (c) deterministic key order. Deterministic.

<a name="test-05"></a>**TEST-05 — merge-settings golden.** Feed a fixture
`settings.json` carrying a machine-local `env` block + an existing `permissions.deny`.
Assert the hook block is **replaced** by the fragment (`merge-settings.py:33`), the
allow-list is **unioned** (`:38`), and `env` + `deny` survive untouched (the stated
contract at `merge-settings.py:3-6`). Deterministic. **This is the single cheapest
high-value test in the repo** — pure function, mutates the user's real config, zero
coverage today.

<a name="test-06"></a>**TEST-06 — install dry-run snapshot, per provider.** Run
`providers/{claude,cursor}/install.sh` with `DRY_RUN=1` and snapshot the planned
actions (the `[dry-run]` log lines). Assert the expected set of writes/symlinks per
provider (skills symlink, CLAUDE.md, mcp merge, settings merge for claude;
skills/mcp/rules/hooks/principles for cursor). Catches an accidentally dropped install
step. Deterministic.

<a name="test-07"></a>**TEST-07 — CLAUDE.md / .mdc render golden.** `install_claude_md`
(`providers/claude/install.sh:33`) concatenates stub + AGENTS.md + every principle +
every user-rule; the cursor side renders each principle to an `alwaysApply` `.mdc`
(`providers/cursor/install.sh:73`). Render into a temp `$HOME` and assert each
principle and user-rule appears exactly once, in order, with the right frontmatter.
Deterministic. Guards silent drift where a new principle file stops being rendered.

### 3.4 Plan: the **end-to-end "together" eval** (the headline harness)

<a name="test-08"></a>**TEST-08 — full-toolset vs bare-agent E2E (value-style A/B).**
This is the harness that directly answers the owner's question. It is the **only** one
that exercises the tools *together*.

- **Design:** pick 3–5 realistic multi-step tasks that *naturally* touch several
  layers — e.g. *"In this Go repo, change the `Repository.Save` signature and report
  every caller; then run the build and confirm it passes."* That single task should
  pull in GitNexus (impact), ast-grep (find call sites), rtk/lean-ctx (run build with
  compressed output), and verification-before-completion (don't claim green without
  output).
- **Arms:** **treatment** = full real config (skills + hook + MCP). **control** = the
  `config-dir` isolation already built (`render_config.py:54`) extended to also
  disable the hook and MCP servers, so the control agent has *only* native tools.
- **Measure (three numbers, all already cheap to capture):**
  1. **Success** — pairwise judge on task completion (reuse `judge_pairwise`).
  2. **Tool-call count** and **transcript size** — free from `agent.metrics`
     (`agent.py:74`).
  3. **Token usage** — see TEST-12; the stream-json `result` event carries usage.
- **Reuse:** this is the existing value track with (a) a harder multi-tool prompt and
  (b) a control arm that strips the *whole* toolset, not one skill. Minimal new code.
- **Cost:** LLM-judged, so local-only, N=3. The expensive eval — but it is *the* one
  that proves the thesis, so it earns its cost.
- **Definition of "works together" (falsifiable):** treatment completes the task in
  **fewer tool calls and fewer tokens** while the judge rates it **not worse** on
  correctness. If treatment is *more* expensive without being better, the toolset is
  *not* complementing — exactly the failure this repo should be able to detect.

---

## 4. North-star measurement gap

> The north-star is three claims: **(a) fewer tokens / less context pollution, (b) a
> weak agent (Haiku) made dramatically better, (c) the toolset works together.** Today:
> (a) is **proxied** but not measured end-to-end, (b) is **not measured at all**, (c)
> is covered by TEST-08 above.

### 4.1 What today's harness actually measures vs the claim

- **Token reduction — partial.** `bench.py` proves each *tool's* output is smaller
  (×4,884 for `rtk` grep, `BENCHMARKS.md:25`). That is a real, honest, deterministic
  number — but it measures the **transform in isolation on a synthetic 200k-line
  fixture**, not the tokens an *agent* spends on a *real task*. The leap from "this
  command's output is 99% smaller" to "the agent's context bill drops" is **inferred,
  not shown**.
- **Context pollution — not measured.** No harness captures context-window occupancy
  or how much irrelevant material lands in the agent's working set. `transcript_chars`
  (`agent.py:95`) is a crude proxy and is not reported as a north-star metric.
- **Weak-agent (Haiku) uplift — not measured at all.** The value track is
  *parameterized* by `--model` (`run.py:127`) and records per-model
  (`run.py:63`), so the *capability* exists — but the only recorded run is on
  `claude-opus-4-8` (`results/claude-opus-4-8/…`, `BENCHMARKS.md:11`). There is **no
  Haiku run and no harness that frames the weak-model uplift as a metric.** This is the
  single most under-delivered north-star claim.

### 4.2 Plan: concrete north-star value-evals

<a name="test-09-haiku"></a>**TEST-10 — Haiku-uplift suite (the headline north-star
eval).**
Run a fixed task suite **on Haiku** in two arms — full toolset vs bare — and report
the **success-delta** and **token-delta**.

- **Shape:** reuse the TEST-08 harness and prompts; pin `--model claude-haiku-*` for
  both arms. Add a *second* arm pair on a strong model (Opus) so the table shows
  "uplift on weak vs strong" side by side — the claim is that the toolset closes the
  gap *more* for the weak model.
- **Report:** a new `BENCHMARKS.md` section, *"Weak-agent uplift,"* with columns
  `task | model | success (treat/control) | token Δ | tool-call Δ`. `report.py`
  already rolls per-model results (`report.py:23`); extend its renderer.
- **Falsifiable claim:** *"On Haiku, the full toolset yields ≥X% higher task-success
  and ≥Y% fewer tokens than bare Haiku, and the success uplift exceeds the uplift seen
  on Opus."* If Haiku-with-tools is no better than Haiku-bare, the north-star is false
  and this catches it.
- **Cost:** LLM-judged, local-only. Haiku calls are cheap, which *helps* — the weak
  model is also the cheap model, so this suite is far less costly than an Opus suite.

<a name="test-11"></a>**TEST-11 — end-to-end token-delta metric (deterministic capture,
LLM to generate).**
The agent transcript's terminal `{"type":"result"}` event carries token usage
(input/output/cache). `agent.final_text` already parses that event
(`agent.py:55`); add a sibling `agent.usage(raw)` that extracts the usage block.
Then **every** value/E2E run reports a real **token delta** for free — turning the
"context savings" claim from inferred into measured. Deterministic parsing; no extra
model calls. *(If the metric reveals a bug in how usage is summed, that's plans/03.)*

<a name="test-12"></a>**TEST-12 — keep the synthetic bench, label it honestly.**
The `bench.py` compression numbers are valuable as an **upper bound** ("the transform
*can* save this much"). Keep them, but in `BENCHMARKS.md` distinguish *transform-level*
savings (bench) from *task-level* savings (TEST-11). No new harness — a documentation/
framing fix so the north-star table isn't read as proven by the synthetic number. Low
effort, prevents over-claiming (honesty principle).

### 4.3 Cost discipline (the owner is token-conscious)

- Push everything possible to **deterministic** (TEST-01..07, TEST-11): hook, merge,
  render, token-parse. These are free and CI-safe.
- Reserve **LLM-judged** evals for the two questions only a judge can answer:
  *did it work together* (TEST-08) and *did the weak model get better* (TEST-10).
- Prefer **Haiku** as both the judge *and* the subject where variance allows — cheap,
  and self-consistent for the uplift comparison.

---

## 5. CI & regression-protection assessment

### 5.1 Observed state

- **No GitHub Actions workflow exists.** `find .github -type f` → empty. The
  `README.md:86` ("CI on every PR") and `PLAYBOOK.md:202` claims are **not backed by a
  workflow file**. (The prompt's note that `ci.yml` is "untracked" overstates it —
  it is *absent*, not merely untracked.) **Inference:** today a regression is caught
  only if a human remembers to run `bin/ci-check.sh` locally.
- `bin/ci-check.sh` is well-built and *ready* to be a gate (it already runs lint +
  selftest + a dry-run parse), but nothing invokes it automatically.
- The deterministic harnesses that *would* catch the highest-leverage regressions
  (hook, merge) **don't exist yet** (§2.1), so even a wired-up CI would not catch a
  broken hook today.

### 5.2 Would a behavior regression be caught? (honest answer: mostly no)

| Regression | Caught today? | By what (after this plan) |
|---|---|---|
| Someone breaks `shell-guard.sh` branch-3 (rtk stops applying) | **No** | TEST-01 (CI) |
| Hook starts double-wrapping | **No** | TEST-01 (CI) |
| `merge-settings.py` clobbers the user's `env` | **No** | TEST-05 (CI) |
| A new principle stops rendering into CLAUDE.md | **No** | TEST-07 (CI) |
| A skill's description regresses so it stops triggering | Only if conformance is run manually | conformance + CI-wiring (TEST-13) |
| ast-grep loses its precision edge | Only if `bench.py` run manually | bench + manual |
| Toolset stops complementing (more tokens, no better) | **No** | TEST-08/TEST-10 (manual) |

### 5.3 Plan

<a name="test-13"></a>**TEST-13 — add `.github/workflows/ci.yml`.** Run
`bin/ci-check.sh` on every PR (it is already self-contained and zero-token). Add the
new deterministic tests (TEST-01, 02, 04–07, 11) into `ci-check.sh` so they ride the
same gate. **Explicitly keep token-spending tracks (conformance, value, E2E, Haiku)
out of PR CI** — run them manually / on a schedule, per the existing PLAYBOOK stance
(`PLAYBOOK.md:20`). Effort S; **this is the force-multiplier** — without it, every
other test in this plan only fires when someone remembers.

<a name="test-14"></a>**TEST-14 — judge variance control.** Today a value verdict is
N=3 with a single flip-pair per run (`run.py:76`, `judge.py:96`); variance beyond
position-bias is unmanaged. For the headline evals (TEST-08/10) add **multi-sample
judging** (e.g. 3 judge samples per ordering, majority vote) and report the judge's
self-agreement rate alongside flip-rate. Keeps the UNRELIABLE gate honest when the
stakes (north-star claims) are highest. Cost: more judge calls on the two flagship
evals only.

---

## 6. Test requirements handed to the Go `agentic` binary (→ plans/01)

The planned Go `agentic` binary (design owned by **plans/01**) will replace the bash
install/merge layer. Its job is exactly the deterministic, mutate-the-user's-config
work that is **least covered today** — so it must ship with the tests this plan
specifies for the bash equivalents, plus binary-specific ones. **Handing these
requirements to doc 01:**

1. **Golden-file merge tests (table-driven).** Port TEST-04/05 as Go table tests:
   given `(existing config, fragments)` → assert exact merged output. Must cover the
   preservation contracts (work-only MCP servers; machine-local `env`; existing
   `deny`). Deterministic.
2. **Hook precedence-table test.** Port TEST-01 as a Go test of the binary's hook
   logic (if the binary subsumes `shell-guard.sh`): the same input→envelope table,
   including the heredoc/already-wrapped passthroughs and the malformed-input safety.
   This is the binary's highest-leverage test.
3. **Dry-run snapshot tests.** `agentic install --dry-run --provider {claude,cursor}`
   must emit a stable, asserted plan (port TEST-06). Snapshot-test the plan.
4. **Idempotency test.** Running install twice produces no diff on the second run and
   leaves exactly one backup — the gap TEST-08-idempotency flags for bash, but trivial
   to assert for a binary.
5. **Cross-platform build/smoke test.** `go test ./...` in CI on macOS **and** Linux
   (the CI runner is Linux and currently can't exercise the bash install meaningfully).
   A binary makes the install path *finally testable in CI* — call this out to 01 as a
   primary motivation, not a side benefit.
6. **`$HOME`-fixture install test.** Point the binary at a temp `$HOME` and assert the
   resulting tree (symlinks, rendered files). This is where doc 04's portability
   scenarios plug in (§7).

> Cross-link: 01 owns *how* the binary is built; this section owns *what coverage it
> must carry*. The merge/hook/render golden fixtures (TEST-04/05/07) should be authored
> **provider-agnostic** so they are reused verbatim by both the bash tests now and the
> Go tests later — write them once.

---

## 7. Portability test scenarios (← plans/04)

**plans/04** owns portability; it will hand over concrete scenarios. I reserve a slot
to fold them into the harness. Expected scenarios (to confirm with 04):

<a name="test-09"></a>**TEST-09 — install onto a fixture `$HOME` with pre-existing
state.** Stand up a temp `$HOME` containing a **hand-written `CLAUDE.md`**, an existing
`~/.claude/settings.json` with a local `env`, an existing `~/.claude/skills`
*directory* (not a symlink), and an existing `mcp.json` with a work-only server. Run
the real install (bash today, binary later) and assert: existing `CLAUDE.md` is backed
up (`install.sh:41-43`), the skills dir is backed up before symlinking
(`install.sh:23-27`), `env`/work-server survive (TEST-04/05 contracts), and no real
`$HOME` is touched. Deterministic. This is the integration test that proves the
install is **safe on a populated machine**, not just a clean one — and it composes
TEST-04..07 into one realistic flow.

Other likely 04 hand-offs to slot here: missing-binary degradation (no `rtk`/lean-ctx
→ hook branch-3 still safe, doctor warns not fails), and a non-macOS run of
`bootstrap.sh` (should warn-and-exit, `bootstrap.sh:21-26`).

---

## 8. Prioritized backlog

Severity/leverage: **★★★** north-star-critical or silent-regression risk · **★★**
real gap · **★** polish. Effort: S < 1h-ish, M a few hours, L a day+.

| ID | Title | Leverage | Effort | Det / LLM | Depends on |
|---|---|---|---|---|---|
| [TEST-13](#test-13) | Add `.github/workflows/ci.yml` running `ci-check.sh` | ★★★ | S | Det | — |
| [TEST-01](#test-01) | shell-guard golden-envelope tests (3 branches + guards) | ★★★ | M | Det | TEST-13 (to gate) |
| [TEST-05](#test-05) | merge-settings golden test (env/deny preserved) | ★★★ | S | Det | — |
| [TEST-04](#test-04) | merge-mcp golden test (work-server preserved) | ★★ | S | Det | — |
| [TEST-08](#test-08) | Full-toolset vs bare-agent E2E A/B ("works together") | ★★★ | L | LLM | TEST-11 |
| [TEST-10](#test-09-haiku) | Haiku-uplift suite (success-Δ + token-Δ, weak vs strong) | ★★★ | L | LLM | TEST-08, TEST-11 |
| [TEST-11](#test-11) | End-to-end token-delta capture (`agent.usage`) | ★★★ | S | Det | — |
| [TEST-02](#test-02) | lean-ctx stub for hook branch-2 | ★★ | S | Det | TEST-01 |
| [TEST-07](#test-07) | CLAUDE.md / `.mdc` render golden | ★★ | M | Det | — |
| [TEST-06](#test-06) | install dry-run snapshot per provider | ★★ | S | Det | — |
| [TEST-09](#test-09) | Install onto populated fixture `$HOME` (with plans/04) | ★★ | M | Det | TEST-04/05/07; plans/04 |
| [TEST-14](#test-14) | Judge multi-sample variance control (flagship evals) | ★★ | M | LLM | TEST-08 |
| [TEST-03](#test-03) | Precedence-overlap conformance case | ★ | S | LLM | — |
| [TEST-12](#test-12) | Label transform-level vs task-level savings in BENCHMARKS | ★ | S | Det | TEST-11 |
| — | Value cases for the 6 skills with conformance-only coverage | ★ | M | LLM | — |
| — | One conformance case each for honesty / karpathy principles | ★ | S | LLM | — |

**Suggested order:** TEST-13 → TEST-01/04/05/11 (cheap, deterministic, CI-gated,
close the silent-regression holes) → TEST-08 → TEST-10 (the two flagship north-star
evals) → the rest.

---

## 9. Cross-document dependencies (for the master plan)

- **→ plans/01 (Go binary):** §6 hands over six test requirements; author merge/hook/
  render golden fixtures provider-agnostic so bash-now and Go-later share them.
- **→ plans/03 (gaps & bugs):** the shell-guard branch-1 over-trigger on code
  extensions in the *pattern* (`shell-guard.sh:53-55`, reproduced during this review),
  the unrestored `_judge_once` monkeypatch (`selftest.py:31`), and any usage-summing
  bug surfaced by TEST-11 are 03's to fix; TEST-01/11 encode the intended behavior as
  their targets.
- **→ plans/02 (maturity):** the matrix in §2 and the regression table in §5.2 are the
  evidence base for the grade; verdict is 02's.
- **← plans/04 (portability):** TEST-09 reserves the slot for 04's `$HOME`-fixture and
  missing-binary scenarios.
- **Self-contained note:** the existing harness is genuinely good *per tool* — the work
  is not a rewrite but adding the **integration, hook, golden, and north-star** layers
  on top, most of them deterministic and CI-cheap.

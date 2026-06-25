# Eval playbook — the loop for proving a tool is worth its place

A skill, rule, or tool in this repo earns its place only by **provably changing
agent behavior for the better**. This playbook is the loop that keeps that true as
the repo grows: every artifact added under `core/` ships with the evals that defend
it, and `evals/lint.py` fails the build if it doesn't.

The discipline is the one Anthropic, OpenAI, and Cursor all put at the center of
agent work: iterate against measurements, not impressions. Cursor states it
plainly — add a rule only when you observe the agent making the same mistake
repeatedly, and keep the rule only as long as a benchmark shows it helps.

## The two tracks

| | Conformance | Value |
|---|---|---|
| Question | Does the rule change behavior / does the skill trigger when it should? | Does the artifact make the **outcome** better or cheaper? |
| Method | One transcript, judged PASS/FAIL against `expect` / `expect_not` | A/B: same prompt **with** the artifact (treatment) vs **without** it (control), pairwise judge |
| Cost | One agent run + one judge | 2 arms × N + 2 judges per run (order-swapped) |
| Where it runs | Can be cheap enough for manual CI; still token-spending | Manual / local only — never in PR CI |
| Lives in | `conformance/cases/*.json` | `value/cases/*.json` |

Conformance answers "did the wiring work". Value answers "was the wiring worth
it". A skill can pass conformance (it fires) and still fail value (firing didn't
help) — that is exactly the signal this repo exists to catch.

## Definition of done for a new skill / rule / tool

A PR that adds an artifact under `core/` is **not complete** until it adds:

1. **≥1 conformance case** proving the artifact changes behavior — and, for a
   skill, a **negative** case proving it does *not* over-trigger on unrelated
   prompts (`expect_not`, empty `expect`).
2. **≥1 value case** stating a falsifiable hypothesis and an A/B that an agent
   run can settle.

`evals/lint.py` enforces coverage mechanically: every directory under
`core/skills/` must be named by at least one case (a conformance case names its
skill in the `rule` text — the repo convention — or a value case in its `skill`
field). A skill with no eval is an undefended claim and fails CI. The only exempt
skill is `no-mistakes` (tool-generated, gitignored).

## Which case do I write?

```
Adding/Changing an artifact in core/
        │
        ├─ Does it change WHETHER the agent does something
        │  (a behavior, a trigger)?            → conformance case (+ negative guard)
        │
        └─ Does it change HOW GOOD or HOW CHEAP
           the outcome is?                     → value case (A/B)
```

Most artifacts want both: one conformance case that it fires, one value case that
firing pays off.

## Where a case comes from (do not invent synthetic tasks)

Following CursorBench: a case is born from a **real weakness you observed** — a
task where the agent, without the tool, did the wrong or wasteful thing. Capture
that exact task as the case `prompt`. A prompt invented to flatter the tool proves
nothing; a prompt that reproduces a real failure proves the tool fixes it.

## Templates

### Conformance case

```json
{
  "id": "short-kebab-id",
  "rule": "which default this guards — name the skill in this text for coverage",
  "prompt": "the message sent to the agent",
  "expect": ["behavior the agent SHOULD exhibit"],
  "expect_not": ["behavior the agent must NOT exhibit"]
}
```

A negative (over-trigger guard) case sets `expect: []` and puts the unwanted
behavior in `expect_not`.

### Value case

```json
{
  "id": "short-kebab-id",
  "skill": "exact-skill-dir-name",
  "hypothesis": "what the artifact is supposed to improve, falsifiably",
  "prompt": "a task that reproduces a real weakness the tool addresses",
  "ablate": ["exact-skill-dir-name"],
  "rubric": ["what a good outcome looks like", "one checkable property per line"],
  "pass_condition": "treatment_preferred",
  "n": 3
}
```

`pass_condition`:
- `treatment_preferred` — the judge must prefer the treatment arm (use when the
  tool is meant to improve quality/correctness).
- `treatment_not_worse` — treatment must not lose on quality; pair it with the
  efficiency metrics (tool-call delta) when the tool's payoff is economy, not
  quality (e.g. `terminal-rtk`).

## Case review checklist

- [ ] One assertion per behavior, so a failure points at exactly one cause.
- [ ] The prompt genuinely exercises the tool (a control-arm agent would plausibly
      do worse).
- [ ] The rubric is checkable from a transcript, not a matter of taste.
- [ ] (Value) `ablate` names the real artifact whose contribution is being measured.
- [ ] (Value) the hypothesis is falsifiable — it could come back FAIL.

## Reading verdicts honestly (judge biases)

LLM judges are biased — they favor the first option (position bias), longer
answers (verbosity bias), and their own model family (self-preference). We counter
the first directly: every pairwise comparison runs in **both orders** and we
report the **flip rate**. A flip rate above `FLIP_THRESHOLD` (10%) means the
verdict is order-dependent and is stamped **UNRELIABLE** — treat it as no signal,
not a pass. When verdicts come back UNRELIABLE repeatedly, that is the cue for
**human grading**: read the two transcripts yourself.

Isolation confidence is also stamped on every value result:
- **high** — `config-dir` strategy: the control arm physically lacks the skill.
  Requires env-based auth (`ANTHROPIC_API_KEY`), set `AGENTIC_EVAL_ISOLATION=config-dir`.
- **medium** — `prompt` strategy (default): both arms share the real config and
  the control arm is *instructed* to ignore the artifact. Portable, but leakier.
  Used automatically when auth is OAuth/Keychain, because relocating the config
  dir there breaks authentication.

## Versioning the set

When the case mix changes materially, bump `EVAL_SET_VERSION` in
[`report.py`](report.py). Compare benchmark numbers only **within** one version —
across versions the task distribution differs and the numbers are not comparable
(the CursorBench rule).

## Running

```bash
# Dry (default) — prints what would run, executes nothing:
python3 evals/run.py --track all

# Conformance (token-spending; run from a throwaway scratch repo):
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track conformance

# Value A/B for one tool under a specific model:
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track value --filter rtk --model claude-opus-4-8

# Refresh the committed summary:
python3 evals/report.py        # → evals/BENCHMARKS.md
```

Static, zero-token checks (run in CI on every PR via `bin/ci-check.sh`):

```bash
python3 evals/lint.py          # schema, unique ids, ablate targets, skill coverage
python3 evals/selftest.py      # harness logic (pairwise mapping, verdict thresholds)
```

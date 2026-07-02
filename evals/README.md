# Evals

A skill or rule in this repo is worth only as much as it provably changes agent
behavior **for the better**. These evals turn each artifact under `core/` into a
runnable, re-runnable assertion — the discipline Anthropic ("Building Effective
Agents"), OpenAI ("A Practical Guide to Building Agents"), and Cursor (CursorBench)
all put at the center of agent work: iterate against measurements, not impressions.

The loop for adding and maintaining cases lives in **[PLAYBOOK.md](PLAYBOOK.md)**.
Measured results live in **[BENCHMARKS.md](BENCHMARKS.md)** (generated, per model).

## Two tracks

- **Conformance** ([`conformance/cases/`](conformance/cases/)) — does a rule change
  behavior, and does a skill trigger when it should (and stay quiet when it
  shouldn't)? One transcript, graded PASS/FAIL by an LLM judge against
  `expect` / `expect_not`.
- **Value** ([`value/cases/`](value/cases/)) — does the artifact make the *outcome*
  better or cheaper? An A/B: the same prompt is run **with** the artifact
  (treatment) and **without** it (control), and a pairwise judge picks the better
  transcript. This is the part that proves a tool is *worth its place*, not just
  that it fires.

## How it works

1. Cases are JSON specs (schemas and templates in [PLAYBOOK.md](PLAYBOOK.md)).
2. [`run.py`](run.py) sends each prompt to the agent headless (`claude -p`),
   capturing the transcript **including tool calls**.
   - Conformance: one run, judged PASS/FAIL/ERROR.
   - Value: treatment and control arms, judged **pairwise in both orders** to
     control for the judge's position bias. The **flip rate** across orders is
     reported; above 10% the verdict is stamped `UNRELIABLE`. Efficiency metrics
     (tool-call count, transcript size) are captured for free from each transcript.
   - A failed launch (`result_error` — auth error, timeout, no result event) is
     detected before judging and recorded as **ERROR**, never judged as data; if
     the very first case/run of the whole suite errors, the run aborts early
     instead of grinding through a suite of phantom results. Judging itself is
     **fail-closed**: unparseable judge output is also ERROR, never a silent
     PASS/TIE — see PLAYBOOK's
     [Reading verdicts honestly](PLAYBOOK.md#reading-verdicts-honestly-judge-biases).
3. Both arms' transcripts and the judge's raw replies are persisted to
   `results/<model>/transcripts/` (gitignored) — see
   [Re-judging without re-spending tokens](#re-judging-without-re-spending-tokens).
4. Value results are written per model to `results/<model>/` (gitignored);
   [`report.py`](report.py) rolls them into the committed [BENCHMARKS.md](BENCHMARKS.md).
   `report.py` refuses to shrink that file: if the fresh `results/` scan on this
   machine has fewer (or zero) value rows than what's already committed, it exits
   nonzero and writes nothing rather than overwrite real history with an empty
   table (pass `--force` if the shrink is intentional). Rows for a (case, model)
   pair with no fresh result on this machine are carried forward from the
   committed file.

The harness is agent-agnostic — the agent is the `AGENTIC_EVAL_AGENT_CMD` string,
so a Cursor or other headless CLI can be swapped in. Today it is exercised with
`claude -p`.

## Running

Evals spend tokens and the agent may take actions, so they are **dry by default**.
Run real evals from a throwaway scratch repo so a misbehaving case cannot touch
real work.

```bash
# Dry run — prints what would be sent, runs nothing. --track all covers
# conformance + value + metric cases:
python3 evals/run.py --track all

# Conformance, for real (--model is honored here too):
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track conformance --model claude-opus-4-8

# Value A/B for one tool, under a chosen model (records to results/<model>/):
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track value --filter rtk --model claude-opus-4-8

# Refresh the committed summary table:
python3 evals/report.py
```

`--n` (default 3) sets the value track's repeat count; a case's own `"n"` field
in its JSON overrides the CLI default when present, so a case that specifically
wants 5 repeats gets 5 even if `--n` isn't passed.

Override the agent/judge command if your CLI differs:

```bash
AGENTIC_EVAL_AGENT_CMD='claude -p' AGENTIC_EVAL_JUDGE_CMD='claude -p' \
  AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py --track value
```

### Re-judging without re-spending tokens

Every case run persists both arms' transcripts and the judge's raw reply to
`results/<model>/transcripts/<case>-<timestamp>-{transcript,judge,on,off}.txt`,
with their paths recorded in the result JSON. That means a verdict can be
re-checked or a judge prompt/rubric re-tuned without re-invoking the agent:

```bash
python3 evals/run.py --rejudge evals/results/<model>/<timestamp>-<case-id>.jsonl
```

Only judge tokens are spent on a re-judge — the (usually much larger) agent
run is not repeated.

### Arm isolation for value A/B

The control arm must run the same prompt with the artifact removed. Two strategies,
chosen automatically (details in [PLAYBOOK.md](PLAYBOOK.md#reading-verdicts-honestly-judge-biases)):

- **config-dir** (high confidence) — renders a genuinely bare `CLAUDE_CONFIG_DIR`:
  hooks stripped, the repo-managed permission allow-list removed, `CLAUDE.md`
  empty, no MCP servers, and the skill physically absent. Needs env-based auth
  (`ANTHROPIC_API_KEY`); opt in with `AGENTIC_EVAL_ISOLATION=config-dir`.
- **prompt** (medium confidence, default) — both arms share the real config and the
  control arm is instructed to ignore the artifact; it still runs under any
  globally-installed hooks, so a hook-enforced behavior looks the same in both
  arms. Used automatically under OAuth/Keychain auth, where relocating the config
  dir breaks authentication.

## Static checks (zero tokens, CI on every PR)

```bash
python3 evals/lint.py        # schema, unique ids, ablate targets exist, skill coverage
python3 evals/selftest.py    # harness logic (pairwise order-swap, verdict thresholds)
```

`lint.py` is what mechanically enforces the loop: every skill under `core/skills/`
must be covered by at least one case, or the build fails. Both run inside
[`bin/ci-check.sh`](../bin/ci-check.sh).

## Adding a case

See **[PLAYBOOK.md](PLAYBOOK.md)** — it has the definition of done, the
decision tree for which track to use, the JSON templates, and the review checklist.
Keep one assertion per behavior so a failure points at exactly one cause. Trigger
and outcome matching are probabilistic — run several times and look at stability,
not a single pass.

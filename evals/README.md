# Evals

A rule in this repo is worth only as much as it provably changes agent behavior.
These evals turn each global default in [`core/instructions/AGENTS.md`](../core/instructions/AGENTS.md)
into a behavioral assertion you can run headless and re-run as a regression check.

This is the discipline both Anthropic ("Building Effective Agents") and OpenAI
("A Practical Guide to Building Agents") put at the center of agent work: iterate
against measurements, not impressions.

## How it works

1. Each case in [`cases/`](cases/) is a JSON spec: an `id`, the `rule` it guards, a
   `prompt` to send to the agent, and an `expect` list of behaviors a judge must
   confirm (or `expect_not` for things the agent must *not* do).
2. [`run.py`](run.py) sends each prompt to the agent headless (`claude -p`), captures
   the transcript **including tool calls**, then asks an LLM judge to score the
   transcript against `expect` / `expect_not`.
3. It tallies pass/fail and exits non-zero on any failure (CI-friendly).

## Running

Evals spend tokens and the agent may take actions, so they are **dry by default**.

```bash
# Dry run — prints what would be sent, runs nothing:
python3 evals/run.py

# Real run — set the confirmation flag, and run from a throwaway scratch repo
# so a misbehaving case cannot touch real work:
AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py
```

Override the agent command if your CLI differs:

```bash
AGENTIC_EVAL_AGENT_CMD='claude -p' AGENTIC_EVAL_JUDGE_CMD='claude -p' \
  AGENTIC_EVAL_CONFIRM=1 python3 evals/run.py
```

## Adding a case

Drop a new JSON file in [`cases/`](cases/):

```json
{
  "id": "short-kebab-id",
  "rule": "which global default this guards",
  "prompt": "the message sent to the agent",
  "expect": ["behavior the agent SHOULD exhibit"],
  "expect_not": ["behavior the agent must NOT exhibit"]
}
```

Keep one assertion per behavior so a failure points at exactly one rule.

## Skill-trigger cases

To test that a skill fires when it should — and stays quiet when it shouldn't —
write paired cases. A **positive** case asserts the skill is used
(`expect: ["surfaces or invokes the <skill> skill"]`); a **negative** case guards
against over-triggering on unrelated prompts
(`expect_not: ["invokes the <skill> skill"]`, with an empty `expect`). The judge
reads the transcript, which includes tool calls, to decide. Trigger matching is
probabilistic — run these several times and look at stability, not a single pass.

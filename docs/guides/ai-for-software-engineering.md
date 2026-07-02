# Using AI for software engineering — a practitioner's playbook

A field guide to getting real engineering value out of AI coding agents (Claude Code,
Cursor, Codex, Gemini CLI) without the two failure modes that waste the most time:
**under-specifying** (the agent guesses wrong and you pay to re-do it) and **over-trusting**
(plausible code that's subtly wrong ships to `main`).

The through-line: **you stay the engineer; the model is the fastest junior you've ever
had.** It's brilliant at typing, recall, and breadth, and unreliable at judgement, context,
and knowing when it's wrong. Design your workflow around that asymmetry.

> This pairs with the repo's machinery: the [`model-orchestration`](../../core/skills/model-orchestration/SKILL.md)
> skill (tier the model to the task), [`prompt-caching-playbook`](../../core/skills/prompt-caching-playbook/SKILL.md)
> (cut cost), [`verification-before-completion`](../../core/skills/verification-before-completion/SKILL.md)
> (the trust gate), and the [`karpathy-guidelines`](../../core/principles/karpathy-guidelines.md) principle.

## The loop

```
spec → context → plan → small diff → verify → review → repeat
```

Most bad AI sessions skip straight to "small diff" from a one-line ask. The leverage is in
the first three steps and the last two.

## 1. Spec before you prompt

The single highest-return habit. A vague prompt ("make auth work") forces the model to
invent the spec — and it invents confidently. A tight prompt makes success checkable.

- State the **goal, the constraints, and the done-condition**. "Add a rate limiter" →
  "Add a per-IP rate limiter, 100 req/min, returning 429 with `Retry-After`; add a unit
  test for the limit boundary."
- Give it the **interfaces and examples** it should match, not prose descriptions of them.
- If there are multiple reasonable designs, **ask it to lay them out first** and pick —
  don't let it silently choose (see `karpathy-guidelines` §1).

Rule of thumb: if you can't write the success check in one sentence, the task isn't ready
to hand to an agent.

## 2. Engineer the context (this is where tokens are won or lost)

The model only knows what's in its window. Curating that window — "context engineering" —
matters more than prompt wording.

- **Use a rules/instructions file.** `AGENTS.md` / `CLAUDE.md` / `.cursor/rules` carry your
  conventions so you don't restate them every turn. This is exactly what this repo renders.
  Keep it short — a bloated file gets *ignored*, not obeyed (Anthropic, see below).
- **Retrieve, don't stuff.** Pull the *relevant* code with structural/search tools
  (GitNexus, `ast-grep`) instead of pasting whole files. Less context = cheaper, faster,
  and *more accurate* (irrelevant context degrades output).
- **Keep the stable prefix stable** so the prompt cache hits — reordering your system/
  instructions each turn silently re-bills the whole prefix (`prompt-caching-playbook`).
- **Start fresh when the thread rots.** A long, meandering context is worse and pricier
  than a clean one with a crisp summary. Compact or restart.

## 3. Route the model to the task

Match model tier to task weight — don't pay frontier prices for mechanical work, and don't
send architecture decisions to the cheap tier.

| Task | Tier |
|------|------|
| Decompose an ambiguous feature; review a risky diff; hard debugging | **Strong** (Opus / GPT-5 / Gemini Pro) |
| Most day-to-day coding with a clear spec | **Mid** (Sonnet / mini / Flash) |
| Renames, boilerplate, formatting, extraction, search, file summaries | **Cheap** (Haiku / nano / Flash-Lite) |

The high-leverage pattern: **plan with a strong model, delegate well-specified sub-tasks to
a cheaper one (or subagents), verify, escalate only on failure.** Full policy in the
[`model-orchestration`](../../core/skills/model-orchestration/SKILL.md) skill — Google's own
guidance converges on the same shape (see below).

## 4. Small, verifiable diffs — with a test loop

Big AI diffs are where bugs hide and review dies. Keep changes small enough to actually
read, and give the agent an automatic way to know it's right.

- Prefer **test-first**: "write a failing test that reproduces this, then make it pass."
  A strong success criterion lets the agent loop itself to green instead of pinging you
  (OpenAI's Codex guidance frames test-check-review as one loop; see below).
- One concern per diff. Land it, then move on — don't let the agent "improve" adjacent code
  (`karpathy-guidelines` §3, surgical changes).
- Run the build/tests/linters in the loop, not at the end.
- **Make state legible to the agent, not just to you.** Log generously so the agent can
  self-diagnose, and keep permission checks where the model can actually see them, rather
  than buried in middleware it never reads (Armin Ronacher; see below).

## 5. Review AI output like a junior's PR — because it is one

This is the trust boundary. The model's confidence is uncorrelated with its correctness —
Karpathy's framing of the moment: "right now the agents are like interns. You still have to
be in charge of aesthetics, judgment, taste, and oversight" (see below).

- **Read every line you ship.** "It ran" ≠ "it's correct." Unreviewed AI code is technical
  debt you haven't met yet. Anthropic names this failure mode directly as the
  "trust-then-verify gap," fixed with one rule: "if you can't verify it, don't ship it."
- Look hardest at the things models get wrong: **hallucinated APIs/params**, off-by-one and
  boundary conditions, error handling, auth/permission checks, and **silent scope creep**.
- Make the agent **show its evidence** — the command it ran and the actual output — before
  it claims done (`verification-before-completion`). "Tests pass" with no transcript is a
  claim, not a fact.
- **Set a review-capacity budget, not just a diff-size one.** Velocity without review
  capacity is how a codebase outgrows anyone's understanding of it (Simon Willison; see below).

## 6. Guard against the known failure modes

- **Hallucinated dependencies.** Models invent plausible package and function names. Verify
  imports resolve; beware "slopsquatting" (typo-package supply-chain attacks on invented
  names).
- **Prompt injection.** Treat any content the agent reads — issues, web pages, code
  comments, tool output — as untrusted. It can carry instructions. Never let an agent act
  on fetched content with credentials without a human gate. Simon Willison's **lethal
  trifecta** names exactly when this turns dangerous: private-data access + untrusted
  content + external communication, together (see below).
- **Confident wrongness.** Ask "how would you verify that?" rather than accepting the first
  answer. Make it cite the file/line.
- **Scope creep.** Diff against intent: every changed line should trace to the request.

## 7. When NOT to reach for the agent

- You don't yet understand the problem — AI will help you *avoid* understanding it, which is
  a trap. Think first, then accelerate.
- Tiny edits you can make faster by hand than by prompting.
- Security-, money-, or migration-critical changes where you can't fully review the output.
- Anything where a confident wrong answer is expensive and hard to detect.

## Token-economy quick wins (cheaper *and* usually better)

1. Tier the model (§3) — most edits don't need the frontier.
2. Cache the stable prefix; don't reshuffle instructions each turn.
3. Retrieve relevant code; don't paste whole files.
4. Isolate sub-tasks in subagents so intermediate reads don't bloat the main context.
5. Write less code — the cheapest tokens are the ones never generated. Enforce a do-less
   ladder (the `ponytail` plugin in [`catalog/plugins.yaml`](../../catalog/plugins.yaml)).

## What the professionals converge on

Independent practitioners keep landing on the same handful of rules. In their own words:

- **You're still the engineer.** "The agents are like interns. You still have to be in
  charge of aesthetics, judgment, taste, and oversight." — Karpathy, [*AI Ascent 2026*](https://karpathy.bearblog.dev/sequoia-ascent-2026/).
- **Plan before you let it run.** "Spending extra time to build and revise an execution
  plan generally gives you better code output on complex tasks." — Google Cloud, [*Five best practices*](https://cloud.google.com/blog/topics/developers-practitioners/five-best-practices-for-using-ai-coding-assistants).
- **Give it a check it can run, or you become the check.** "It's the difference between a
  session you watch and one you walk away from." — Anthropic, [*Best practices*](https://code.claude.com/docs/en/best-practices).
- **Test-and-review is one loop, not two steps.** "Codex... can help test it, check it, and
  review it." — OpenAI, [*Codex best practices*](https://developers.openai.com/codex/learn/best-practices).
- **Bound velocity to review capacity.** "Set yourself limits on how much code you let the
  [agent] generate per day, in line with your ability to actually review." — Willison, [*slowing down*](https://simonwillison.net/2026/Mar/25/thoughts-on-slowing-the-fuck-down/).
- **Make your own mistakes un-repeatable.** Hashimoto's "harness engineering" — fix the
  docs/tools an agent's mistake exposed, not just the output. [*AI Adoption Journey*](https://mitchellh.com/writing/my-ai-adoption-journey).
- **Never combine the three dangerous capabilities.** Private-data access + untrusted
  content + external communication is the "lethal trifecta." — Willison, [*trifecta*](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents).

## Sources & further reading

- Anthropic — [*Building effective agents*](https://www.anthropic.com/engineering/building-effective-agents)
  and [*Best practices for Claude Code*](https://code.claude.com/docs/en/best-practices)
  ("give the agent a way to verify its own work"; explore → plan → implement → commit; keep
  instruction files short).
- Andrej Karpathy — [the original "vibe coding" note](https://x.com/karpathy/status/1886192184808149383):
  "fully give in to the vibes … forget that the code even exists" — explicitly scoped to
  throwaway projects, **not** production. Scaled up to real engineering practice in his
  [AI Ascent 2026 talk](https://karpathy.bearblog.dev/sequoia-ascent-2026/), which also seeds
  this repo's [`karpathy-guidelines`](../../core/principles/karpathy-guidelines.md) principle.
- Simon Willison — [*Not all AI-assisted programming is vibe coding*](https://simonwillison.net/2025/Mar/19/vibe-coding/):
  never commit AI code you couldn't explain. Plus [*slowing the fuck down*](https://simonwillison.net/2026/Mar/25/thoughts-on-slowing-the-fuck-down/)
  and [*the lethal trifecta*](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents) (quoted above).
- Armin Ronacher — [*Agentic Coding Recommendations*](https://lucumr.pocoo.org/2025/6/12/agentic-coding/)
  and Mitchell Hashimoto — [*My AI Adoption Journey*](https://mitchellh.com/writing/my-ai-adoption-journey) — quoted above.
- OpenAI — [*Codex best practices*](https://developers.openai.com/codex/learn/best-practices)
  and Google Cloud — [*Five best practices for AI coding assistants*](https://cloud.google.com/blog/topics/developers-practitioners/five-best-practices-for-using-ai-coding-assistants) — quoted above.
- Google / DORA — [2025 DORA report](https://dora.dev/dora-report-2025/): AI is an
  *amplifier* of existing engineering strengths and weaknesses, not an automatic win.
- Company-specific orchestration/token practices, cited and dated:
  [docs/research/ai-native-agentic-engineering.md](../research/ai-native-agentic-engineering.md).
- This repo's [`evals/BENCHMARKS.md`](../../evals/BENCHMARKS.md) — measured value of these levers per model.

*(Company-specific specifics are catalogued and dated in [`docs/research/ai-native-agentic-engineering.md`](../research/ai-native-agentic-engineering.md).)*

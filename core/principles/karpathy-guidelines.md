# Karpathy guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from
[Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876)
on LLM coding pitfalls. Adapted from
[multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) (MIT).

These bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think before coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop, name what's confusing, and ask.

## 2. Simplicity first

Minimum code that solves the problem — scope and over-engineering rules live in
coding-principles. Test: "Would a senior engineer call this overcomplicated?" If
yes, simplify.

## 3. Surgical changes

Touch only what you must; clean up only your own mess — see coding-principles.
Match existing style. Remove only what YOUR change orphaned. Test: every
changed line traces to the request.

## 4. Goal-driven execution

Define success criteria. Loop until verified.

- "Add validation" → "write tests for invalid inputs, then make them pass".
- "Fix the bug" → "write a test that reproduces it, then make it pass".
- "Refactor X" → "ensure tests pass before and after".

For multi-step tasks, state a brief plan with a verifiable check per step.
Strong success criteria let you loop independently; weak ones ("make it work")
force constant clarification.

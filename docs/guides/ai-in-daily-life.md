# Using AI in daily life — a practical guide

How to get durable value from AI assistants (Claude, ChatGPT, Gemini) outside of coding,
without the two traps that catch most people: **outsourcing your judgement** and
**trusting confident-sounding output that's wrong.**

The mindset that works: treat AI as a tireless, well-read **intern** — fast, broad, and
occasionally confidently mistaken. You delegate the legwork; you keep the judgement and the
final check.

## Pick the right tool for the job

| You want… | Reach for | Why |
|-----------|-----------|-----|
| A fact you can verify yourself | Search, or AI **with** sources shown | Plain chat can hallucinate facts |
| To think something through | A strong reasoning model | Worth the wait for hard questions |
| A quick rewrite / summary / draft | A fast, cheap model | Don't pay frontier prices for easy work |
| To actually *do* a task (book, file, fetch) | An agent / tool-connected assistant | Chat can only talk; agents can act |

Same tiering logic as engineering: **match the model to the difficulty.** Use the fast
model for the 80% of easy asks; save the deep model for genuinely hard reasoning. Most apps
default to the fast tier to save compute — Ethan Mollick's rule of thumb: "for anything high
stakes... usually switch to the powerful model" via the model selector
([*Using AI Right Now*](https://www.oneusefulthing.org/p/using-ai-right-now-a-quick-guide)).

## Research & summarization

- **Always ask for sources**, then click through. AI is a great *index into* reality, a poor
  *substitute for* it. The summary orients you; the source decides it.
- Use it to **break the blank page**: "give me the five things I should understand about X,
  and what I'm probably missing."
- For anything high-stakes (medical, legal, financial), AI is for **framing the questions**
  to ask a professional — not the answer.

## Writing & editing

- Best as a **drafting and critique partner**, not a ghostwriter. Draft yourself, ask it to
  red-team; or have it draft, then rewrite in your own voice. Output that's 100% AI usually
  reads like it.
- Give it your **constraints and audience** ("200 words, plain, for a skeptical manager"),
  and an example of your style. Specificity in = quality out.
- Use it to find **what's weak**: "what's the strongest objection to this argument?"

## Learning & tutoring

- AI is a patient 1:1 tutor — but learning requires *struggle it can short-circuit*. Use it
  to **explain, quiz, and check**, not to hand you answers you skip understanding.
- The **Feynman move**: explain the concept back to it in your own words and have it catch
  what you got wrong.
- Ask for **active recall**: "quiz me on this, one question at a time, and don't give the
  answer until I try."

## Decision support

- Have it lay out **options, trade-offs, and what you might be missing** — then *you* decide.
  Its job is to widen your view, not to choose. Push past the obvious: Mollick's advice is to
  "ask for 50 ideas instead of 10... then push the AI to expand on the things you like"
  (*Using AI Right Now*, above) — breadth first, then depth on what's actually good.
- **Red-team your plan**: "argue the other side," "what breaks this," "what would make me
  regret this in a year."
- Beware **sycophancy**: assistants tend to agree with you. Explicitly ask for disagreement.

## Planning, email & automation

- Turn a brain-dump into a **structured plan**: paste the mess, ask for a prioritized list
  with a first concrete step.
- Draft replies and summaries, but **read before you send** — tone and facts are yours to
  own.
- For recurring chores, **automation/agents** (scheduled tasks, connected tools) beat
  re-prompting by hand — but give anything that *acts* a review gate the first few runs.

## Literacy & safety — the habits that keep AI useful

- **Verify load-bearing facts.** Names, numbers, dates, quotes, citations, and anything
  legal/medical/financial. Models state fiction with the same confidence as fact.
- **Mind privacy.** Don't paste secrets, other people's personal data, or anything you
  wouldn't want retained. Assume inputs may be logged; use privacy controls where offered.
- **Don't over-trust or over-delegate.** Keep the skills you'd be helpless without. AI
  should *augment* your judgement, not replace it. Ethan Mollick calls this "making a
  conscious choice about AI use, rather than reflexive dependence or reflexive avoidance"
  ([*Choosing to Stay Human*](https://www.oneusefulthing.org/p/choosing-to-stay-human)).
- **Watch for prompt injection in the wild.** If an assistant browses or reads your files,
  malicious content can try to hijack it — be cautious granting it the ability to *act*.
  Simon Willison's **lethal trifecta**: private-data access + untrusted content + the
  ability to send data out, combined, is the dangerous pattern — any two alone are fine
  ([*The lethal trifecta for AI agents*](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents)).
- **Confident ≠ correct.** When it matters, ask "how sure are you, and how would I check?"

## A simple weekly routine

1. **Plan** — Monday: dump your week into a model, get a prioritized list.
2. **Delegate the legwork** — research, first drafts, summaries; verify the load-bearing bits.
3. **Learn one thing** — 20 minutes of tutored active recall on something you want to know.
4. **Review** — Friday: "here's what I did; what did I miss, and what should I drop?"

This is what Ethan Mollick means by "an era of managing AIs, rather than working with them":
the routine isn't a single chat, it's you directing several delegated threads and checking
their output ([*The Shape of the Thing*](https://www.oneusefulthing.org/p/the-shape-of-the-thing)).

## What the professionals converge on

- **Switch tiers deliberately.** "For anything high stakes... usually switch to the powerful
  model." — Ethan Mollick, [*Using AI Right Now*](https://www.oneusefulthing.org/p/using-ai-right-now-a-quick-guide).
- **Ask for more, then curate.** "Ask for 50 ideas instead of 10... then push the AI to
  expand on the things you like." — Mollick, *Using AI Right Now* (above).
- **Make AI use a choice, not a reflex.** "A conscious choice about AI use, rather than
  reflexive dependence or reflexive avoidance." — Mollick, [*Choosing to Stay Human*](https://www.oneusefulthing.org/p/choosing-to-stay-human).
- **You're managing AIs now, not just chatting with one.** "An era of managing AIs, rather
  than working with them." — Mollick, [*The Shape of the Thing*](https://www.oneusefulthing.org/p/the-shape-of-the-thing).
- **Never let one tool combine the three risky powers.** Private-data access + untrusted
  content + external communication is the "lethal trifecta" — avoid the combination, don't
  just trust guardrails. — Simon Willison, [*The lethal trifecta*](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents).
- **Sources over assertions.** Verify that cited sources actually exist and support the
  claim before you rely on them — institutional guidance converges here too (below).

## Sources & further reading

- Ethan Mollick — [*Using AI Right Now: A Quick Guide*](https://www.oneusefulthing.org/p/using-ai-right-now-a-quick-guide)
  and *Co-Intelligence*: pick one frontier model, pay for it, switch to its most powerful
  reasoning tier for anything high-stakes. Plus [*Choosing to Stay Human*](https://www.oneusefulthing.org/p/choosing-to-stay-human)
  and [*The Shape of the Thing*](https://www.oneusefulthing.org/p/the-shape-of-the-thing) — quoted above.
- Simon Willison ([simonwillison.net](https://simonwillison.net/)) — grounded, skeptical
  commentary on what these tools can and can't do, including [*the lethal trifecta*](https://simonw.substack.com/p/the-lethal-trifecta-for-ai-agents)
  (quoted above).
- University/institutional IT guidance (e.g. [UC Santa Cruz](https://its.ucsc.edu/get-support/it-guides/guide-use-artificial-intelligence-ai-safely/)) —
  never paste sensitive/confidential data into unlicensed public tools; verify that cited
  sources actually exist and support the claim.
- Research note: heavy, unstructured AI use is associated with **cognitive offloading** that
  can erode critical thinking and durable learning — a reason to keep AI in *tutor* mode, not
  *answer-machine* mode ([Frontiers in Psychology, 2025](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2025.1550621/full)).

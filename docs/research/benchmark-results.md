# SWE benchmark — live results (Opus / Sonnet / Haiku × difficulty)

> A real, measured run of [`evals/swe_bench.py`](../../evals/swe_bench.py) across the full
> difficulty ladder and all three model tiers. Methodology and the two-regime framing live in
> [swe-benchmark-design.md](swe-benchmark-design.md); the design's predictions came from the
> repo's earlier n=3 study ([`plans/06`](../../plans/06-overhead-and-uplift.md)). This doc reports
> what the instrument *actually measured*, the honest small-n caveats, and which
> [roadmap](improvement-roadmap.md) hypotheses the data supports, complicates, or refutes.

## What was run

- **Command:** `python3 evals/swe_bench.py --confirm --models haiku,opus,sonnet --reps 1 --out plans/data/swe-bench-2026-06-30.jsonl`
- **Date:** 2026-06-30. **Models:** `haiku` (Haiku 4.5), `opus` (Opus 4.8), `sonnet` (Sonnet 4.6), as the `claude` CLI resolves them.
- **Arms:** ON = the full applied agentic-cfg environment (skills, hooks, MCP, prefix); OFF =
  prompt-isolated bare agent (same binary, told to ignore the custom skills/rules/rtk/lean-ctx/
  ast-grep/gitnexus and use only built-in tools).
- **Reps:** 1 for the full matrix (**directional, not a verdict** — see the variance note), plus a
  **reps=5** confirmation pass on the `easy` tier for the headline.
- Raw per-cell JSON: [`plans/data/swe-bench-2026-06-30.jsonl`](../../plans/data/swe-bench-2026-06-30.jsonl)
  and [`plans/data/swe-bench-easy-n5-2026-06-30.jsonl`](../../plans/data/swe-bench-easy-n5-2026-06-30.jsonl).

## The matrix (reps=1)

`total` = total-input ratio ON/OFF (≈95 % cache_read). `repriced` = billed input only
(`input + cache_creation`). `cost` = API-equivalent cost ratio. `turns` = agent-loop length
ON/OFF. `correct` = pass/pass; for these reps=1 cells it is a single observation per arm (1/1),
not an established rate. Every cell passed on both arms (text check or `go test`).

| tier | model | total | repriced | cost | turns ON/OFF | correct |
|------|-------|------:|---------:|-----:|:------------:|:-------:|
| trivial | haiku | 1.01× | 1.02× | 1.05× | 3 / 3 | 100/100 |
| easy | haiku | **2.30×** | 1.21× | 1.56× | **19 / 9** | 100/100 |
| medium | haiku | 1.66× | 1.09× | 1.38× | 16 / 10 | 100/100 |
| hard | haiku | **0.84×** | 1.07× | 0.96× | 10 / 12 | 100/100 |
| very_hard | haiku | 1.29× | 1.18× | 1.25× | 26 / 16 | 100/100 |
| trivial | opus | 0.73× | 0.94× | 0.86× | 3 / 4 | 100/100 |
| easy | opus | 1.00× | 1.00× | 1.00× | 5 / 5 | 100/100 |
| medium | opus | 1.43× | 1.02× | 1.15× | 8 / 7 | 100/100 |
| hard | opus | 0.77× | 0.96× | 0.88× | 9 / 10 | 100/100 |
| very_hard | opus | **0.65×** | 0.96× | 0.81× | 12 / 15 | 100/100 |
| trivial | sonnet | 0.74× | 0.99× | 0.91× | 3 / 4 | 100/100 |
| easy | sonnet | **2.62×** | 1.12× | 1.57× | **18 / 8** | 100/100 |
| medium | sonnet | 1.54× | 1.05× | 1.20× | 10 / 8 | 100/100 |
| hard | sonnet | 1.20× | 1.01× | 1.05× | 12 / 10 | 100/100 |
| very_hard | sonnet | **3.02×** | 1.13× | 1.63× | **22 / 10** | 100/100 |

## Headline confirmation — `easy` tier at reps=5 (median of 5)

The `easy` tier was re-run at five reps per cell. The medians **deflate the matrix's most
dramatic single draws and reorder the models to match the thesis:**

| model | total (n=1 → n=5) | repriced n=5 | cost n=5 | turns n=5 ON/OFF | correct |
|-------|:-----------------:|:------------:|:--------:|:----------------:|:-------:|
| haiku | 2.30× → **1.67×** | 1.19× | 1.38× | 17 / 9 | 100/100 |
| sonnet | 2.62× → **1.31×** | 1.04× | 1.13× | 10 / 8 | 100/100 |
| opus | 1.00× → **1.01×** | 1.02× | 1.04× | 7 / 5 | 100/100 |

At n=5 the over-tooling is **real but moderate**, and ordered exactly by model weakness —
**haiku (1.67×) > sonnet (1.31×) > opus (1.01×)**. Crucially, the n=1 matrix's alarming
sonnet/easy 2.62× was a high-variance draw: five reps put it at 1.31×. The billed (`repriced`)
overhead is small for all three (1.02–1.19×); the visible cost overhead is the output/turn
effect, largest on Haiku (1.38×). This is the single most important result in the run — see
finding 2.

## What the data says

**1. The two-regime *direction* is consistent for Opus and Haiku — in a single-rep matrix.** Opus
is flat-to-helpful: ≤1.0× total on four of five tiers, only a mild `medium` bump (1.43× total but
1.02× repriced), and its largest *apparent* win on the hardest task (`very_hard` 0.65× total,
0.81× cost, 12 turns vs 15). Haiku over-tools the light scan task — `easy` **1.67× at n=5** (the
only replicated cell), 17 turns vs 9 — yet on `hard` it runs **fewer turns ON than OFF (10 vs 12)
at 0.96× cost**, though its billed input there is still 1.07×. **These hard-tier results are each
a single draw — directional, not reproduced** (only the `easy` tier was re-run at reps=5), so
they are "apparent wins" pending an n≥5 pass, exactly as the roadmap row below states. The earlier
n=3 study (`plans/06`) put weak-easy at 2.27×; this run's single `easy`-Haiku draw was 2.30× but
its 5-rep median is 1.67×, so read the direction, not the exact ratio.

**2. The n=1 matrix manufactured a false "Sonnet surprise" that reps=5 corrected.** The single-rep
matrix posted Sonnet's `easy` at 2.62× and `very_hard` at 3.02× — *above* Haiku's — which looked
like a real finding ("the mid tier over-tools as much as the weak one"). It is not. Re-running
`easy` at five reps collapsed Sonnet from 2.62× to **1.31×** and Haiku from 2.30× to **1.67×**,
restoring the weakness-ordered ranking the thesis predicts (haiku > sonnet > opus). The Sonnet
`very_hard` 3.02× is a **single unconfirmed draw** and, given the easy-tier correction, should be
read as noise until re-run at higher n — not as evidence that Sonnet over-tools the hardest task.
The honest, n=5-backed statement is narrower: **the mid tier is not perfectly immune like Opus —
it carries a small light-task tax (easy 1.31× total input, but only 1.04× billed / 1.13× cost at
n=5) — but it does not over-tool like the weak tier.**
The *method* lesson is the real headline: at n=1 the noise floor is high enough to invent a
plausible cross-model surprise, which is exactly why the repo's own rule is medians-over-reps
before any claim (finding 5).

**3. The scary "3×" numbers are mostly free cache, not bill.** Read the `repriced` column next to
`total`. Even the noisiest single draw — Sonnet's `very_hard` at 3.02× *total* input — is only
**1.13× billed** input; Haiku's `easy` is 1.67× total but **1.19× billed** at n=5. ~95 % of "total
input" is `cache_read`, which is near-free. The honest overhead lives in **`cost` (≈1.1–1.6× on the over-tooling cells at n=1;
1.1–1.4× on the replicated `easy` tier)**, and it is driven by **output**, i.e. extra turns — not
by the always-on prefix bytes. This is the repo's own "overhead is turns, not bytes" finding, now visible per cell:
every cell with cost > 1.2× also has ON turns well above OFF turns; every cell at parity has equal
turns.

**4. Correctness never diverged — the toolset's measured value is efficiency, not rescue.** All
30 arms (15 cells × ON/OFF) were correct, *including* the multi-file `very_hard` refactor on bare
Haiku. So nothing here shows the custom layer making a model *succeed where it would have failed*;
its only measured effect is the turn-count delta (a tax on light tasks, a saving on hard ones for
Haiku/Opus). This directly **reaffirms roadmap item 0**: the suite still lacks a task where
weak-bare actually fails, so the central open question — does the toolset lift *correctness* for
weak models? — remains unanswered. The `very_hard` task needs to be made genuinely harder (or run
at higher n where bare-Haiku flakiness would show) before any quality lever can be proven.

**5. n=1 is genuinely noisy — quantified.** Minutes before this matrix, a standalone
`trivial × haiku` cell measured **3.22×** (9 turns vs 3); in the matrix the same cell measured
**1.01×** (3 turns vs 3). Same task, same model, opposite verdict. That single swing is the whole
argument for medians over many reps before shipping anything — and the reason the `easy` tier was
re-run at reps=5 below.

## What this licenses — and what it does not

- **Licensed:** "On current evidence the config is net-neutral-to-helpful for Opus across the
  ladder; a moderate, weakness-ordered turn-tax on the light `easy` task (haiku 1.67× > sonnet
  1.31× > opus 1.01× at n=5) that does not touch correctness; and honest billed-input overhead of
  ~1.0–1.2× with the visible cost overhead being an output/turns effect." These three are the only
  statements backed by a 5-rep median.
- **Not licensed:** any claim that the toolset improves correctness (zero divergence observed);
  **any single-rep cell as a finding** — the sonnet `very_hard` 3.02× and `hard` 1.20×, and the
  3.22× `trivial`-haiku draw, are n=1 and several were shown to collapse under reps=5; any precise
  per-cell ratio as a ship gate; any cost claim as a Max-plan *bill* (`cost_usd` is an
  API-equivalent estimate and the subprocess arms don't run inside the live PreToolUse hook).

## Roadmap impact

| Roadmap item / claim | This run says |
|---|---|
| **0** — build a task where weak-bare *fails* | **Reinforced.** 30/30 arms correct; the hardest task didn't break bare Haiku. The correctness question is still unmeasured. |
| **1** — harden `overhead.py` (per-rep, raise n) | **Reinforced.** On-tier evidence: Haiku's `easy` ratio moved 2.30× (n=1) → 1.67× (n=5 median), the exact wide-IQR-at-low-n the item predicts. (The standalone 3.22×→1.01× `trivial`-haiku swing is further, off-tier, n=1-noise evidence.) The cells need n≥5 persisted distributions. |
| **2** — near-vanilla weak tier | **Supported, magnitude tempered.** Haiku's `easy` tax is real at n=5 (1.67×). Sonnet shows a *small* tax (1.31× total, 1.04× billed); the n=1 hint that it over-tools like Haiku did not survive reps=5, so "extend the trimmed profile to Sonnet" is a weaker (still testable) hypothesis than the matrix first suggested. |
| **3** — conditional Read/Grep redirect | **Supported by the easy/medium tiers — and it corrects the item's own premise.** Roadmap item 3 names a "trivial-task turn-inducer (12–20 turns)", but every measured `trivial` cell is 3 ON turns (3/3, 3/4, 3/4) — parity or below OFF, no inducer there. The 12–26-turn inducer actually lives on `easy` (haiku 19, sonnet 18), `medium` (haiku 16) and `very_hard` (haiku 26); a redirect that doesn't fire on small/low-breadth reads should target *those* tiers, and item 3's trivial framing should be rewritten. |
| *(thesis claim, not a numbered item)* hard-task payoff is universal | **Not supported as stated; under-powered.** A win is *suggested* for Opus (`very_hard` 0.65×, n=1) and Haiku (`hard` 0.84× total / 0.96× cost, n=1), but both are single draws — as are the Sonnet `hard` 1.20× / `very_hard` 3.02×. No hard-tier cell has an n≥5 median, so per-model "payoff" is neither confirmed nor denied. |

## Caveats (from the design, restated honestly)

- Single machine, single run (plus one reps=5 tier); MCP cold-start and network jitter are inside
  the timings. n=1 cells are directional only.
- The `claude` subprocess arms load the config but do not execute inside the live PreToolUse hook,
  and `cost_usd` is an API-equivalent estimate, not a Max-plan bill.
- Correctness is graded deterministically (text match or `go test`), so "100 %" means the check
  passed, not that the diff was idiomatic.

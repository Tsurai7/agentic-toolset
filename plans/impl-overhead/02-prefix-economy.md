# W2 — Prefix economy (de-dup + MCP-schema deferral + byte budget)

> Parent: [../06-overhead-and-uplift.md](../06-overhead-and-uplift.md). Relates to ADR-0006
> (model-tier render fork) and the P2-13 cache gate on branch `722d6e2`; MAT-05/MAT-07.

## Goal

Shrink the always-on prefix that is re-read on **every** turn, and make that size
**budgeted and enforced**. Unlike W1 (behavioural, helps only the prompt-isolation axis),
W2 is the only lever that also helps against a *truly bare* agent, and its saving
multiplies by turn count.

## Evidence

Turn-1 always-on context is **~28.3k tokens** (identical across all arms — it is the
config, not the task). `cache_read` re-reads it every turn: on the easy ON run that was
**323k** over 12 turns (~27k/turn). Cutting the prefix by *k* tokens saves ~`k × turns`
input. Source footprint (measured 2026-06-26):

- `~/.claude/CLAUDE.md` — **10,016 bytes** (~2.8k tokens), inlining AGENTS.md + tool
  precedence + honesty principles + Karpathy guidelines + coding-principles +
  communication + cursor-rules-pointer.
- `~/.claude/rules/lean-ctx.md` — **2,481 bytes** (~0.7k tokens).
- Skill listing — 8 skills (descriptions only; bodies load on demand).
- **MCP tool schemas** — `lean-ctx` (~25 `ctx_*` tools) is the only user-scope server;
  its schemas are always-on **unless deferred**. Potentially the largest single removable
  chunk — must be measured (step 3).

## Duplication found (MAT-05, in the installed CLAUDE.md)

- **"verify before done" stated 3×**: AGENTS.md Global default #6, the
  `verification-before-completion` skill, and Karpathy guideline #4 ("Goal-driven
  execution").
- **coding-principles ⊃ Karpathy overlap**: "Simplicity first" / "Surgical changes" /
  "minimize scope" appear in both the Karpathy block and the coding-principles user-rule
  (`simpl` matches 7×, `surgical` 2× in one file).
- **Tool guidance stated twice**: the Global-defaults numbered list and the Tool-precedence
  table both enumerate rtk/ast-grep/gitnexus/lean-ctx precedence.

## Changes (concrete)

1. **Consolidate to single source.** Keep each principle once, in its canonical home,
   and cross-reference instead of restating:
   - "Verify before done" → keep in the `verification-before-completion` skill; reduce
     AGENTS.md #6 and Karpathy #4 to one-line pointers.
   - Merge the coding-principles/Karpathy overlap into one "code-change principles" block;
     drop the duplicated sentences.
   - Collapse the Global-defaults tool list into the Tool-precedence section (which W1 is
     already editing) so tool guidance appears once.
   - Target: **CLAUDE.md ≤ ~7 KB** (from 10 KB) with no loss of distinct guidance.

2. **Weak-tier render byte budget + gate (extends ADR-0006).** The ADR-0006 model-tier
   fork requires only "strong render < weak render". Add a **hard ceiling on the weak
   render** too: `providers/claude/install.sh:install_claude_md()` must produce a weak-tier
   prefix ≤ a committed budget (e.g. a `PREFIX_BUDGET_TOKENS` constant). Wire a check into
   `bin/ci-check.sh` and `telemetry/gate.py` (P2-13): a render that exceeds budget or
   drops cache-hit below 0.85 is a **blocking regression**.

3. **MCP-schema deferral / trim (measure first).** Determine whether `lean-ctx`'s ~25
   tool schemas are inline in a fresh `claude -p` weak-tier session or deferred behind
   tool-search (as they are in the interactive session here). Method: diff turn-1
   `cache_creation` with the server enabled vs a config-dir render with it removed
   (`evals/lib/render_config.py` config-dir mode, needs `ANTHROPIC_API_KEY`). Then:
   - If inline and large: prefer **tool-search/deferred loading** for the weak tier, or
     **trim the surfaced `ctx_*` set** to the few the config actually routes through
     (read/search/shell/edit), dropping rarely-used tools from the always-on surface.
   - If already deferred: record it (no action) and remove MCP schemas from the suspect
     list.

4. **Byte-stability golden (MAT-07).** Add a golden test asserting the rendered weak- and
   strong-tier CLAUDE.md are byte-identical across runs (stable cache prefix). A churny
   prefix silently destroys the 96% cache-hit rate, inflating `cache_creation` every
   session.

## Validation

- **Footprint:** turn-1 `cache_creation` (the new/session-specific prefix chunk) drops
  measurably vs the 2026-06-26 baseline; `total_input` on a fixed multi-turn task drops
  proportionally to (saved-prefix × turns).
- **No-loss:** every distinct rule still present (diff the de-duped CLAUDE.md against the
  original; each removed line maps to a surviving single source).
- **Cache stable:** byte-stability golden green; `telemetry/gate.py` cache-hit ≥ 0.85.
- **Budget enforced:** CI fails if the weak-tier render exceeds `PREFIX_BUDGET_TOKENS`.

## Projected gain

Directly-editable text (CLAUDE.md + rules + listing) ≈ ~4k tokens; de-dup reclaims an
estimated ~1–1.5k tokens/turn → on a 12-turn run, ~12–18k fewer `total_input`. **MCP
deferral, if schemas are inline, could dwarf this** (a 25-tool surface can be several k
tokens/turn) — hence step 3 is measure-first. All multiply by turn count and stack with
W1's turn reduction.

## Risks

- **De-dup that loses nuance.** Some "duplication" is deliberate reinforcement for weak
  models. Mitigate: keep the *content* once but ensure it is still reachable; validate
  weak-model conformance (the verify/triage/safety cases) does not regress after de-dup.
- **Trimming MCP tools the config relies on.** Only trim after confirming the routing
  table (lean-ctx rules) doesn't reference the dropped tool; keep them loadable on demand.

## Decisions for the owner

- Hard prefix budget value (tokens) for the weak tier — propose calibrating from the
  de-duped render + a small headroom, committed as a constant.
- Whether to trim the `lean-ctx` surfaced toolset or rely solely on tool-search deferral
  (recommended: rely on deferral if measurement shows it active; trim only if inline).

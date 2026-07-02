# 04 — Pricing: Claude 5 rows, current Opus rates, unknown-model flag

**Problem** (audit finding 11, plus a new fact found during planning): neither
`internal/gain/gain.go` nor `telemetry/report.py` knows the Claude 5 family, so
`claude-fable-5` (9.7% of input and rising) silently bills at the table's opus rates.
Worse: the **opus row itself is 3× stale** — the table says $15 in / $75 out per MTok,
while current Opus 4.x pricing is **$5 / $25**. All dollar figures in the 2026-07-02
audit were computed with the stale table.

**Depends on:** plan 03 merged first (same file, `internal/gain/gain.go`).

## Authoritative rates (per MTok, cached from platform docs 2026-06-24 via the claude-api reference)

| Family key | input | cache read (0.1×) | cache write 5m (1.25×) | cache write 1h (2×) | output |
|---|---|---|---|---|---|
| `fable`, `mythos` | 10.00 | 1.00 | 12.50 | 20.00 | 50.00 |
| `opus` (4.x) | 5.00 | 0.50 | 6.25 | 10.00 | 25.00 |
| `sonnet` | 3.00 | 0.30 | 3.75 | 6.00 | 15.00 |
| `haiku` | 1.00 | 0.10 | 1.25 | 2.00 | 5.00 |

Notes: Sonnet 5 has introductory pricing ($2/$10) through 2026-08-31 — use the sticker
$3/$15 and say so in the table comment (estimates, not billing truth). Cache multipliers
are Anthropic's published 0.1× / 1.25× / 2× applied to the input rate.

## Change specification

### `internal/gain/gain.go`

1. Update the `pricing` slice: add `{"fable", …}` and `{"mythos", …}` **before** the
   existing keys (substring matching — order is the precedence), correct the `opus` row
   to the table above, leave `sonnet`/`haiku` as-is. Update the comment block above it
   (rates, cache multipliers, "keep in sync with telemetry/report.py", cache date).
2. Unknown-model visibility: add `func knownModel(model string) bool` (same substring
   scan as `ratesFor`). In `Render`/`RenderCache` by-model rows, suffix the model name
   with `*` when unknown, and print one footnote line
   (`* unknown model — billed at default (opus) rates in these estimates`) only when at
   least one row is flagged. `ModelStat` gains a `Known bool` field (include in JSON as
   `"known_pricing"`).
3. Default fallback stays opus (now the *current* opus rates).

### `telemetry/report.py`

Mirror the same table in `PRICING` (it uses per-model dicts — add `fable`/`mythos`,
correct `opus`), keep `DEFAULT_RATES = PRICING["opus"]`, and update its comment header
(same cache date + sync note).

### Erratum in the audit doc

Append a short `## Erratum (2026-07-02)` section to
`docs/design/gain-and-enforcement-audit-office-hours.md`: the dollar figures in the audit
were computed with the pre-fix table (opus at $15/$75 — 3× the current $5/$25, fable
billed as opus); token counts, hit rates, shares, and every non-dollar finding are
unaffected; re-run `agentic gain` after this wave for corrected dollars.

### Tests

`internal/gain/gain_test.go` (or a dedicated pricing test):

- `ratesFor("claude-fable-5")` → `{10, 1, 12.5, 20, 50}`.
- `ratesFor("claude-mythos-5")` → same.
- `ratesFor("claude-opus-4-8")` → `{5, 0.5, 6.25, 10, 25}`.
- `ratesFor("claude-sonnet-5")` / haiku unchanged.
- `ratesFor("totally-unknown-model")` → opus rates, and `knownModel` returns false.

## Acceptance criteria (hard)

1. All five `ratesFor` unit assertions above pass; `go test ./internal/gain/` green.
2. `./bin/agentic gain --by-model --last 20` runs; if an unknown model appears it is
   flagged with `*` + footnote; known models are not flagged.
3. `python3 telemetry/report.py --last 3` runs without error.
4. `grep -c "15.0" internal/gain/gain.go` shows the stale opus input rate is gone from
   the pricing table (sonnet's 15.0 *output* remains — check the row, not just the number).
5. The audit doc contains the `## Erratum` section.
6. Both files' pricing comments carry the same cache date and the mutual sync note.
7. Diff touches only: `internal/gain/gain.go`, `internal/gain/gain_test.go`,
   `telemetry/report.py`, `docs/design/gain-and-enforcement-audit-office-hours.md`.

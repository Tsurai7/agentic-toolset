# issues

Known problems with the agent environment, tooling, or workflow — one Markdown
file per issue. These are operational gotchas worth remembering across sessions,
not code bugs tracked in a normal tracker.

## Format

Each file is `<kebab-slug>.md` with YAML frontmatter followed by prose:

```markdown
---
id: <kebab-slug>            # must equal the filename
title: <short title>
severity: low | medium | high | critical
status: open | mitigated | resolved | wontfix
area: <component, e.g. shell-hook / git / no-mistakes / telemetry>
discovered: YYYY-MM-DD
---

## Summary
One or two sentences: what is wrong.

## Impact
What breaks, and what damage it can cause if unnoticed.

## How to reproduce
Concrete, minimal steps.

## Workaround
What to do instead until it is fixed (if anything).

## Root cause / notes
Optional: what we know about why it happens.
```

## Severity guide

- **critical** — silent data loss or acting on the wrong target with no signal.
- **high** — wrong/destructive behavior that is recoverable but easy to miss.
- **medium** — reliable failure with a clear error, has a workaround.
- **low** — cosmetic or rare, minimal impact.

See `_TEMPLATE.md` to start a new one.

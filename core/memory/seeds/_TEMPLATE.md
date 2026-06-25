---
name: example-fact-slug
description: One-line summary used to judge relevance during recall
metadata:
  type: user
---

This is a template, not a real fact. Files whose name starts with `_` are
skipped by `sync.py` and never distributed to project memory.

Copy this file to `seeds/<slug>.md` (drop the leading underscore) to create a
real cross-project seed. Rules for the body:

- `metadata.type` must be one of: `user`, `feedback`, `project`, `reference`.
  Only `user` and `feedback` facts belong in `seeds/` — they are cross-project
  by nature (who you are, how you want the agent to work). `project` and
  `reference` facts stay in their own project's memory, not here.
- `name` must equal the filename slug (kebab-case).
- For `feedback`/`project` facts, follow the body with `**Why:**` and
  `**How to apply:**` lines.
- Link related memories with `[[other-slug]]`.

See POLICY.md for the full memory architecture and where each fact type lives.

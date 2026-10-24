# Coding principles

Always follow when writing code:

1. **Minimize scope** — Simplest correct diff. No unrelated changes, especially for question-only or review-only tasks.
2. **Avoid over-engineering** — No one-line helpers that should be inline. No excessive error handling for impossible edges.
3. **Use existing conventions** — Match naming, types, abstractions, imports, documentation level. Reuse and extend rather than reimplement.
4. **Comments** — Default to none; code should be self-explanatory. Comment only where the code would be unclear without it (a non-obvious business rule, a workaround, a deep technical reason). Keep each comment as short as possible: one line, at most 80 characters, saying why, not what. Never restate the code, narrate the change, or split one comment into several to get around the limit. When you change code, update or delete the comments it makes stale.
5. **Useful tests only** — Add tests when requested or they add meaningful coverage of real behavior. No tests that trivially assert the obvious.

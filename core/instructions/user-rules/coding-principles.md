# Coding principles

Always follow when writing code:

1. **Minimize scope** — Simplest correct diff. No unrelated changes, especially for question-only or review-only tasks.
2. **Avoid over-engineering** — No one-line helpers that should be inline. No excessive error handling for impossible edges.
3. **Use existing conventions** — Match naming, types, abstractions, imports, documentation level. Reuse and extend rather than reimplement.
4. **Comments** — Code should be self-explanatory. Comments only for non-obvious business logic or deep technical details.
5. **Useful tests only** — Add tests when requested or they add meaningful coverage of real behavior. No tests that trivially assert the obvious.

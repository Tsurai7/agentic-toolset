# Principles (always-on)

Principles are **always-on behavioral guidance** — they shape every action the
agent takes, without waiting for a trigger to match. Each `*.md` here is rendered
into the providers' always-on layers by `bin/install.sh`:

- **Claude** — concatenated into the generated `~/.claude/CLAUDE.md`.
- **Cursor** — rendered to an `alwaysApply: true` rule in `~/.cursor/rules/`.

## Principle vs skill — where does new guidance go?

| | Principle (`core/principles/`) | Skill (`core/skills/`) |
|---|---|---|
| Loaded | Always, every turn | On trigger (description match) |
| Use for | Cross-cutting behavioral defaults (how to think, edit, verify) | Situational tools/procedures (`ast-grep`, `create-pr`, `gitnexus`) |
| Cost | Always in context — keep short | Near-zero until triggered |

Rule of thumb: if it should apply *even when the agent isn't thinking about it*,
it's a principle. If the agent should reach for it *when a specific situation
arises*, it's a skill. Keep principles short — they pay a per-turn context cost.

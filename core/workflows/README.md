# Workflow catalog

Use marketplace plugins for full workflow libraries. This repo only documents **when** to reach for each.

## Recommended baselines (install from marketplace)

| Plugin | Use when |
|--------|----------|
| **superpowers** | Starting features (brainstorming), TDD, systematic debugging, verification before claiming done, executing written plans |
| **cursor-team-kit** | Fixing CI, PR review, compiler errors, smoke tests, merge conflicts |
| **ponytail** | Cutting generated-code bloat — a do-less decision ladder before implementing (token economy); `/ponytail-review`, `/ponytail-audit` |

## Personal skills (this repo — `core/skills/`)

| Skill | Use when |
|-------|----------|
| `git-safety` | User asks to commit; always before `git commit` |
| `create-pr` | User asks to open or update a pull request |
| `verification-before-completion` | About to claim work is complete or tests pass |
| `gitnexus-navigation` | Structural code changes, refactors, impact analysis |
| `ast-grep` | Searching/rewriting code by syntax pattern (instead of regex grep) |
| `terminal-rtk` | Running shell commands on macOS |
| `model-orchestration` | Planning a multi-step / token-expensive task: pick the model tier per sub-task; plan strong, execute cheap, escalate |

## Decision flow

1. **Bug or test failure** → superpowers `systematic-debugging`, then `verification-before-completion`
2. **New feature** → superpowers `brainstorming` / `writing-plans`, then implement with `git-safety`
3. **PR / CI** → full gated PR (review/test/docs/lint + CI auto-fix) via `no-mistakes` (see [`integrations/no-mistakes/`](../../integrations/no-mistakes/)); plain PR with no gate via `create-pr`
4. **Cross-file refactor** → `gitnexus-navigation` for impact, then `ast-grep` for pattern search/rewrite (not regex grep)
5. **Multi-step or token-expensive task** → `model-orchestration`: plan/decide with a strong tier, delegate well-specified mechanical sub-tasks to a cheaper tier or subagents, verify, escalate only on failure. Skip the split for anything that fits one context. See [`archive/model-orchestration-office-hours.md`](../../archive/model-orchestration-office-hours.md) for the scope rationale.

See [`catalog/plugins.yaml`](../../catalog/plugins.yaml) for install links.

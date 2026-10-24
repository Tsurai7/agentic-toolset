# Workflow catalog

Use marketplace plugins for full workflow libraries. This repo only documents **when** to reach for each.

## Recommended baselines (install from marketplace)

| Plugin | Use when |
|--------|----------|
| **superpowers** | Starting features (brainstorming), TDD, systematic debugging, verification before claiming done, executing written plans |
| **cursor-team-kit** | Fixing CI, PR review, compiler errors, smoke tests, merge conflicts |
| **ponytail** | Cutting generated-code bloat — a do-less decision ladder before implementing (token economy); `/ponytail-review`, `/ponytail-audit` |

## Personal skills

See [`core/skills/`](../skills/) — each `SKILL.md` description is its trigger.

## Decision flow

1. **Bug or test failure** → `systematic-debugging` (the repo-local skill in `core/skills/systematic-debugging/`, distilled from gstack), then `verification-before-completion`. If the `superpowers` plugin is also installed its own `systematic-debugging` skill overlaps; the local one auto-fires on its description regardless.
2. **New feature** → superpowers `brainstorming` / `writing-plans`, then implement with `git-safety`
3. **PR / CI** → full gated PR (review/test/docs/lint + CI auto-fix) via `no-mistakes` (see [`integrations/no-mistakes/`](../../integrations/no-mistakes/)); plain PR with no gate via `create-pr`
4. **Cross-file refactor** → `codebase-memory` for impact, then `ast-grep` for pattern search/rewrite (not regex grep)
5. **Multi-step or token-expensive task** → `model-orchestration`: plan/decide with a strong tier, delegate well-specified mechanical sub-tasks to a cheaper tier or subagents, verify, escalate only on failure. Skip the split for anything that fits one context. See [`archive/model-orchestration-office-hours.md`](../../archive/model-orchestration-office-hours.md) for the scope rationale.
6. **Vetting a proposal before building it** → `office-hours`: run the forcing questions (premise, status quo, evidence of value, narrowest wedge, risk, cost of keeping) before writing an implementation plan for a new capability.

See [`catalog/plugins.yaml`](../../catalog/plugins.yaml) for install links.

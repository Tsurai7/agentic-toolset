---
name: git-safety
description: >-
  Safe git commit workflow. Use when the user asks to create a commit, or before
  running git commit. Covers staging, message style, HEREDOC format, amend rules,
  and hook failures.
---

# Git commit safety

Only create commits when **requested by the user**. If unclear, ask first.

## Before committing

Run in parallel:

- `git status` — untracked files
- `git diff` — staged and unstaged changes
- `git log` — recent messages for style

## Message

- 1–2 sentences focused on **why**, not only what
- Accurate type: add / update / fix / refactor / test / docs
- Do not commit secrets (`.env`, credentials, etc.)

## Commit command

Pass message via HEREDOC:

```bash
git commit -m "$(cat <<'EOF'
Commit message here.

EOF
)"
```

## Protocol

- **NEVER** update git config
- **NEVER** destructive commands (`push --force`, `hard reset`, etc.) unless explicitly requested
- **NEVER** skip hooks (`--no-verify`, `--no-gpg-sign`) unless explicitly requested
- **NEVER** force push to `main`/`master` — warn if requested
- **Avoid `git commit --amend`** unless ALL:
  1. User requested amend, OR commit succeeded but pre-commit hook modified files
  2. HEAD commit was created in this session by you
  3. Commit has **not** been pushed
- If commit **failed** or was **rejected by hook** — never amend; fix and **new commit**
- If already pushed — never amend unless user explicitly requests (needs force push)
- **Do not push** unless user asks

## Sequence

1. Stage relevant files
2. Commit with HEREDOC message
3. `git status` to verify

## Hook failure

Fix the issue and create a **new** commit — do not amend a failed commit.

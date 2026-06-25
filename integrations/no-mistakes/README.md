# no-mistakes integration

[no-mistakes](https://github.com/kunchenguid/no-mistakes) is a local git proxy +
AI validation pipeline: you push to a gate remote instead of `origin`, it runs
**review → test → docs → lint → push → PR → CI** in a disposable worktree, applies
safe mechanical fixes, escalates intent-touching findings to you, and opens a clean
PR only once every check is green. Evidence for each change is stored under
`.no-mistakes/evidence/`.

It enforces, mechanically, what this repo asks for in prose: the
`verification-before-completion` skill, the `honesty` principle (evidence-backed
claims), and `create-pr` (clean PRs).

## Install

The binary is **not vendored**. `bin/bootstrap.sh` installs it via:

```sh
go install github.com/kunchenguid/no-mistakes/cmd/no-mistakes@latest
```

Ensure the Go bin dir is on `PATH` (e.g. `export PATH="$(go env GOPATH)/bin:$PATH"`).
Alternatives (curl installer, build from source) are in the
[upstream install guide](https://kunchenguid.github.io/no-mistakes/start-here/installation/).

## Per-repo setup (not global)

Unlike skills/MCP, no-mistakes is configured **per repository** — it wires a gate
remote for that specific repo:

```sh
cd <your-repo>
no-mistakes init                       # gate remote + installs the /no-mistakes skill
# for fork contributions:
no-mistakes init --fork-url <your-fork-url>
```

Then use any of the three entry points:

- `git push no-mistakes <branch>` — explicit git path
- `no-mistakes` (`-y` to auto-drive) — TUI wizard
- `/no-mistakes <task>` — the agent skill (drives `no-mistakes axi`, a
  non-interactive interface to the same approval flow)

## Interaction with this repo's skills layout

`no-mistakes init` installs the `/no-mistakes` skill "at user level" — into
`~/.claude/skills` (and `~/.cursor/skills`), which here are **symlinks to
`core/skills/`**. So the generated `SKILL.md` lands at
`core/skills/no-mistakes/SKILL.md`. That path is **gitignored** on purpose: the
skill is generated and versioned by the `no-mistakes` binary (regenerated on
`init`/upgrade), so we let the tool own it rather than committing a drifting copy.

## When to use which

- **Full gated PR (review/test/docs/lint + CI auto-fix)** → `no-mistakes`
- **Plain PR, no gate** → the `create-pr` skill

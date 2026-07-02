# Setup — using this config on a new machine

How to install this agentic config on a fresh laptop for **Cursor** and/or
**Claude Code**, and how to keep it updated.

## 1. Authenticate (the repo is private)

The repo lives under the **Tsurai7** GitHub account and is private, so a new
machine needs access first:

```bash
# install gh however you like, then:
gh auth login            # log in as Tsurai7, HTTPS protocol
```

## 2. Clone (anywhere)

The install path is detected automatically, so the clone location is up to you:

```bash
git clone https://github.com/Tsurai7/agentic-cfg.git
cd agentic-cfg
```

## 3. One command: deps + install

`bin/bootstrap.sh` installs every dependency (Homebrew if missing, git, python3,
node, gh, plus the optional `rtk` and `lean-ctx`), then runs the installer and a
health check:

```bash
bin/bootstrap.sh                  # all providers
# or: bin/bootstrap.sh --provider cursor
```

That's the whole setup. GitNexus needs no install (it runs via `npx`).

<details>
<summary>Manual path (if you don't want bootstrap to install deps)</summary>

```bash
brew install python3 node gh rtk ast-grep go
brew install yvgude/lean-ctx/lean-ctx     # optional
cp secrets/.env.example secrets/.env       # only to override auto-detected paths
bin/install.sh --provider all
bin/doctor.sh --deep
```
</details>

What each provider gets:

| Provider | Installed |
|----------|-----------|
| **Cursor** | `~/.cursor/skills` → symlink to `core/skills`; rule `core/rules/lean-ctx.mdc` → `~/.cursor/rules`; hooks → `~/.cursor/hooks.json`; MCP **merged into** `~/.cursor/mcp.json` (existing servers preserved) |
| **Claude** | `~/.claude/skills` → symlink; `~/.claude/CLAUDE.md` generated from `AGENTS.md` + user-rules; MCP registered into `~/.claude.json` (user scope, via the `claude` CLI — PORT-03, *not* `~/.claude/.mcp.json`); hooks + permissions merged into `settings.json` |

Restart Cursor / Claude afterwards.

Preview changes without writing anything:

```bash
bin/install.sh --provider all --dry-run
```

## 4. Manual step for Cursor

Cursor **User Rules** (Settings → Rules) live in the cloud and are not synced by
files. After install, paste the short pointer rule from
[`core/instructions/user-rules/cursor-rules-pointer.md`](core/instructions/user-rules/cursor-rules-pointer.md)
into Cursor → Settings → Rules.

## 5. Keep it updated

```bash
cd <your clone>
git pull
bin/install.sh --provider all      # idempotent; backs up what it replaces
```

Edit configs in this repo → commit → `git pull` + `install.sh` on other machines.

## 6. Per-project use

For a work repo, drop [`core/instructions/AGENTS.md`](core/instructions/AGENTS.md)
in the project root (or add this repo as a submodule). Keep project-specific
skills in the project's own `.cursor/skills` / `.claude/skills`; personal skills
stay in `$HOME` via the symlink.

GitNexus indexes per repo — run `npx -y gitnexus@1.6.8 analyze` from a project root
once. The version is pinned repo-wide for reproducible installs (see
`integrations/gitnexus/README.md` for the bump procedure); the pin requires Node ≥22
(`brew install node`).

## The `agentic` CLI — install, apply to Claude, verify, remove

`bin/bootstrap.sh` / `bin/install.sh` above sync the *config* (skills, CLAUDE.md, MCP,
hooks). The `agentic` Go binary is a second, optional surface: one reversible command to
inject/eject the agentic-cfg footprint in Claude, plus read-only token-economy metrics. It
is gitignored and built fresh from the checkout.

Build it and put it on PATH once:

```bash
make build            # builds ./bin/agentic (equivalently: go build -o bin/agentic ./cmd/agentic)
./bin/agentic link    # symlinks `agentic` + `agentic-cfg` into ~/.local/bin (override with --dir)
```

Apply to local Claude — two equivalent entry points:

```bash
bin/install.sh --provider claude     # full sync: skills, CLAUDE.md, MCP, hooks + permissions
# ...or the reversible, test-covered front door:
agentic inject                       # skills symlink + CLAUDE.md @import + hooks/permissions + MCP
agentic inject --dry-run             # preview; --skip-mcp to leave MCP alone; --home DIR to target
```

Both preserve your own CLAUDE.md text, your `settings.json` `env`/hooks, and any real
`~/.claude/skills` you already have (a real skills dir is backed up, not clobbered). Restart
Claude Code afterwards to pick up MCP and skills.

Verify, and read the session token economy:

```bash
bin/doctor.sh                # health check — "Passed with N warning(s)" is honest; read the WARN lines
agentic status               # is agentic-cfg injected? exit 0 = yes, 1 = no (--json for scripts)
agentic gain                 # session token economy: cache hit rate + the ACTUAL input bill + cache-avoided
agentic gain --adoption      # enforcement coverage: shell-guard wrap/deny/fail-open shares
agentic cache                # cache-focused view (alias for `agentic gain --cache`)
```

`agentic gain` reports the *session's* prompt-cache economy, not a config-attributed saving:
prompt caching is a Claude platform feature, so the "cache avoided" figure is what caching
saves versus re-sending context uncached — it is shown next to the actual bill so it can't be
read as money the config pocketed. To measure the *config's own* effect, use the A/B
benchmark (`evals/swe_bench.py`), not this readout.

Remove cleanly — the exact inverse of inject, leaving your own content untouched:

```bash
agentic eject
```

## Notes

1. **lean-ctx is portable on both sides.** Cursor gets the rule, MCP server, and
   hooks; Claude gets the MCP server plus hooks + permissions merged into
   `~/.claude/settings.json` (your machine-local `env`, e.g. a proxy URL, is
   preserved). The `lean-ctx` binary is installed by `bin/bootstrap.sh`.
2. **`rtk`** is installed by `bin/bootstrap.sh` (Homebrew core). There is no
   separate rtk hook — on machines running lean-ctx, its rewrite hook wraps shell
   commands; see the tool-precedence section in `AGENTS.md`.
3. **`ANTHROPIC_BASE_URL`** and other machine-local `env` are intentionally not
   vendored — set them per machine in `~/.claude/settings.json`.
4. **GitNexus** must be indexed per project (`npx -y gitnexus@1.6.8 analyze`).
5. **CI workflow** (`.github/workflows/ci.yml`) is live on master, running
   `bin/ci-check.sh` and `golangci-lint` on every push and pull request.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the repo is wired internally.

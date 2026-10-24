# Setup — using this config on a new machine

How to install this agentic config on a fresh laptop for **Cursor** and/or
**Claude** (Desktop + Code), and how to keep it updated.

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

That's the whole setup. codebase-memory-mcp (graph code navigation) is installed and registered separately.

<details>
<summary>Manual path (if you don't want bootstrap to install deps)</summary>

```bash
brew install python3 node gh rtk
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
| **Claude** | `~/.claude/skills` → symlink; `~/.claude/CLAUDE.md` generated from `AGENTS.md` + user-rules; MCP merged into `~/.claude/.mcp.json`; `settings.json` created from template if absent |

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
cd ~/Documents/GitHub/personal/agentic-cfg
git pull
bin/install.sh --provider all      # idempotent; backs up what it replaces
```

Edit configs in this repo → commit → `git pull` + `install.sh` on other machines.

## 6. Per-project use

For a work repo, drop [`core/instructions/AGENTS.md`](core/instructions/AGENTS.md)
in the project root (or add this repo as a submodule). Keep project-specific
skills in the project's own `.cursor/skills` / `.claude/skills`; personal skills
stay in `$HOME` via the symlink.

codebase-memory-mcp indexes per repo — run its `index_repository` tool from a project once.

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
4. **codebase-memory-mcp** must be indexed per project (`index_repository`).
5. **CI workflow** (`.github/workflows/ci.yml`) is not pushed yet — it needs a
   gh token with the `workflow` scope (`gh auth refresh -h github.com -s workflow`).

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the repo is wired internally.

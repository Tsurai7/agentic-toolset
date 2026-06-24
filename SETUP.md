# Setup — using this config on a new machine

How to install this agentic config on a fresh laptop for **Cursor** and/or
**Claude** (Desktop + Code), and how to keep it updated.

## 0. Prerequisites (once per machine)

```bash
xcode-select --install                  # git
brew install python3 node               # python3 + npx (installer + MCP launchers)

# Optional external binaries the config REFERENCES but does not vendor:
brew install yvgude/lean-ctx/lean-ctx   # lean-ctx (ctx_* tools + hooks)
# rtk — installed separately; not version-controlled in this repo (see Caveats)
```

GitNexus needs no install — it runs via `npx`.

## 1. Authenticate (the repo is private)

The repo lives under the **Tsurai7** GitHub account and is private, so a new
machine needs access:

```bash
brew install gh
gh auth login            # log in as Tsurai7, HTTPS protocol
```

## 2. Clone into the expected path

The generated `~/.claude/CLAUDE.md` points at a fixed path, so clone there:

```bash
git clone https://github.com/Tsurai7/agentic-cfg.git ~/Documents/GitHub/personal/agentic-cfg
cd ~/Documents/GitHub/personal/agentic-cfg
cp secrets/.env.example secrets/.env     # adjust paths for this machine if needed
```

## 3. Install

```bash
bin/install.sh --provider all     # or: --provider cursor | --provider claude
bin/doctor.sh --deep              # verify
```

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

GitNexus indexes per repo — run `npx gitnexus analyze` from a project root once.

## Caveats (honest portability gaps)

1. **Claude side is lighter than a fully hand-tuned machine.** The generated
   `CLAUDE.md` is built from `AGENTS.md` + `core/instructions/user-rules/`. Any
   richer rules you added directly to a machine's `~/.claude/CLAUDE.md` (e.g. a
   full lean-ctx ruleset, `RTK.md`) are not all in the repo yet.
2. **`rtk` is not installed or version-controlled here.** If you rely on it,
   install it (and its Claude hook) separately on each machine.
3. **GitNexus** must be indexed per project (`npx gitnexus analyze`).
4. **CI workflow** (`.github/workflows/ci.yml`) is not pushed yet — it needs a
   gh token with the `workflow` scope (`gh auth refresh -h github.com -s workflow`).

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for how the repo is wired internally.

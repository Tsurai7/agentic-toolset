# Plan 04 — evals: make the control/OFF arm a genuinely bare Claude

[Index](00-INDEX.md) · Wave A · Files: `evals/lib/render_config.py`,
`evals/overhead.py`, `evals/swe_bench.py`, `evals/PLAYBOOK.md`,
`evals/BENCHMARKS.md`, `evals/README.md`.

## Context (findings)

**CRITICAL.** The value A/B and the overhead/SWE instruments compare
toolset-ON vs toolset-OFF, but the OFF arm is not ablated:

- Prompt strategy (`render_config.py` ~45–51): both arms share the live config.
  The control is *told* to act as if skills were absent, but the globally
  installed PreToolUse hooks (`shell-guard.sh` on Bash, discovery-gate on Read)
  mechanically enforce the very behaviors under test — a control that cannot
  run a bare `grep` cannot behave "as if ast-grep were not installed". The
  arms converge (consistent with the recorded `rtk … UNRELIABLE 0/3, flip 0.67`).
- Config-dir strategy (~60–64) copies `settings.json`, `.mcp.json`, and
  `CLAUDE.md` verbatim; `~/.claude/CLAUDE.md` imports
  `agentic-cfg.generated.md` by ABSOLUTE path, so the control still loads the
  full Global defaults + hooks; only SKILL.md files are pruned. Yet PLAYBOOK
  labels this "high confidence".
- `overhead.py` (~37–40) and `swe_bench.py` (~45–48) OFF arms are
  prompt-isolated; the nested `claude` inherits `~/.claude` entirely. Hook
  denials inflate OFF-arm tokens/turns, biasing ratios in the toolset's favor.

## Changes

### 1. `render_config.py`: bare control for the config-dir strategy

In the control render:

- `CLAUDE.md`: write an EMPTY file (or omit) — never copy the live one (it
  imports the generated prefix by absolute path).
- `settings.json`: start from the live file but set `"hooks": {}` and drop the
  repo-managed permission allow-list; PRESERVE everything auth/runtime-relevant
  (`env`, `model`, `apiKeyHelper`, `forceLoginMethod`, etc. — copy all keys
  except `hooks` and the managed `permissions.allow` entries).
- MCP: do not register any servers (no `.mcp.json` / no user-scope servers in
  the rendered dir).
- Preserve whatever auth artifacts the config-dir mechanism relies on today
  (e.g. `.credentials.json` if the current code copies the config dir
  wholesale — inspect what `CLAUDE_CONFIG_DIR` consumes and keep ONLY
  auth + the stripped settings).
- The ON arm stays as today (full copy).

### 2. `overhead.py` + `swe_bench.py`: OFF arm uses the bare rendered dir

Replace prompt-only isolation for the OFF arm with
`CLAUDE_CONFIG_DIR=<bare-render>` (reuse the same rendering helper from
`render_config.py` — export a function, don't duplicate). Update the module
docstrings that currently claim the OFF arm is "not wrapped by the live
PreToolUse shell-guard hook" to describe the new mechanism truthfully.

### 3. Honesty updates in docs

- `evals/PLAYBOOK.md` (~124–126): config-dir strategy description — state
  exactly what is now stripped (hooks, CLAUDE.md import, MCP, skills) and keep
  "high confidence" only if AC 3 below passes; the prompt strategy gets an
  explicit caveat: "control arm still runs under any globally-installed hooks;
  low confidence for behaviors a hook enforces".
- `evals/BENCHMARKS.md`: add one footnote line under the table: rows recorded
  before 2026-07-01 used a control arm that inherited global hooks and the
  generated CLAUDE.md prefix; treat PASS/UNRELIABLE accordingly until re-run.
- `evals/README.md`: reflect the OFF-arm mechanism if it describes it.

## Acceptance criteria

1. `python3 evals/run.py --track value` DRY RUN still lists the same cases
   (no case regressions), and `python3 evals/selftest.py` passes.
2. Static proof of bareness: after rendering a control dir (add or use a
   `--render-only` path if one exists; otherwise a 5-line python snippet
   calling the render function), show in your report:
   `jq .hooks <control>/settings.json` → `{}`;
   `cat <control>/CLAUDE.md` → empty/absent;
   no MCP server registration files in the control dir.
3. Behavioral smoke (cheap, uses haiku): run
   `CLAUDE_CONFIG_DIR=<control> claude -p --model claude-haiku-4-5-20251001 "Run exactly this command with the Bash tool and paste its raw output: grep -c def evals/run.py"`
   from the repo root. PASS = the transcript/output shows the command ran
   UNMODIFIED (no `rtk` prefix, no deny message). Run the same probe WITHOUT
   `CLAUDE_CONFIG_DIR` to show the live config still rewrites/denies it
   (that contrast is the whole point). Paste both raw outputs. If auth fails
   inside the bare dir, fix the render (AC 2's auth preservation) rather than
   skipping this check.
4. `python3 evals/overhead.py` dry run and `python3 evals/swe_bench.py --selftest`
   both still pass and their output names the new OFF-arm mechanism.
5. `bash bin/ci-check.sh` exits 0.
6. `git status` touches only the six files in the header (plus any new shared
   helper inside `evals/lib/`).

## Out of scope

Re-running the actual A/B or overhead benchmarks (costs real tokens — deferred,
see [index](00-INDEX.md)). Judge isolation reuses this render in plan 07.

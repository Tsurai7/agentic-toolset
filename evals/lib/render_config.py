"""Prepare the treatment / control arms for an A/B value case.

The control arm must run the SAME prompt with the case's artifact removed, so the
verdict measures that artifact's contribution rather than the agent in general.
There are two isolation strategies, picked automatically:

* prompt  (default, works everywhere): both arms use the real config; the control
          arm gets a prefix instruction to behave as if the ablated artifacts were
          not installed. Cheap and portable, but leakier — the agent still runs
          under any globally-installed PreToolUse hooks, which can mechanically
          enforce the very behavior under test. Verdicts are medium-confidence.

* config-dir (opt-in via AGENTIC_EVAL_ISOLATION=config-dir, needs env-based auth):
          renders an isolated CLAUDE_CONFIG_DIR for the control arm that is a
          genuinely bare Claude: no hooks, no repo-managed permission allow-list,
          no CLAUDE.md import, no MCP servers, and the ablated skills physically
          absent. Only auth-relevant files are carried over. Cleaner,
          high-confidence — but CLAUDE_CONFIG_DIR relocates the whole config,
          which breaks OAuth/Keychain auth, so it only works when auth comes from
          ANTHROPIC_API_KEY in the environment.

The chosen strategy and its confidence are returned so the runner can stamp every
verdict with how much to trust it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_SRC = REPO_ROOT / "core" / "skills"
AGENTS_SRC = REPO_ROOT / "core" / "agents"
REAL_CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
STUB_PATH = REPO_ROOT / "providers" / "claude" / "CLAUDE.md.stub"
AGENTS_MD_PATH = REPO_ROOT / "core" / "instructions" / "AGENTS.md"
PRINCIPLES_SRC = REPO_ROOT / "core" / "principles"
USER_RULES_SRC = REPO_ROOT / "core" / "instructions" / "user-rules"
SETTINGS_FRAGMENT = REPO_ROOT / "providers" / "claude" / "settings.hooks.json"
INTEGRATIONS_SRC = REPO_ROOT / "integrations"

# Valid exclude tokens for render_full_variant() — see its docstring.
FULL_VARIANT_EXCLUDES = frozenset({"lean-ctx", "gitnexus", "shell-guard"})
# exclude token -> MCP server name it drops (matches the server name keys the
# fragments under integrations/ register — see merge-mcp.py's AGENTIC_MCP_EXCLUDE).
_MCP_EXCLUDE_SERVERS = {"lean-ctx": "lean-ctx", "gitnexus": "gitnexus"}


def _load_module(name: str, filename: str):
    """Import a providers/shared/*.py helper by file path (hyphenated filenames,
    not normal package imports) — same technique evals/selftest.py uses to load
    run.py. Re-imported per call; the modules are tiny and this keeps
    render_full_variant() free of import-time side effects on other tests."""
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "providers" / "shared" / filename
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_merge_mcp():
    return _load_module("agentic_merge_mcp", "merge-mcp.py")


def _load_merge_settings():
    return _load_module("agentic_merge_settings", "merge-settings.py")


# Settings keys managed by this repo's install (hooks + the lean-ctx allow-list);
# stripped from the control's settings.json so it enforces nothing repo-specific.
# Everything else (env, model, apiKeyHelper, forceLoginMethod, etc.) is preserved
# verbatim so the control arm still authenticates and runs like a real Claude.
_MANAGED_ALLOW_PREFIXES = ("mcp__lean-ctx__",)
# Auth artifacts the config-dir mechanism relies on when CLAUDE_CONFIG_DIR
# relocates the whole config; carried over untouched so login still works.
_AUTH_FILES = (".credentials.json",)
_KEYCHAIN_SERVICE = "Claude Code-credentials"


def _write_credentials_from_keychain(dest: Path) -> None:
    """On macOS with OAuth/Keychain auth, `.credentials.json` does not exist on
    disk — the CLI reads the OS Keychain instead, keyed by the default config
    path. A relocated CLAUDE_CONFIG_DIR does not see that keychain entry, so the
    control arm would fail to log in (confirmed: an empty rendered dir gets
    "Not logged in"). Extract the same secret the live config already uses and
    materialize it as the file-based credential the CLI also understands.
    Best-effort: silently no-ops when `security` is unavailable or there is no
    matching entry (e.g. Linux, or a machine using ANTHROPIC_API_KEY instead).
    """
    if sys.platform != "darwin":
        return
    try:
        secret = subprocess.run(
            ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if secret.returncode == 0 and secret.stdout.strip():
        dest.write_text(secret.stdout)
        dest.chmod(0o600)


def _bare_settings(src: Path) -> dict:
    """Return the live settings with hooks and the managed allow-list stripped.

    Auth/runtime keys (env, model, apiKeyHelper, forceLoginMethod, etc.) pass
    through untouched — only `hooks` and repo-managed `permissions.allow`
    entries are repo-specific and must not leak into a "bare" control.
    """
    settings = json.loads(src.read_text()) if src.exists() else {}
    settings["hooks"] = {}
    allow = settings.get("permissions", {}).get("allow", [])
    kept = [a for a in allow if not a.startswith(_MANAGED_ALLOW_PREFIXES)]
    if "permissions" in settings:
        settings["permissions"]["allow"] = kept
    return settings


def auth_is_env_based() -> bool:
    """config-dir isolation only survives when auth does not live in the relocated dir."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def strategy() -> str:
    requested = os.environ.get("AGENTIC_EVAL_ISOLATION", "prompt")
    if requested == "config-dir" and auth_is_env_based():
        return "config-dir"
    return "prompt"


# Fixed lead-in of the prompt-strategy ablation prefix (see `_ablation_prefix`).
# A control transcript starts with this text verbatim before the case prompt;
# the judge must never see it (single source of truth for judge.py's stripping).
ABLATION_PREFIX_LEAD = "For this task, behave as if the following capabilities were NOT installed "


def _ablation_prefix(ablate: list[str]) -> str:
    items = ", ".join(ablate)
    return (
        f"{ABLATION_PREFIX_LEAD}"
        f"and are unavailable to you: {items}. Do not use them, mention them, or "
        "route work through them; solve the task as you would without them.\n\n"
    )


def render_bare_control(dest: Path, keep_skills: list[str] | None = None) -> Path:
    """Build a genuinely bare CLAUDE_CONFIG_DIR at `dest`: no hooks, no repo-managed
    permission allow-list, no CLAUDE.md import, no MCP servers, and skills pruned
    down to `keep_skills` (default: none — a fully bare control).

    Shared by the value track's config-dir control arm (`_render_control_config_dir`,
    which keeps the case's non-ablated skills) and the overhead/SWE OFF arm (which
    wants zero skills), so the isolation logic is written once.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # CLAUDE.md must be EMPTY, never the live one — it imports the generated
    # prefix (Global defaults + hooks) by absolute path.
    (dest / "CLAUDE.md").write_text("")
    settings = _bare_settings(REAL_CONFIG / "settings.json")
    (dest / "settings.json").write_text(json.dumps(settings, indent=2))
    # No .mcp.json / no MCP server registration — the control registers nothing.
    # Auth artifacts: carry over only what CLAUDE_CONFIG_DIR relocation needs.
    for name in _AUTH_FILES:
        src = REAL_CONFIG / name
        if src.exists():
            shutil.copy2(src, dest / name)
    creds = dest / ".credentials.json"
    if not creds.exists():
        _write_credentials_from_keychain(creds)
    # Skills: materialize only the ones the caller wants kept (real config
    # symlinks the whole core/skills tree; here we copy a pruned subset).
    keep = set(keep_skills or [])
    skills_out = dest / "skills"
    skills_out.mkdir()
    for skill_dir in sorted(SKILLS_SRC.iterdir()):
        if skill_dir.is_dir() and skill_dir.name in keep:
            shutil.copytree(skill_dir, skills_out / skill_dir.name)
    return dest


def _render_control_config_dir(case: dict, workdir: Path) -> Path:
    """Build the value-track control arm: bare, with the case's non-ablated
    skills kept (only the ablated artifact is removed)."""
    ablate = set(case.get("ablate", []))
    keep = [d.name for d in sorted(SKILLS_SRC.iterdir()) if d.is_dir() and d.name not in ablate]
    return render_bare_control(workdir / "control-config", keep_skills=keep)


def prepare(case: dict, workdir: Path) -> dict:
    """Return arm specs: {treatment, control, strategy, confidence}.

    Each arm spec is {"env": dict, "prefix": str}: env overlays for run_capture,
    and a prompt prefix prepended to the case prompt.
    """
    mode = strategy()
    treatment = {"env": {}, "prefix": ""}

    if mode == "config-dir":
        control_dir = _render_control_config_dir(case, workdir)
        control = {"env": {"CLAUDE_CONFIG_DIR": str(control_dir)}, "prefix": ""}
        confidence = "high"
    else:
        control = {"env": {}, "prefix": _ablation_prefix(case["ablate"])}
        confidence = "medium"

    return {
        "treatment": treatment,
        "control": control,
        "strategy": mode,
        "confidence": confidence,
    }


def _assemble_claude_md() -> str:
    """Byte-for-byte the same assembly order as install.sh:install_claude_md:
    stub (with __AGENTIC_ROOT__ resolved) + AGENTS.md + a Principles section
    (each core/principles/*.md except README.md) + a User rules section (each
    core/instructions/user-rules/*.md except cursor-rules-pointer.md, each
    under a `### <basename>` header)."""
    parts = [STUB_PATH.read_text().replace("__AGENTIC_ROOT__", str(REPO_ROOT))]
    parts.append(AGENTS_MD_PATH.read_text())
    parts.append("\n## Principles (always-on)\n")
    for f in sorted(PRINCIPLES_SRC.glob("*.md")):
        if f.name == "README.md":
            continue
        parts.append("\n" + f.read_text())
    parts.append("\n## User rules\n")
    for f in sorted(USER_RULES_SRC.glob("*.md")):
        if f.name == "cursor-rules-pointer.md":
            continue
        parts.append(f"\n### {f.stem}\n" + f.read_text())
    return "".join(parts)


def _full_settings(exclude: frozenset[str]) -> dict:
    """Merge the resolved hooks fragment onto the SAME preserved live-settings base
    as `_bare_settings`, mirroring install.sh's merge-settings step: the live
    settings.json auth/runtime keys (`env`, `apiKeyHelper`, `forceLoginMethod`,
    `model`, ...) pass through untouched while the repo's hook groups and
    `mcp__lean-ctx__*` allow entries are merged on top (via merge-settings.py's
    own `merge_hooks`/`_merge_allow`, the single source of merge truth). Overwriting
    with only the fragment would drop those auth keys and leave the full arm on a
    different auth footing than the bare control.

    Exclusions are applied to the fragment before the merge, mirroring install.sh's
    AGENTIC_TIER=weak settings transform: "shell-guard" removes the `^Bash$` matcher
    group; "lean-ctx" removes the `lean-ctx hook redirect` group and every
    `mcp__lean-ctx__*` allow entry."""
    resolved = SETTINGS_FRAGMENT.read_text().replace("__AGENTIC_ROOT__", str(REPO_ROOT))
    fragment = json.loads(resolved)
    if "shell-guard" in exclude:
        pre = fragment.get("hooks", {}).get("PreToolUse", [])
        fragment["hooks"]["PreToolUse"] = [g for g in pre if g.get("matcher") != "^Bash$"]
    if "lean-ctx" in exclude:
        pre = fragment.get("hooks", {}).get("PreToolUse", [])
        fragment["hooks"]["PreToolUse"] = [
            g for g in pre
            if not any("lean-ctx hook redirect" in h.get("command", "") for h in g.get("hooks", []))
        ]
        allow = fragment.get("permissions", {}).get("allow", [])
        fragment["permissions"]["allow"] = [a for a in allow if not a.startswith("mcp__lean-ctx__")]

    merge_settings = _load_merge_settings()
    src = REAL_CONFIG / "settings.json"
    settings = json.loads(src.read_text()) if src.exists() else {}
    schema = fragment.get("$schema")
    if schema is not None:
        settings.setdefault("$schema", schema)
    if "hooks" in fragment:
        settings["hooks"] = merge_settings.merge_hooks(settings.get("hooks") or {}, fragment["hooks"])
    perms = settings.get("permissions") or {}
    settings["permissions"] = perms
    perms["allow"] = merge_settings._merge_allow(perms.get("allow", []) or [], fragment)
    perms.setdefault("deny", [])
    return settings


def _full_mcp_config(dest: Path, exclude: frozenset[str]) -> str | None:
    """Build a `claude --mcp-config`-compatible {"mcpServers": {...}} from this
    repo's MCP fragments, minus excluded servers, and write it to
    dest/mcp-config.json. Reuses providers/shared/merge-mcp.py's
    collect_fragments/load_env/substitute (the same fragment discovery,
    __AGENTIC_ROOT__/__PATH__-style placeholder resolution, and
    Claude-Code-compatible key filtering the installer's merge path uses)
    rather than re-implementing them. Returns None when every server is
    excluded (nothing to load).

    Exclusions are driven ONLY by the explicit `exclude` argument: ambient
    AGENTIC_MCP_EXCLUDE (which `collect_fragments` honors internally, e.g.
    inherited from a weak-tier install shell) is cleared for the collect so it
    cannot silently drop servers and quietly make the 'full' arm not-full."""
    merge_mcp = _load_merge_mcp()
    exclude_servers = {_MCP_EXCLUDE_SERVERS[tok] for tok in exclude if tok in _MCP_EXCLUDE_SERVERS}
    ambient_exclude = os.environ.pop("AGENTIC_MCP_EXCLUDE", None)
    try:
        all_servers = merge_mcp.collect_fragments(INTEGRATIONS_SRC).get("mcpServers", {})
    finally:
        if ambient_exclude is not None:
            os.environ["AGENTIC_MCP_EXCLUDE"] = ambient_exclude
    fragments = {
        "mcpServers": {
            name: cfg for name, cfg in all_servers.items()
            if name not in exclude_servers
        }
    }
    env = merge_mcp.load_env(REPO_ROOT)
    resolved = merge_mcp.substitute(fragments, env)
    servers = {
        name: merge_mcp._claude_server_config(cfg)
        for name, cfg in resolved.get("mcpServers", {}).items()
    }
    if not servers:
        return None
    out = dest / "mcp-config.json"
    out.write_text(json.dumps({"mcpServers": servers}, indent=2))
    return str(out)


def render_full_variant(dest: Path, exclude: frozenset[str] = frozenset()) -> dict:
    """Render TODAY'S complete config into an isolated CLAUDE_CONFIG_DIR, minus the
    named exclusions. Returns {"config_dir": str, "mcp_config": str|None} — the
    caller passes config_dir via CLAUDE_CONFIG_DIR and mcp_config via
    `claude --mcp-config` (see swe_bench.py's arms axis). Valid exclude tokens:
    "lean-ctx", "gitnexus", "shell-guard". Unknown tokens -> ValueError (fail
    loud, not open: a typo'd/renamed exclude token must never silently render a
    still-full arm and be mistaken for an ablated one).

    Fidelity note: this isolated arm intentionally differs from the live
    machine in exactly one way — MCP servers are loaded via `--mcp-config`
    (this function's mcp_config output) rather than the live ~/.claude.json
    user-scope registration the real installer uses. Everything else (CLAUDE.md
    assembly, settings.json hooks/permissions, skills/agents) mirrors
    providers/claude/install.sh's live-install behavior exactly, just written
    into `dest` instead of ~/.claude.
    """
    unknown = exclude - FULL_VARIANT_EXCLUDES
    if unknown:
        raise ValueError(
            f"render_full_variant: unknown exclude token(s) {sorted(unknown)}; "
            f"valid tokens are {sorted(FULL_VARIANT_EXCLUDES)}"
        )
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "CLAUDE.md").write_text(_assemble_claude_md())
    settings = _full_settings(exclude)
    (dest / "settings.json").write_text(json.dumps(settings, indent=2))
    (dest / "skills").symlink_to(SKILLS_SRC)
    (dest / "agents").symlink_to(AGENTS_SRC)
    for name in _AUTH_FILES:
        src = REAL_CONFIG / name
        if src.exists():
            shutil.copy2(src, dest / name)
    creds = dest / ".credentials.json"
    if not creds.exists():
        _write_credentials_from_keychain(creds)
    mcp_config = _full_mcp_config(dest, exclude)
    return {"config_dir": str(dest), "mcp_config": mcp_config}

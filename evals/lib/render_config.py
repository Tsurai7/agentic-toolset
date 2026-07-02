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

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_SRC = REPO_ROOT / "core" / "skills"
REAL_CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))

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

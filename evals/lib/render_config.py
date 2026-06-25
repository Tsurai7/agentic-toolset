"""Prepare the treatment / control arms for an A/B value case.

The control arm must run the SAME prompt with the case's artifact removed, so the
verdict measures that artifact's contribution rather than the agent in general.
There are two isolation strategies, picked automatically:

* prompt  (default, works everywhere): both arms use the real config; the control
          arm gets a prefix instruction to behave as if the ablated artifacts were
          not installed. Cheap and portable, but leakier — the agent is *asked* to
          ignore a skill rather than not having it. Verdicts are medium-confidence.

* config-dir (opt-in via AGENTIC_EVAL_ISOLATION=config-dir, needs env-based auth):
          renders an isolated CLAUDE_CONFIG_DIR for the control arm with the ablated
          skills physically absent. Cleaner, high-confidence — but CLAUDE_CONFIG_DIR
          relocates the whole config, which breaks OAuth/Keychain auth, so it only
          works when auth comes from ANTHROPIC_API_KEY in the environment.

The chosen strategy and its confidence are returned so the runner can stamp every
verdict with how much to trust it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_SRC = REPO_ROOT / "core" / "skills"
REAL_CONFIG = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def auth_is_env_based() -> bool:
    """config-dir isolation only survives when auth does not live in the relocated dir."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def strategy() -> str:
    requested = os.environ.get("AGENTIC_EVAL_ISOLATION", "prompt")
    if requested == "config-dir" and auth_is_env_based():
        return "config-dir"
    return "prompt"


def _ablation_prefix(ablate: list[str]) -> str:
    items = ", ".join(ablate)
    return (
        "For this task, behave as if the following capabilities were NOT installed "
        f"and are unavailable to you: {items}. Do not use them, mention them, or "
        "route work through them; solve the task as you would without them.\n\n"
    )


def _render_control_config_dir(case: dict, workdir: Path) -> Path:
    """Build an isolated config dir with the ablated skills physically removed."""
    arm = workdir / "control-config"
    if arm.exists():
        shutil.rmtree(arm)
    arm.mkdir(parents=True)
    # Seed the bits an agent run needs; auth is expected from the environment.
    for name in ("settings.json", ".mcp.json", "CLAUDE.md"):
        src = REAL_CONFIG / name
        if src.exists():
            shutil.copy2(src, arm / name)
    # Skills: copy the inventory minus the ablated ones (real config symlinks the
    # whole core/skills tree; here we materialize a pruned copy).
    skills_out = arm / "skills"
    skills_out.mkdir()
    ablate = set(case.get("ablate", []))
    for skill_dir in sorted(SKILLS_SRC.iterdir()):
        if skill_dir.is_dir() and skill_dir.name not in ablate:
            shutil.copytree(skill_dir, skills_out / skill_dir.name)
    return arm


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

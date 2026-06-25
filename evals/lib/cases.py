"""Case loading and schema validation for both tracks.

A single source of truth for what a valid case looks like, imported by run.py
(to load) and lint.py (to validate cheaply in CI without spending tokens).
"""

from __future__ import annotations

import json
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent
CONFORMANCE_DIR = EVALS_DIR / "conformance" / "cases"
VALUE_DIR = EVALS_DIR / "value" / "cases"

PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse"}


def _track_dir(track: str) -> Path:
    return {"conformance": CONFORMANCE_DIR, "value": VALUE_DIR}[track]


def load(track: str) -> list[dict]:
    """Load and tag every case file in a track, sorted by id."""
    out = []
    for p in sorted(_track_dir(track).glob("*.json")):
        case = json.loads(p.read_text("utf-8"))
        case["_track"] = track
        case["_path"] = str(p)
        out.append(case)
    return out


def validate(case: dict, track: str) -> list[str]:
    """Return a list of human-readable schema errors (empty ⇒ valid)."""
    errors: list[str] = []

    def require(key: str, typ: type) -> None:
        if key not in case:
            errors.append(f"missing required key '{key}'")
        elif not isinstance(case[key], typ):
            errors.append(f"key '{key}' must be {typ.__name__}")

    require("id", str)
    require("prompt", str)

    if track == "conformance":
        require("rule", str)
        has_expect = bool(case.get("expect")) or bool(case.get("expect_not"))
        if not has_expect:
            errors.append("conformance case needs a non-empty 'expect' or 'expect_not'")
    elif track == "value":
        require("hypothesis", str)
        require("skill", str)
        require("ablate", list)
        require("rubric", list)
        pc = case.get("pass_condition")
        if pc not in PASS_CONDITIONS:
            errors.append(f"'pass_condition' must be one of {sorted(PASS_CONDITIONS)}")
        if not case.get("rubric"):
            errors.append("value case needs a non-empty 'rubric'")
        if not case.get("ablate"):
            errors.append("value case needs a non-empty 'ablate' (what to remove for control)")
    else:
        errors.append(f"unknown track '{track}'")

    return errors

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
METRIC_DIR = EVALS_DIR / "metric" / "cases"

PASS_CONDITIONS = {"treatment_preferred", "treatment_not_worse"}
METRIC_OPS = {">=", "<=", ">", "<"}

# Keys load()/load_reporting() stamp onto every case dict — not part of the
# on-disk schema, but always present by the time validate() sees a case.
_LOADER_KEYS = {"_track", "_path"}

# Every top-level key a case file is allowed to use, per track. Audited from
# evals/{conformance,value,metric}/cases/*.json — keep in sync when a new
# field is introduced, so a typo (e.g. "expects") is rejected instead of
# silently ignored.
ALLOWED_KEYS = {
    "conformance": {"id", "prompt", "rule", "expect", "expect_not"} | _LOADER_KEYS,
    "value": {"id", "prompt", "hypothesis", "skill", "ablate", "rubric", "pass_condition", "n"} | _LOADER_KEYS,
    "metric": {"id", "rule", "metric", "op", "threshold", "min_tokens", "window_sessions"} | _LOADER_KEYS,
}


def _track_dir(track: str) -> Path:
    return {"conformance": CONFORMANCE_DIR, "value": VALUE_DIR, "metric": METRIC_DIR}[track]


class CaseLoadError(Exception):
    """A case file could not be read as a JSON object — carries the offending path.

    The merge scripts already name the bad file (merge-mcp.load_json); the eval
    loaders used a bare json.loads, so one typo'd case aborted the whole lint/run
    with an opaque traceback and no filename (BUG-22). This makes the failure
    legible instead.
    """


def _read_case(p: Path) -> dict:
    """Read one case file, raising CaseLoadError(path: reason) on any problem."""
    try:
        case = json.loads(p.read_text("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise CaseLoadError(f"{p}: invalid JSON: {exc}") from exc
    if not isinstance(case, dict):
        raise CaseLoadError(f"{p}: expected a JSON object at top level, got {type(case).__name__}")
    return case


def load(track: str) -> list[dict]:
    """Load and tag every case file in a track, sorted by id.

    Raises CaseLoadError naming the offending file on the first malformed case
    (fail-fast — used by run.py before spending tokens). Linters that want to
    report *every* bad file should use load_reporting() instead.
    """
    out = []
    for p in sorted(_track_dir(track).glob("*.json")):
        case = _read_case(p)
        case["_track"] = track
        case["_path"] = str(p)
        out.append(case)
    return out


def load_reporting(track: str) -> tuple[list[dict], list[str]]:
    """Like load() but collect per-file load errors instead of raising, so a
    linter reports every malformed file (named) and still validates the good ones."""
    loaded: list[dict] = []
    errors: list[str] = []
    for p in sorted(_track_dir(track).glob("*.json")):
        try:
            case = _read_case(p)
        except CaseLoadError as exc:
            errors.append(str(exc))
            continue
        case["_track"] = track
        case["_path"] = str(p)
        loaded.append(case)
    return loaded, errors


def validate(case: dict, track: str) -> list[str]:
    """Return a list of human-readable schema errors (empty ⇒ valid)."""
    errors: list[str] = []

    def require(key: str, typ: type) -> None:
        if key not in case:
            errors.append(f"missing required key '{key}'")
        elif not isinstance(case[key], typ):
            errors.append(f"key '{key}' must be {typ.__name__}")

    require("id", str)

    if track in ALLOWED_KEYS:
        unknown = set(case) - ALLOWED_KEYS[track]
        for key in sorted(unknown):
            errors.append(f"unknown key '{key}'")

    if track == "conformance":
        require("prompt", str)
        require("rule", str)
        has_expect = bool(case.get("expect")) or bool(case.get("expect_not"))
        if not has_expect:
            errors.append("conformance case needs a non-empty 'expect' or 'expect_not'")
    elif track == "value":
        require("prompt", str)
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
    elif track == "metric":
        # A metric case asserts a number from local telemetry against a
        # threshold — no agent run, so no 'prompt'.
        require("rule", str)
        require("metric", str)
        require("op", str)
        if not isinstance(case.get("threshold"), (int, float)):
            errors.append("metric case needs a numeric 'threshold'")
        if case.get("op") not in METRIC_OPS:
            errors.append(f"'op' must be one of {sorted(METRIC_OPS)}")
    else:
        errors.append(f"unknown track '{track}'")

    return errors

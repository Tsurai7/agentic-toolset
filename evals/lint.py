#!/usr/bin/env python3
"""Static checks for the eval suite — zero tokens, safe for CI on every PR.

This is what mechanically enforces the loop in PLAYBOOK.md: every case validates
against its schema, ids are unique, value cases ablate real skills, and every
skill under core/skills/ is covered by at least one case. A skill with no eval is
an undefended claim, so this fails the build.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import cases  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "core" / "skills"
# Skills generated/owned by external tools (gitignored), not authored here.
COVERAGE_EXEMPT = {"no-mistakes"}


def _skill_names() -> set[str]:
    return {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}


def main() -> int:
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    covered: set[str] = set()
    skills = _skill_names()

    for track in ("conformance", "value", "metric"):
        track_cases, load_errors = cases.load_reporting(track)
        errors.extend(f"{track}: {e}" for e in load_errors)
        for case in track_cases:
            cid = case.get("id", "<no-id>")
            loc = f"{track}:{cid}"

            for err in cases.validate(case, track):
                errors.append(f"{loc}: {err}")

            if cid in seen_ids:
                errors.append(f"{loc}: duplicate id (also in {seen_ids[cid]})")
            else:
                seen_ids[cid] = loc

            if track == "value":
                for target in case.get("ablate", []):
                    if target not in skills:
                        errors.append(f"{loc}: ablate target '{target}' is not a skill in core/skills/")
                if case.get("skill") in skills:
                    covered.add(case["skill"])
            elif track == "conformance":
                # Best-effort coverage credit: a skill named in the rule text.
                for s in skills:
                    if s in (case.get("rule", "") + " " + cid):
                        covered.add(s)

    uncovered = skills - covered - COVERAGE_EXEMPT
    for s in sorted(uncovered):
        errors.append(f"coverage: skill '{s}' has no eval case (add a conformance or value case)")

    if errors:
        print("LINT FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"lint OK — {len(seen_ids)} cases, {len(skills)} skills covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

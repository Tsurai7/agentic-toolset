#!/usr/bin/env python3
"""Memory hygiene linter (Phase 2).

Validates memory files — the version-controlled seeds by default, or the live
per-project stores under ~/.claude/projects with --live. Stdlib only, zero
tokens, so it can run in a static-check pipeline or a pre-commit hook.

Checks per memory directory:
  - every *.md (except MEMORY.md) has frontmatter with `name`, `description`,
    and `metadata.type` in {user, feedback, project, reference};
  - `name` matches the filename slug;
  - MEMORY.md and the fact files agree: no index entry points at a missing
    file, no fact file is missing from the index;
  - [[wikilinks]] resolve to a fact file in the same dir (unresolved ones are
    warnings, not errors — they mark a memory worth writing later).

Usage:
    python3 core/memory/lint.py                 # lint seeds/ (tracked)
    python3 core/memory/lint.py --live          # lint ~/.claude/projects/*/memory
    python3 core/memory/lint.py --dir <path>    # lint one memory dir

Exit codes: 0 clean (warnings allowed), 1 errors found, 2 bad usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ALLOWED_TYPES = {"user", "feedback", "project", "reference"}
LINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9-]*)\]\]")
INDEX_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


def parse_frontmatter(text: str) -> dict | None:
    """Minimal YAML-frontmatter reader for the known memory schema."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    out: dict = {}
    in_metadata = False
    for raw in block.splitlines():
        if not raw.strip():
            continue
        indented = raw[0] in " \t"
        key, _, val = raw.strip().partition(":")
        key = key.strip()
        val = val.strip()
        if key == "metadata" and not val:
            in_metadata = True
            continue
        if in_metadata and indented:
            out[f"metadata.{key}"] = val
        else:
            in_metadata = False
            out[key] = val
    return out


def lint_dir(d: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    facts = sorted(p for p in d.glob("*.md")
                   if p.name != "MEMORY.md" and not p.name.startswith("_"))
    fact_slugs = {p.stem for p in facts}

    for p in facts:
        text = p.read_text(errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            errors.append(f"{p}: missing or malformed frontmatter")
            continue
        if not fm.get("name"):
            errors.append(f"{p}: frontmatter missing `name`")
        elif fm["name"] != p.stem:
            errors.append(f"{p}: name '{fm['name']}' != filename slug '{p.stem}'")
        if not fm.get("description"):
            errors.append(f"{p}: frontmatter missing `description`")
        mtype = fm.get("metadata.type")
        if mtype not in ALLOWED_TYPES:
            errors.append(f"{p}: metadata.type '{mtype}' not in {sorted(ALLOWED_TYPES)}")
        for slug in LINK_RE.findall(text):
            if slug not in fact_slugs:
                warnings.append(f"{p}: [[{slug}]] has no matching file (yet)")

    index = d / "MEMORY.md"
    if not index.exists():
        if facts:
            errors.append(f"{d}: has fact files but no MEMORY.md index")
    else:
        linked = {Path(m).stem for m in INDEX_LINK_RE.findall(index.read_text(errors="replace"))}
        for slug in linked - fact_slugs:
            errors.append(f"{index}: links '{slug}.md' which does not exist")
        for slug in fact_slugs - linked:
            errors.append(f"{index}: missing index entry for '{slug}.md'")

    return errors, warnings


def discover_dirs(args) -> list[Path]:
    if args.dir:
        return [Path(args.dir)]
    if args.live:
        root = Path(os.path.expanduser("~/.claude/projects"))
        return sorted(p for p in root.glob("*/memory") if p.is_dir())
    return [Path(__file__).resolve().parent / "seeds"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="lint live ~/.claude/projects/*/memory dirs")
    ap.add_argument("--dir", help="lint a single memory directory")
    args = ap.parse_args()

    dirs = discover_dirs(args)
    if not dirs:
        print("no memory directories found.")
        return 0

    total_err = 0
    for d in dirs:
        if not d.exists():
            continue
        errors, warnings = lint_dir(d)
        if errors or warnings:
            print(f"== {d} ==")
            for w in warnings:
                print(f"  warn: {w}")
            for e in errors:
                print(f"  ERROR: {e}")
        total_err += len(errors)

    print(f"\n{total_err} error(s) across {len(dirs)} dir(s).")
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())

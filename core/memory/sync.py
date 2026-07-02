#!/usr/bin/env python3
"""Seed cross-project memory (Phase 2).

Distributes version-controlled `user`/`feedback` seed facts from
core/memory/seeds/ into the live per-project memory stores under
~/.claude/projects, so cross-project facts (who you are, how you want the agent
to work) are recalled everywhere instead of being trapped in one project's silo.

Design decisions (see POLICY.md):
  - Active projects only: a project counts as active if it has a transcript
    (*.jsonl) modified within --active-days (default 30). Dead/scratch projects
    are skipped.
  - Merge by name, never clobber: a seed is written only if no fact with the
    same `name` slug already exists in the target. Local edits and locally
    authored facts are never overwritten or deleted.
  - Templates excluded: files whose name starts with `_` are skipped.
  - Dry-run by default: prints the plan; pass --apply to write.

Usage:
    python3 core/memory/sync.py                 # dry-run plan
    python3 core/memory/sync.py --apply         # write seeds + update indexes
    python3 core/memory/sync.py --active-days 60

Exit codes: 0 ok, 2 bad usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

# Reuse the merge scripts' atomic writer (providers/shared/safe_io.py) so a crash
# mid-write can never leave a half-written or empty live memory file.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "providers" / "shared"))
from safe_io import atomic_write_text  # noqa: E402

INDEX_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def seed_files(seeds_dir: Path) -> list[Path]:
    return sorted(p for p in seeds_dir.glob("*.md")
                  if p.name != "MEMORY.md" and not p.name.startswith("_"))


def active_projects(root: Path, active_days: int) -> list[Path]:
    cutoff = time.time() - active_days * 86400
    out = []
    for proj in sorted(root.glob("*")):
        if not proj.is_dir():
            continue
        if any(j.stat().st_mtime >= cutoff for j in proj.glob("*.jsonl")):
            out.append(proj)
    return out


def existing_slugs(mem_dir: Path) -> set[str]:
    return {p.stem for p in mem_dir.glob("*.md") if p.name != "MEMORY.md"}


def index_line(seed: Path) -> str:
    m = DESC_RE.search(seed.read_text(errors="replace"))
    hook = m.group(1).strip() if m else seed.stem
    return f"- [{seed.stem}]({seed.name}) — {hook}"


def ensure_index(mem_dir: Path, new_seeds: list[Path], apply: bool) -> list[str]:
    index = mem_dir / "MEMORY.md"
    existing = index.read_text(errors="replace") if index.exists() else "# Memory index\n"
    linked = {Path(m).name for m in INDEX_LINK_RE.findall(existing)}
    additions = [index_line(s) for s in new_seeds if s.name not in linked]
    if additions and apply:
        body = existing.rstrip("\n") + "\n" + "\n".join(additions) + "\n"
        atomic_write_text(index, body)
    return additions


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=str(Path(__file__).resolve().parent / "seeds"))
    ap.add_argument("--projects-root", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--active-days", type=int, default=30)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = ap.parse_args()

    seeds_dir = Path(args.seeds)
    root = Path(args.projects_root)
    if not seeds_dir.exists():
        print(f"seeds dir not found: {seeds_dir}", file=sys.stderr)
        return 2
    if not root.exists():
        # Fresh machine: Claude Code has never run, so there are zero active
        # projects to seed into. Not an error — degrade to a no-op so a fresh
        # `bin/install.sh --provider all` completes instead of aborting at exit 2.
        print(f"projects root not present yet ({root}); nothing to seed", file=sys.stderr)
        return 0

    seeds = seed_files(seeds_dir)
    projects = active_projects(root, args.active_days)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] {len(seeds)} seed(s) -> {len(projects)} active project(s) "
          f"(active within {args.active_days}d)\n")

    if not seeds:
        print("No real seeds yet (only templates). Mechanism is ready; add "
              "user/feedback facts under seeds/ to distribute them.")
        return 0

    for proj in projects:
        mem = proj / "memory"
        have = existing_slugs(mem) if mem.exists() else set()
        to_add = [s for s in seeds if s.stem not in have]
        if not to_add:
            continue
        print(f"{proj.name}:")
        for s in to_add:
            print(f"  + {s.name}")
            if args.apply:
                mem.mkdir(parents=True, exist_ok=True)
                atomic_write_text(mem / s.name, s.read_text(errors="replace"))
        added_idx = ensure_index(mem, to_add, args.apply)
        for line in added_idx:
            print(f"    index: {line}")

    if not args.apply:
        print("\n(dry-run) re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

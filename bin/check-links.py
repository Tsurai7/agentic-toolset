#!/usr/bin/env python3
"""Verify that relative Markdown links in tracked docs actually resolve.

The repo cross-links heavily (docs/, plans/, skills, READMEs). A moved or renamed
file silently breaks those links; this catches it. Zero deps, safe for CI.

Checks every tracked *.md file for inline links `](target)` where target is a
relative path (http(s)://, mailto:, and bare #anchors are skipped). The target's
optional `#anchor` and `:line` suffixes are stripped, then it is resolved relative
to the linking file and checked for existence (file or directory).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# ](target) — capture up to the first ) or whitespace; ignore images? images also
# resolve to real files, so include them. Skip autolinks/reference-style.
LINK_RE = re.compile(r"\]\(\s*([^)\s]+)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")
# Markdown link syntax inside code is not a link (e.g. a Python `d["k"](x, y)`),
# so strip fenced and inline code spans before extracting links.
FENCE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    text = FENCE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def tracked_md() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.md", "**/*.md"],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout
        files = [REPO / line for line in out.splitlines() if line.strip()]
        if files:
            return sorted(set(files))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # Fallback: walk the tree, skipping .git.
    return sorted(p for p in REPO.rglob("*.md") if ".git/" not in str(p))


def link_targets(text: str) -> list[str]:
    out = []
    for m in LINK_RE.finditer(text):
        target = m.group(1).strip()
        if not target or target.lower().startswith(SKIP_PREFIXES):
            continue
        out.append(target)
    return out


def resolve(md_file: Path, target: str) -> Path:
    # Drop a #fragment and a trailing :line (e.g. foo.ts:42).
    target = target.split("#", 1)[0]
    target = re.sub(r":\d+(-\d+)?$", "", target)
    if not target:
        return md_file  # pure anchor that slipped through → treat as present
    return (md_file.parent / target).resolve()


def main() -> int:
    broken: list[str] = []
    checked = 0
    for md in tracked_md():
        try:
            text = md.read_text("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel_md = md.relative_to(REPO)
        for target in link_targets(strip_code(text)):
            checked += 1
            dest = resolve(md, target)
            if not dest.exists():
                broken.append(f"{rel_md} -> {target}")
    if broken:
        print("BROKEN LINKS:")
        for b in broken:
            print(f"  - {b}")
        return 1
    print(f"link check OK — {checked} relative links across {len(tracked_md())} files resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

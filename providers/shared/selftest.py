#!/usr/bin/env python3
"""Self-tests for the shared merge helpers — zero deps, runs in bin/ci-check.sh.

The merge scripts had no Python-level tests (only the Go parity test exercised
them end-to-end). This guards the filesystem-safety invariant directly: a merge
must never corrupt the user's live config, even if interrupted mid-write.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import safe_io  # noqa: E402


def test_atomic_write_replaces_existing():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "settings.json"
        target.write_text("OLD", encoding="utf-8")
        safe_io.atomic_write_text(target, "NEW")
        assert target.read_text(encoding="utf-8") == "NEW"
        leftovers = [p.name for p in Path(d).iterdir() if p.name != "settings.json"]
        assert leftovers == [], f"temp file leaked: {leftovers}"


def test_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "nested" / "deep" / "mcp.json"
        safe_io.atomic_write_text(target, "{}\n")
        assert target.read_text(encoding="utf-8") == "{}\n"


def test_failed_write_leaves_original_intact():
    # Simulate a crash between temp-write and rename. The live file must survive
    # byte-for-byte and no temp file may leak — the whole point of BUG-12's fix.
    real_replace = os.replace

    def boom(src, dst):
        raise KeyboardInterrupt("killed mid-write")

    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "mcp.json"
        target.write_text("ORIGINAL", encoding="utf-8")
        os.replace = boom
        try:
            safe_io.atomic_write_text(target, "HALF-WRITTEN GARBAGE")
        except KeyboardInterrupt:
            pass
        finally:
            os.replace = real_replace
        assert target.read_text(encoding="utf-8") == "ORIGINAL", "non-atomic write corrupted the live file"
        leftovers = [p.name for p in Path(d).iterdir() if p.name != "mcp.json"]
        assert leftovers == [], f"temp file leaked after failure: {leftovers}"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"merge-helpers selftest OK — {len(tests)} checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

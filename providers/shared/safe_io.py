#!/usr/bin/env python3
"""Shared filesystem helpers for the merge scripts.

The merge tools write the user's *live* provider config (~/.claude/settings.json,
~/.cursor/mcp.json). A plain ``path.write_text(...)`` truncates the target before
writing, so an interruption (Ctrl-C, OOM, crash) between truncate and flush leaves
the user with an empty or half-written config that Claude/Cursor then fails to load
(BUG-12). The Go path already writes atomically (internal/jsonorder.WriteFile); this
brings the Python fallback to parity.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` atomically.

    The bytes are written and fsync'd to a temp file in the *same directory*, then
    ``os.replace()``'d over the target — an atomic rename on the same filesystem.
    On any failure the temp file is removed and the original target is left exactly
    as it was, so a crashed merge never corrupts the user's live config.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".agentic-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Leave the original target untouched; clean up the temp file.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

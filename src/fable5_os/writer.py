"""Safely write generated code files to a sandboxed output directory.

LLM-produced paths are untrusted. Every path is normalized and confined under a
single base directory; anything that would escape (absolute paths, ``..``,
drive letters) is rejected rather than written.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from .schemas import GeneratedFile


class UnsafePathError(ValueError):
    """Raised when a generated path would escape the output directory."""


def _safe_relative_path(raw: str) -> Path:
    # Reject absolute paths and Windows drive letters up front.
    candidate = raw.strip().replace("\\", "/").lstrip("/")
    if not candidate:
        raise UnsafePathError("empty path")
    p = Path(candidate)
    if p.is_absolute() or (len(candidate) >= 2 and candidate[1] == ":"):
        raise UnsafePathError(f"absolute path not allowed: {raw!r}")
    if any(part == ".." for part in p.parts):
        raise UnsafePathError(f"'..' not allowed in path: {raw!r}")
    return p


def write_files(files: List[GeneratedFile], base_dir: str) -> List[Dict[str, Any]]:
    """Write each file under ``base_dir``. Returns a per-file result record.

    A single bad or unwritable file does not abort the batch — it is recorded
    with its error so the caller can report it.
    """

    base = Path(base_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    results: List[Dict[str, Any]] = []

    for f in files:
        try:
            rel = _safe_relative_path(f.path)
            target = (base / rel).resolve()
            # Final defense: confirm the resolved path is still inside base.
            if os.path.commonpath([str(base), str(target)]) != str(base):
                raise UnsafePathError(f"path escapes output dir: {f.path!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content, encoding="utf-8")
            results.append({"path": str(rel).replace("\\", "/"), "written": True, "error": None})
        except Exception as exc:  # keep going; report the failure
            results.append({"path": f.path, "written": False, "error": f"{type(exc).__name__}: {exc}"})

    return results

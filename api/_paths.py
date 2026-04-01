from __future__ import annotations

from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def safe_relpath(p: str) -> str:
    """
    Normalize a user-provided relative path and block traversal.
    Returns '' if invalid.
    """
    p = str(p or "").replace("\\", "/").lstrip("/")
    if not p:
        return ""
    # block traversal
    if ".." in p.split("/"):
        return ""
    return p


def resolve_under_root(rel: str, root: Path = PROJECT_ROOT) -> Optional[Path]:
    """
    Resolve a relative path under project root and ensure it does not escape.
    Returns None if invalid/outside root.
    """
    rel = safe_relpath(rel)
    if not rel:
        return None
    root_r = root.resolve()
    fp = (root_r / rel).resolve()
    try:
        fp.relative_to(root_r)
    except Exception:
        return None
    return fp


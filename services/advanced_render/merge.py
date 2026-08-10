"""Merge and downsample multiple point clouds."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np


def merge_point_clouds(
    parts: List[Tuple[np.ndarray, np.ndarray, Dict[str, Any]]],
    max_total: int,
    per_source_cap: int | None = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    parts: list of (positions Nx3 float32, colors Nx3 uint8, meta dict with 'id' optional)
    """
    cap = per_source_cap or max_total
    trimmed: List[Tuple[np.ndarray, np.ndarray, Dict[str, Any]]] = []
    per_counts: Dict[str, int] = {}
    for pos, col, meta in parts:
        if pos is None or pos.size == 0:
            continue
        n = pos.shape[0]
        sid = str(meta.get("id", meta.get("source", "unknown")))
        if n > cap:
            idx = np.random.choice(n, cap, replace=False)
            pos = pos[idx]
            col = col[idx]
            n = cap
        trimmed.append((pos, col, meta))
        per_counts[sid] = per_counts.get(sid, 0) + n

    if not trimmed:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros((0, 3), dtype=np.uint8),
            {"per_source": {}, "total": 0},
        )

    all_pos = np.concatenate([p[0] for p in trimmed], axis=0)
    all_col = np.concatenate([p[1] for p in trimmed], axis=0)
    total = all_pos.shape[0]
    if total > max_total:
        idx = np.random.choice(total, max_total, replace=False)
        all_pos = all_pos[idx]
        all_col = all_col[idx]
        total = max_total

    return all_pos, all_col, {"per_source": per_counts, "total": total}

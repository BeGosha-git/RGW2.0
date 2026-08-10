"""Last merged-scene stats for /api/robot/advanced_world/stats."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict

_lock = threading.Lock()
_stats: Dict[str, Any] = {
    "updated_at": 0.0,
    "merge": {},
    "per_source": {},
    "cv": {},
    "world_path": "",
}


def set_stats(
    merge_meta: Dict[str, Any],
    cv_stats: Dict[str, Any] | None = None,
    world_path: str = "",
) -> None:
    with _lock:
        _stats["updated_at"] = time.time()
        _stats["merge"] = dict(merge_meta or {})
        _stats["per_source"] = dict((merge_meta or {}).get("per_source") or {})
        if cv_stats is not None:
            _stats["cv"] = dict(cv_stats)
        if world_path:
            _stats["world_path"] = world_path


def get_stats() -> Dict[str, Any]:
    with _lock:
        return dict(_stats)

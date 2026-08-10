"""Load and validate advanced world JSON (sources, merge, view, robot overlay)."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_WORLD_REL = "data/advanced_world.json"

# Шаблон для записи на диск при первом запуске (совпадает с рекомендуемым data/advanced_world.json).
SHIPPED_ADVANCED_WORLD: Dict[str, Any] = {
    "version": 1,
    "merge": {
        "max_total_points": 45000,
        "per_source_cap": 22000,
        "plane_snap": True,
        "plane_snap_tolerance_rel": 0.1,
        "plane_snap_max_planes": 8,
        "plane_snap_knn_scale": 2.5,
        "plane_snap_knn_k": 8,
        "plane_snap_cooldown_sec": 10.0,
        "plane_snap_seed_tries": 36,
        "plane_snap_link_edge_factor": 1.65,
        "plane_snap_link_bridge_k": 2.85,
        "plane_snap_eps_l_factor": 0.16,
        "plane_snap_eps_knn_factor": 1.75,
        "plane_snap_expand_iters": 12,
        "plane_snap_expand_radius_mul": 1.45,
        "plane_snap_expand_min_bridge_k": 2.65,
        "plane_snap_working_points": 14000,
    },
    "view": {
        "yaw": 0.0,
        "pitch": 1.0471975511965976,
        "z_near": 0.25,
        "z_far": 3.5,
        "point_step": 4,
        "low_density_threshold": 5000,
        "point_radius_low_density": 2,
    },
    "sources": [
        {
            "id": "sim_room",
            "enabled": True,
            "type": "simulated",
            "num_points": 6000,
            "seed": 42,
            "room": {"half_x": 1.2, "half_y": 1.2, "half_z": 1.0, "floor_z": -0.4},
            "noise": 0.02,
        },
        {
            "id": "realsense",
            "enabled": True,
            "type": "realsense_depth",
            "width": 640,
            "height": 480,
            "fps": 30,
            "step": 4,
            "max_points": 20000,
        },
        {
            "id": "dds_lidar",
            "enabled": True,
            "type": "dds_pointcloud2",
            "topic": None,
            "read_timeout_sec": 0.35,
            "max_points": 20000,
            "candidate_topics": [
                "rt/pointcloud2",
                "rt/lidar/pointcloud",
                "rt/lidar/points",
                "rt/utlidar/cloud",
                "rt/utlidar/pointcloud",
                "rt/lf/pointcloud2",
                "rt/lf/lidar/points",
            ],
        },
    ],
    "robot_overlay": {
        "enabled": True,
        "joints": 29,
        "seg_len": 0.05,
        "chain_step_px": 18,
        "rest_wobble": 0.22,
    },
}


def ensure_advanced_world_file(path: Path | None = None) -> bool:
    """
    Создаёт JSON мира на диске из SHIPPED_ADVANCED_WORLD, если файла ещё нет.
    Returns True, если выполнялась запись.
    """
    p = Path(path) if path is not None else default_world_path()
    try:
        p = p.resolve()
    except Exception:
        pass
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        return False
    p.write_text(json.dumps(SHIPPED_ADVANCED_WORLD, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def default_world_path() -> Path:
    p = os.environ.get("RGW2_ADV_WORLD_PATH", "").strip()
    if p:
        return Path(p)
    return Path(DEFAULT_WORLD_REL)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def default_world_dict() -> Dict[str, Any]:
    """Minimal valid world if file missing."""
    return {
        "version": 1,
        "merge": {"max_total_points": 40000, "per_source_cap": 20000},
        "view": {
            "yaw": 0.8,
            "pitch": 0.15,
            "z_near": 0.25,
            "z_far": 3.5,
            "point_step": 4,
            "low_density_threshold": 5000,
            "point_radius_low_density": 2,
        },
        "sources": [
            {
                "id": "sim",
                "enabled": True,
                "type": "simulated",
                "num_points": 5000,
                "seed": 1,
                "room": {"half_x": 1.0, "half_y": 1.0, "half_z": 0.8, "floor_z": -0.3},
                "noise": 0.02,
            }
        ],
        "robot_overlay": {
            "enabled": True,
            "joints": 29,
            "seg_len": 0.05,
            "chain_step_px": 18,
            "rest_wobble": 0.22,
        },
    }


def load_world(path: Path | None = None) -> Dict[str, Any]:
    path = path or default_world_path()
    base = default_world_dict()
    if not path.exists():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return base
        merged = _deep_merge(base, raw)
        # Ensure lists exist
        if not isinstance(merged.get("sources"), list):
            merged["sources"] = base["sources"]
        return merged
    except Exception:
        return base


def enabled_sources(world: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in world.get("sources") or []:
        if not isinstance(s, dict):
            continue
        if s.get("enabled", True):
            out.append(s)
    return out


def source_by_id(world: Dict[str, Any], sid: str) -> Dict[str, Any] | None:
    for s in world.get("sources") or []:
        if isinstance(s, dict) and str(s.get("id", "")) == sid:
            return s
    return None

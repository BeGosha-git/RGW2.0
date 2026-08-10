"""Runtime: world JSON + live buffers → merged point cloud per frame."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from services.advanced_render.merge import merge_point_clouds
from services.advanced_render.plane_snap import dominant_planes_rectangles
from services.advanced_render.sources.dds_pointcloud2 import DDSPointCloudBuffer
from services.advanced_render.sources.realsense_depth import RealSenseDepthBuffer, depth_to_points_colors
from services.advanced_render.sources.simulated import sample_simulated
from services.advanced_render.world import enabled_sources


class WorldSceneRuntime:
    def __init__(self, world: Dict[str, Any]):
        self.world = world
        self._rs: Optional[RealSenseDepthBuffer] = None
        self._dds: Optional[DDSPointCloudBuffer] = None
        merge_cfg = world.get("merge") or {}
        self._max_total = int(merge_cfg.get("max_total_points") or 40000)
        self._per_cap = int(merge_cfg.get("per_source_cap") or self._max_total)
        self._plane_snap = bool(merge_cfg.get("plane_snap", False))
        self._plane_snap_tol = float(merge_cfg.get("plane_snap_tolerance_rel") or 0.1)
        self._plane_snap_max = int(merge_cfg.get("plane_snap_max_planes") or 8)
        self._plane_snap_knn_scale = float(merge_cfg.get("plane_snap_knn_scale") or 2.5)
        self._plane_snap_knn_k = int(merge_cfg.get("plane_snap_knn_k") or 8)
        self._plane_snap_cd = float(merge_cfg.get("plane_snap_cooldown_sec") or 10.0)
        self._plane_snap_seed_tries = int(merge_cfg.get("plane_snap_seed_tries") or 36)
        self._plane_snap_link_edge = float(merge_cfg.get("plane_snap_link_edge_factor") or 1.65)
        self._plane_snap_link_bridge = float(merge_cfg.get("plane_snap_link_bridge_k") or 2.85)
        self._plane_snap_eps_l = float(merge_cfg.get("plane_snap_eps_l_factor") or 0.16)
        self._plane_snap_eps_knn = float(merge_cfg.get("plane_snap_eps_knn_factor") or 1.75)
        self._plane_snap_expand_iters = int(merge_cfg.get("plane_snap_expand_iters") or 12)
        self._plane_snap_expand_rmul = float(merge_cfg.get("plane_snap_expand_radius_mul") or 1.45)
        self._plane_snap_expand_min_k = float(merge_cfg.get("plane_snap_expand_min_bridge_k") or 2.65)
        self._plane_snap_work_pts = int(merge_cfg.get("plane_snap_working_points") or 14000)
        self._plane_snap_last_mono: Optional[float] = None
        self._plane_cache_quads: List[Dict[str, Any]] = []
        self._plane_cache_threshs: List[float] = []
        try:
            import os

            if os.environ.get("RGW2_MERGE_PLANE_SNAP", "").lower() in ("1", "true", "yes", "on"):
                self._plane_snap = True
        except Exception:
            pass

        for s in enabled_sources(world):
            st = str(s.get("type", ""))
            if st == "realsense_depth" and self._rs is None:
                w = int(s.get("width") or 640)
                h = int(s.get("height") or 480)
                fps = int(s.get("fps") or 30)
                self._rs = RealSenseDepthBuffer(w, h, fps)
            if st == "dds_pointcloud2" and self._dds is None:
                self._dds = DDSPointCloudBuffer(s)

    def start_hardware(self) -> None:
        if self._rs is not None:
            self._rs.start()
        if self._dds is not None:
            self._dds.start()

    def stop_hardware(self) -> None:
        if self._rs is not None:
            self._rs.stop()
        if self._dds is not None:
            self._dds.stop()

    def sample_merged(self) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        view = self.world.get("view") or {}
        z_near = float(view.get("z_near") or 0.25)
        z_far = float(view.get("z_far") or 3.5)
        step = int(view.get("point_step") or 4)

        parts: List[Tuple[np.ndarray, np.ndarray, Dict[str, Any]]] = []

        for s in enabled_sources(self.world):
            sid = str(s.get("id", "src"))
            st = str(s.get("type", ""))
            if st == "simulated":
                pos, col, m = sample_simulated(s)
                m["id"] = sid
                parts.append((pos, col, m))
            elif st == "realsense_depth" and self._rs is not None:
                depth, ts, intr, scale = self._rs.snapshot()
                fresh = ts > 0 and (time.time() - ts) <= float(
                    __import__("os").environ.get("RGW2_CAMERA_MAX_AGE_SEC", "0.5") or 0.5
                )
                if depth is not None and intr is not None and fresh:
                    max_p = int(s.get("max_points") or 20000)
                    pos, col, m = depth_to_points_colors(
                        depth,
                        intr,
                        scale,
                        z_near,
                        z_far,
                        int(s.get("step") or step),
                        max_p,
                    )
                    # depth_to_points_colors currently returns camera-frame pts; merge uses same frame as projection
                    m["id"] = sid
                    parts.append((pos, col, m))
            elif st == "dds_pointcloud2" and self._dds is not None:
                pos, col, ts, m = self._dds.snapshot()
                m["id"] = sid
                if pos.shape[0] > 0:
                    parts.append((pos, col, m))

        merged_pos, merged_col, mmeta = merge_point_clouds(parts, self._max_total, self._per_cap)
        mmeta["source_ids"] = [str(p[2].get("id", "?")) for p in parts]
        if self._plane_snap and merged_pos.shape[0] > 0:
            now_m = time.monotonic()
            if (
                self._plane_snap_last_mono is None
                or (now_m - self._plane_snap_last_mono) >= self._plane_snap_cd
            ):
                self._plane_snap_last_mono = now_m
                mp = merged_pos
                mc = merged_col
                if mp.shape[0] > max(5000, self._plane_snap_work_pts):
                    rng_sub = np.random.default_rng(
                        int(now_m * 1000) % (2**32 - 1) + (mp.shape[0] % 104729)
                    )
                    ii = rng_sub.choice(mp.shape[0], self._plane_snap_work_pts, replace=False)
                    mp = np.asarray(mp[ii], dtype=np.float32)
                    mc = mc[ii]
                _, _, quads, plane_threshs = dominant_planes_rectangles(
                    mp,
                    mc,
                    tolerance_rel_cap=self._plane_snap_tol,
                    knn_scale=self._plane_snap_knn_scale,
                    knn_k=self._plane_snap_knn_k,
                    max_planes=max(1, self._plane_snap_max),
                    n_seed_tries=max(8, self._plane_snap_seed_tries),
                    link_edge_factor=self._plane_snap_link_edge,
                    link_bridge_k=self._plane_snap_link_bridge,
                    eps_l_factor=self._plane_snap_eps_l,
                    eps_knn_factor=self._plane_snap_eps_knn,
                    expand_iters=max(4, self._plane_snap_expand_iters),
                    expand_radius_mul=self._plane_snap_expand_rmul,
                    expand_min_bridge_k=self._plane_snap_expand_min_k,
                )
                self._plane_cache_quads = quads
                self._plane_cache_threshs = [float(x) for x in plane_threshs]
            mmeta["plane_snap"] = True
            mmeta["plane_snap_tolerance_rel"] = self._plane_snap_tol
            mmeta["plane_snap_max_planes"] = self._plane_snap_max
            mmeta["plane_snap_cooldown_sec"] = self._plane_snap_cd
            mmeta["plane_snap_thresholds"] = list(self._plane_cache_threshs)
            quad_list = []
            for q in self._plane_cache_quads:
                quad_list.append(
                    {
                        "corners": np.asarray(q["corners"], dtype=float).tolist(),
                        "color": np.asarray(q["color"]).astype(int).tolist(),
                    }
                )
            mmeta["plane_quads"] = quad_list
            mmeta["plane_quad"] = quad_list[0] if quad_list else None
        else:
            mmeta["plane_snap"] = False
            mmeta["plane_quad"] = None
            mmeta["plane_quads"] = []
            mmeta["plane_snap_thresholds"] = []
            mmeta["plane_snap_cooldown_sec"] = self._plane_snap_cd
        return merged_pos, merged_col, mmeta

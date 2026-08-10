"""RealSense depth → XYZ + pseudo-colors (same frame as advanced_render)."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import pyrealsense2 as rs

    REALSENSE_AVAILABLE = True
except Exception:
    REALSENSE_AVAILABLE = False
    rs = None  # type: ignore


def depth_to_points_colors(
    depth: np.ndarray,
    intr: Any,
    depth_scale: float,
    z_near: float,
    z_far: float,
    step: int,
    max_points: int,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Return 3D points in RealSense camera frame (x right, y down, z forward) and BGR-like colors."""
    if depth is None or intr is None:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8), {"count": 0}

    step = max(1, int(step))
    z_m = depth[::step, ::step].astype(np.float32) * float(depth_scale)
    v_idx = np.arange(0, depth.shape[0], step, dtype=np.float32)
    u_idx = np.arange(0, depth.shape[1], step, dtype=np.float32)
    uu, vv = np.meshgrid(u_idx, v_idx)
    mask = (z_m > z_near) & (z_m < z_far) & np.isfinite(z_m)
    if not np.any(mask):
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.uint8), {"count": 0}

    x = (uu - float(intr.ppx)) / float(intr.fx) * z_m
    y = (vv - float(intr.ppy)) / float(intr.fy) * z_m
    pts = np.stack([x, y, z_m], axis=-1).reshape(-1, 3)
    pts = pts[mask.reshape(-1)]
    if pts.shape[0] > max_points:
        idx = np.random.choice(pts.shape[0], max_points, replace=False)
        pts = pts[idx]

    # Color by depth in camera frame (before view rotate) using z_m values at those points
    z_vals = pts[:, 2]
    t = 1.0 - np.clip((z_vals - z_near) / max(1e-6, (z_far - z_near)), 0.0, 1.0)
    v = (t * 255.0).astype(np.uint8)
    cols = np.stack([v // 2, v, 255 - v // 2], axis=1).astype(np.uint8)
    meta = {"count": int(pts.shape[0]), "source": "realsense_depth"}
    return pts.astype(np.float32), cols, meta


class RealSenseDepthBuffer:
    """Background capture; thread-safe latest depth + intrinsics."""

    def __init__(self, width: int, height: int, fps: int = 30):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self._lock = threading.Lock()
        self._depth: Optional[np.ndarray] = None
        self._depth_ts = 0.0
        self._intr = None
        self._scale = 0.001
        self._running = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pipeline = None

    def start(self) -> bool:
        if not REALSENSE_AVAILABLE:
            return False
        if self._running:
            return True
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        pipeline = None
        try:
            pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, self.fps)
            profile = pipeline.start(config)
            depth_sensor = profile.get_device().first_depth_sensor
            self._scale = float(depth_sensor.get_depth_scale())
            dprof = profile.get_stream(rs.stream.depth).as_video_stream_profile()
            intr = dprof.get_intrinsics()
            with self._lock:
                self._intr = intr
            while self._running and not self._stop.is_set():
                frames = pipeline.wait_for_frames(timeout_ms=1000)
                df = frames.get_depth_frame() if frames else None
                if not df:
                    continue
                img = np.asanyarray(df.get_data())
                with self._lock:
                    self._depth = img
                    self._depth_ts = time.time()
        except Exception:
            pass
        finally:
            try:
                if pipeline is not None:
                    pipeline.stop()
            except Exception:
                pass

    def snapshot(self) -> Tuple[Optional[np.ndarray], float, Any, float]:
        with self._lock:
            return self._depth, float(self._depth_ts or 0.0), self._intr, float(self._scale or 0.001)

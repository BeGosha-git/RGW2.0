from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

try:
    import cv2

    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
    cv2 = None  # type: ignore

from services.advanced_render.lowstate_motor_buffer import LowStateMotorBuffer
from services.advanced_render.renderer_cv import draw_robot_overlay, project_points_to_bgr
from services.advanced_render.world import default_world_path, load_world
from services.advanced_render.world_runtime import WorldSceneRuntime
from services.advanced_render.world_stats import set_stats


class AdvancedRenderStream:
    """
    JPEG frames for /advanced WebRTC from `data/advanced_world.json`:
    merged point clouds (simulated + RealSense + DDS PointCloud2) + robot overlay from DDS lowstate.
    """

    def __init__(self, base_width: int = 640, base_height: int = 480, max_age_sec: Optional[float] = None):
        self._world_path = str(default_world_path())
        self._world = load_world(Path(self._world_path))
        self._apply_env_overrides_to_world()

        rs_src = next(
            (s for s in (self._world.get("sources") or []) if str(s.get("type")) == "realsense_depth"),
            None,
        )
        if rs_src:
            self.base_width = int(rs_src.get("width") or base_width)
            self.base_height = int(rs_src.get("height") or base_height)
        else:
            self.base_width = int(base_width)
            self.base_height = int(base_height)

        # Долгий merge/plane_snap не должен «протухать» последний JPEG в WebRTC (recv использует wait=False).
        if max_age_sec is None:
            max_age_sec = float(os.environ.get("RGW2_ADV_MAX_FRAME_AGE_SEC", "5.0"))
        self._max_age_sec = float(max_age_sec)

        self.running = False
        self._stop_evt = threading.Event()

        self._frame_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_bgr: Optional["np.ndarray"] = None
        self._latest_ts: float = 0.0
        self._latest_frame_id: int = 0

        self._jpeg_cache: Dict[Tuple[int, int, int, int], bytes] = {}
        self._jpeg_cache_max_keys = int(os.environ.get("RGW2_ADV_JPEG_CACHE_KEYS", "6"))

        ro = self._world.get("robot_overlay") or {}
        self._n_joints = int(ro.get("joints") or os.environ.get("RGW2_ADV_CHAIN_JOINTS", "29"))

        self._motors = LowStateMotorBuffer(self._n_joints)

        self._render_fps = float(os.environ.get("RGW2_ADV_RENDER_FPS", "25"))

        self._debug = str(os.environ.get("RGW2_ADV_DEBUG", "0")).lower() in ("1", "true", "yes", "on")
        self._log_interval_s = float(os.environ.get("RGW2_ADV_LOG_INTERVAL_S", "2.0"))
        self._last_log_ts = 0.0

        self._last_render_stats: Dict[str, Any] = {}

        self._threads: list[threading.Thread] = []
        self._runtime = WorldSceneRuntime(self._world)

    def _apply_env_overrides_to_world(self) -> None:
        v = self._world.setdefault("view", {})
        if os.environ.get("RGW2_ADV_VIEW_YAW"):
            v["yaw"] = float(os.environ["RGW2_ADV_VIEW_YAW"])
        if os.environ.get("RGW2_ADV_VIEW_PITCH"):
            v["pitch"] = float(os.environ["RGW2_ADV_VIEW_PITCH"])
        if os.environ.get("RGW2_ADV_Z_NEAR"):
            v["z_near"] = float(os.environ["RGW2_ADV_Z_NEAR"])
        if os.environ.get("RGW2_ADV_Z_FAR"):
            v["z_far"] = float(os.environ["RGW2_ADV_Z_FAR"])
        ro = self._world.setdefault("robot_overlay", {})
        if os.environ.get("RGW2_ADV_CHAIN_JOINTS"):
            ro["joints"] = int(os.environ["RGW2_ADV_CHAIN_JOINTS"])

    def start(self) -> bool:
        if self.running:
            return True
        if not CV2_AVAILABLE:
            return False
        self.running = True
        self._stop_evt.clear()
        self._runtime.start_hardware()
        self._motors.start()
        self._threads = [
            threading.Thread(target=self._render_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()
        return True

    def stop(self) -> None:
        self.running = False
        self._stop_evt.set()
        try:
            self._motors.stop()
        except Exception:
            pass
        try:
            self._runtime.stop_hardware()
        except Exception:
            pass

    def _render_loop(self) -> None:
        if not CV2_AVAILABLE:
            return

        dt = 1.0 / max(1.0, self._render_fps)
        view = self._world.get("view") or {}
        vy = float(view.get("yaw") or 0.8)
        vp = float(view.get("pitch") or 0.15)
        zn = float(view.get("z_near") or 0.25)
        zf = float(view.get("z_far") or 3.5)
        ld = int(view.get("low_density_threshold") or 5000)
        pr = int(view.get("point_radius_low_density") or 2)
        robot = self._world.get("robot_overlay") or {}

        while self.running and not self._stop_evt.is_set():
            t0 = time.time()
            try:
                # Пока sample_merged() долгий (плоскости и т.д.), не даём WebRTC отбросить предыдущий кадр по age.
                with self._frame_lock:
                    if self._latest_bgr is not None:
                        self._latest_ts = time.time()

                pos, col, mmeta = self._runtime.sample_merged()
                img, cv_stats = project_points_to_bgr(
                    pos, col, self.base_width, self.base_height, vy, vp, zn, zf, ld, pr
                )
                if img is None:
                    img = np.zeros((self.base_height, self.base_width, 3), dtype=np.uint8)

                motor_q, motor_ts = self._motors.snapshot()

                if robot.get("enabled", True):
                    draw_robot_overlay(img, motor_q, robot, vy, vp, zn, zf, depth_center_z=1.0)

                if pos.shape[0] <= 0:
                    try:
                        cv2.putText(
                            img,
                            "NO_PC",
                            (int(self.base_width * 0.03), int(self.base_height * 0.08)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 255, 255),
                            2,
                            lineType=cv2.LINE_AA,
                        )
                    except Exception:
                        pass

                input_ts = time.time()
                if motor_ts > 0:
                    input_ts = max(input_ts, motor_ts)

                stats = {
                    "merged_total": int(pos.shape[0]),
                    "merge_per_source": mmeta.get("per_source"),
                    "cv": cv_stats,
                }
                self._last_render_stats = stats
                set_stats(mmeta, {**cv_stats, "merged_total": int(pos.shape[0])}, self._world_path)

                if self._debug:
                    now_ts = time.time()
                    if now_ts - self._last_log_ts >= self._log_interval_s:
                        self._last_log_ts = now_ts
                        print(
                            f"[ADV_RENDER] merged_points={pos.shape[0]} per_source={mmeta.get('per_source')} cv={cv_stats}",
                            flush=True,
                        )

                with self._frame_lock:
                    self._latest_bgr = img
                    self._latest_ts = float(input_ts)
                    self._latest_frame_id = (self._latest_frame_id + 1) & 0x7FFFFFFF
                    self._frame_event.set()
                    self._jpeg_cache.clear()
            except Exception:
                with self._frame_lock:
                    self._latest_bgr = np.zeros((self.base_height, self.base_width, 3), dtype=np.uint8)
                    self._latest_ts = time.time()
                    self._latest_frame_id = (self._latest_frame_id + 1) & 0x7FFFFFFF
                    self._frame_event.set()

            elapsed = time.time() - t0
            sleep_t = dt - elapsed
            if sleep_t > 0:
                self._stop_evt.wait(timeout=min(sleep_t, 0.25))

    def get_debug_stats(self) -> Dict[str, Any]:
        try:
            return dict(self._last_render_stats)
        except Exception:
            return {}

    def get_latest_frame(self, width: int = None, height: int = None, quality: int = 80, wait: bool = True) -> Optional[bytes]:
        if not CV2_AVAILABLE:
            return None

        if wait:
            self._frame_event.wait(timeout=0.5)
        else:
            # WebRTC трекает с wait=False; один короткий wait на холодном старте.
            with self._frame_lock:
                cold = self._latest_bgr is None
            if cold:
                self._frame_event.wait(timeout=0.35)

        with self._frame_lock:
            bgr = None if self._latest_bgr is None else self._latest_bgr
            ts = float(self._latest_ts or 0.0)
            frame_id = int(self._latest_frame_id or 0)

        if bgr is None:
            return None
        if self._max_age_sec > 0 and ts > 0 and (time.time() - ts) > self._max_age_sec:
            return None

        out_w = int(width) if width is not None else self.base_width
        out_h = int(height) if height is not None else self.base_height
        qv = int(quality)

        key = (frame_id, out_w, out_h, qv)
        cached = self._jpeg_cache.get(key)
        if cached is not None:
            return cached

        frame = bgr
        if out_w != bgr.shape[1] or out_h != bgr.shape[0]:
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), qv])
        if not (ok and buf is not None):
            try:
                placeholder = np.zeros((out_h, out_w, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder,
                    "ADV",
                    (int(out_w * 0.4), int(out_h * 0.5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 255),
                    2,
                )
                ok2, buf2 = cv2.imencode(".jpg", placeholder, [int(cv2.IMWRITE_JPEG_QUALITY), qv])
                if ok2 and buf2 is not None:
                    jpg2 = buf2.tobytes()
                    if len(self._jpeg_cache) >= self._jpeg_cache_max_keys:
                        self._jpeg_cache.clear()
                    self._jpeg_cache[key] = jpg2
                    return jpg2
            except Exception:
                pass
            return None

        jpg = buf.tobytes()
        if len(self._jpeg_cache) >= self._jpeg_cache_max_keys:
            self._jpeg_cache.clear()
        self._jpeg_cache[key] = jpg
        return jpg

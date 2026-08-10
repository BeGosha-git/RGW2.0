"""
JPEG preview of merged advanced world for WebRTC test page.
Рендер без OpenCV: проекция точек в NumPy, JPEG через Pillow, resize через PIL.
"""

from __future__ import annotations

import io
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import numpy as np
from PIL import Image, ImageDraw

from services.advanced_render.robot_overlay_pil import draw_robot_overlay_rgb
from services.advanced_render.world import load_world
from services.advanced_render.world_runtime import WorldSceneRuntime

if TYPE_CHECKING:
    from services.advanced_render.lowstate_motor_buffer import LowStateMotorBuffer


def _rot_x(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], dtype=np.float32)


def _rot_y(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], dtype=np.float32)


def _project_points_to_bgr(
    positions: np.ndarray,
    colors: np.ndarray,
    out_w: int,
    out_h: int,
    view_yaw: float,
    view_pitch: float,
    z_near: float,
    _z_far: float,
) -> np.ndarray:
    """BGR uint8 (H,W,3), только numpy (как плотная ветка renderer_cv)."""
    img = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    if positions.shape[0] == 0:
        return img

    view_r = _rot_y(float(view_yaw)) @ _rot_x(float(view_pitch))
    pts_v = (view_r @ positions.T).T
    z = pts_v[:, 2]
    good = z > float(z_near)
    pts_v = pts_v[good]
    z = z[good]
    if colors.shape[0] == positions.shape[0]:
        cols = colors[good]
    else:
        cols = np.zeros((pts_v.shape[0], 3), np.uint8)

    if pts_v.shape[0] == 0:
        return img

    f = 0.9 * min(out_w, out_h)
    cx = out_w * 0.5
    cy = out_h * 0.5
    xs = (pts_v[:, 0] / z) * f + cx
    ys = (-pts_v[:, 1] / z) * f + cy
    xi = xs.astype(np.int32)
    yi = ys.astype(np.int32)
    inb = (xi >= 0) & (xi < out_w) & (yi >= 0) & (yi < out_h)
    xi = xi[inb]
    yi = yi[inb]
    cols = cols[inb]
    if xi.shape[0] == 0:
        return img
    img[yi, xi] = cols
    return img


class WorldPreviewStream:
    """
    Drop-in for webrtc_handler.CameraVideoTrack: get_latest_frame(width, height, quality, wait).
    """

    def __init__(
        self,
        world_path: Path | None = None,
        *,
        world: Dict[str, Any] | None = None,
        runtime: WorldSceneRuntime | None = None,
        motor_buffer: Optional["LowStateMotorBuffer"] = None,
    ):
        """
        If `runtime` and `world` are passed, reuse them (one RealSense/DDS stack with Viser).
        Otherwise load `world_path` and own a new WorldSceneRuntime.
        """
        self._lock = threading.Lock()
        if runtime is not None and world is not None:
            self._world = world
            self._world_path = str(world_path or os.environ.get("RGW2_ADV_WORLD_PATH", "data/advanced_world.json"))
            self._runtime = runtime
            self._own_runtime = False
        else:
            path = world_path or Path(os.environ.get("RGW2_ADV_WORLD_PATH", "data/advanced_world.json"))
            self._world = load_world(path)
            self._world_path = str(path)
            self._runtime = WorldSceneRuntime(self._world)
            self._own_runtime = True
        self._motor_buffer = motor_buffer
        self._frame_id = 0
        self._capture_ts: deque = deque(maxlen=120)

        view = self._world.get("view") or {}
        self._out_w = int(view.get("width") or 640)
        self._out_h = int(view.get("height") or 480)
        rs = next((s for s in (self._world.get("sources") or []) if str(s.get("type")) == "realsense_depth"), None)
        if rs:
            self._out_w = int(rs.get("width") or self._out_w)
            self._out_h = int(rs.get("height") or self._out_h)

        self._max_age = float(os.environ.get("RGW2_CAMERA_MAX_AGE_SEC", "0.5"))

    def start(self) -> None:
        if self._own_runtime:
            self._runtime.start_hardware()

    def stop(self) -> None:
        if self._own_runtime:
            self._runtime.stop_hardware()

    def get_capture_fps(self) -> float:
        try:
            now = time.monotonic()
            while self._capture_ts and self._capture_ts[0] < now - 1.0:
                self._capture_ts.popleft()
            if len(self._capture_ts) < 2:
                return 0.0
            return (len(self._capture_ts) - 1) / max(1e-6, now - self._capture_ts[0])
        except Exception:
            return 0.0

    def _render_bgr(self, out_w: int, out_h: int) -> np.ndarray:
        view = self._world.get("view") or {}
        vy = float(view.get("yaw") or 0.8)
        vp = float(view.get("pitch") or 0.15)
        zn = float(view.get("z_near") or 0.25)
        zf = float(view.get("z_far") or 3.5)

        pos, col, _ = self._runtime.sample_merged()
        bgr = _project_points_to_bgr(pos, col, out_w, out_h, vy, vp, zn, zf)
        if pos.shape[0] <= 0:
            rgb = bgr[:, :, ::-1].copy()
            pil_im = Image.fromarray(rgb, mode="RGB")
            dr = ImageDraw.Draw(pil_im)
            dr.text((int(out_w * 0.03), int(out_h * 0.06)), "NO_PC", fill=(255, 255, 0))
            bgr = np.asarray(pil_im)[:, :, ::-1]
        return bgr

    def get_latest_frame(
        self,
        width: int = None,
        height: int = None,
        quality: int = 80,
        wait: bool = True,
    ) -> Optional[bytes]:
        out_w = int(width) if width is not None else self._out_w
        out_h = int(height) if height is not None else self._out_h
        qv = max(1, min(95, int(quality)))

        view = self._world.get("view") or {}
        vy = float(view.get("yaw") or 0.8)
        vp = float(view.get("pitch") or 0.15)
        zn = float(view.get("z_near") or 0.25)
        zf = float(view.get("z_far") or 3.5)
        robot = self._world.get("robot_overlay") or {}

        with self._lock:
            bgr = self._render_bgr(out_w, out_h)
            rgb = bgr[:, :, ::-1]
            pil_im = Image.fromarray(rgb, mode="RGB")
            if self._motor_buffer is not None and robot.get("enabled", True):
                mq, _ = self._motor_buffer.snapshot()
                from services.advanced_render.robot_dynamics import apply_if_enabled

                qv, bsh = apply_if_enabled(mq, time.monotonic())
                draw_robot_overlay_rgb(pil_im, qv, robot, vy, vp, zn, zf, base_xy_shift=bsh)
            if pil_im.size != (out_w, out_h):
                pil_im = pil_im.resize((out_w, out_h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            pil_im.save(buf, format="JPEG", quality=qv)
            self._frame_id = (self._frame_id + 1) & 0x7FFFFFFF
            self._capture_ts.append(time.monotonic())
            return buf.getvalue()

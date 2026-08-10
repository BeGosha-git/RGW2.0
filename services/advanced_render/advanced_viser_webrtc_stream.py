"""
Advanced (/advanced) WebRTC source: JPEG frames captured from a live Viser viewport.

Key point:
  - This stream does NOT render a 2D projection itself.
  - Frames are captured via `viser.ClientHandle.get_render()` which returns a rasterized
    image of the WebGL scene rendered in a connected browser client (GPU accelerated).

If no Viser client is connected, get_latest_frame() returns None and the WebRTC track
will fall back to its built-in "No signal" frame.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from services.advanced_render.lowstate_motor_buffer import LowStateMotorBuffer
from services.advanced_render.robot_dynamics import base_shift_visual
from services.advanced_render.viser_render_stream import ViserRenderStream
from services.advanced_render.world import default_world_path, load_world
from services.advanced_render.world_runtime import WorldSceneRuntime
from services.advanced_render.world_stats import set_stats


class AdvancedViserWebRTCStream:
    """
    Drop-in for webrtc_handler.CameraVideoTrack: get_latest_frame(width, height, quality, wait).
    """

    def __init__(self, *, world_path: Optional[Path] = None, width: int = 640, height: int = 480):
        self._world_path = str(world_path or os.environ.get("RGW2_ADV_WORLD_PATH", "") or default_world_path())
        self._world = load_world(Path(self._world_path))
        self._runtime = WorldSceneRuntime(self._world)

        ro = self._world.get("robot_overlay") or {}
        self._n_joints = int(ro.get("joints") or 29)
        self._motors = LowStateMotorBuffer(self._n_joints)

        self._viser_server: Any = None
        self._viser_server_debug: Any = None
        self._viser_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        self._render = ViserRenderStream(base_width=int(width), base_height=int(height))
        self.running = False
        self._save_path = os.environ.get("RGW2_ADV_SAVE_JPEG_PATH", "/tmp/advanced_latest.jpg")
        self._save_every_s = float(os.environ.get("RGW2_ADV_SAVE_JPEG_EVERY_S", "0.5"))
        self._last_save_mono = 0.0
        self._headless_proc: Optional[subprocess.Popen] = None
        self._last_good_jpg: Optional[bytes] = None
        self._last_good_mono: float = 0.0
        self._headless_log = os.environ.get("RGW2_ADV_VISER_HEADLESS_LOG", "/tmp/viser_headless.log")
        self._headless_restart_sec = float(os.environ.get("RGW2_ADV_VISER_HEADLESS_RESTART_SEC", "8.0"))
        self._headless_last_try_mono = 0.0
        self._last_diag_ts = 0.0

    def start(self) -> bool:
        if self.running:
            return True
        try:
            import viser  # noqa: F401
        except Exception as e:
            print(f"[ADV_VISER] viser not installed: {e}", flush=True)
            return False

        self.running = True
        self._stop_evt.clear()
        # IMPORTANT: do not block WebRTC offer path here.
        # Hardware init (RealSense/DDS) can take >20s or hang; if we block here then
        # `handle_offer()` will timeout before returning SDP answer.
        self._viser_thread = threading.Thread(
            target=self._viser_loop,
            daemon=True,
            name="adv-viser-loop",
        )
        self._viser_thread.start()
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
        try:
            if self._viser_server is not None:
                self._viser_server.stop()
        except Exception:
            pass
        try:
            if self._viser_server_debug is not None:
                self._viser_server_debug.stop()
        except Exception:
            pass
        try:
            if self._headless_proc is not None:
                self._headless_proc.terminate()
        except Exception:
            pass

    def _find_browser(self) -> Optional[str]:
        env = os.environ.get("RGW2_ADV_VISER_BROWSER", "").strip()
        if env:
            return env
        for c in (
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
            "chrome",
        ):
            p = shutil.which(c)
            if p:
                return p
        return None

    def _start_headless_client(self, url: str) -> None:
        """
        Start a local headless Chromium/Chrome that connects to Viser so that
        ClientHandle.get_render() works without manual browser.
        """
        # Default ON: server should render without a manually opened browser.
        if os.environ.get("RGW2_ADV_VISER_HEADLESS", "1").lower() not in ("1", "true", "yes", "on"):
            return
        if self._headless_proc is not None and self._headless_proc.poll() is None:
            return
        browser = self._find_browser()
        if not browser:
            print("[ADV_VISER] headless: no chromium/chrome found (set RGW2_ADV_VISER_BROWSER)", flush=True)
            return
        url = str(url or "").strip()
        if not url:
            return

        # NOTE: do NOT use flags that disable networking — we need localhost websocket.
        want_gpu = os.environ.get("RGW2_ADV_VISER_HEADLESS_GPU", "0").lower() in ("1", "true", "yes", "on")
        extra = os.environ.get("RGW2_ADV_VISER_BROWSER_FLAGS", "").strip().split()
        args = [
            browser,
            "--headless=new",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            # Safe defaults: keep software rasterizer available so the client can connect
            # even if GPU init fails in headless environment.
            "--hide-scrollbars",
            "--window-size=1280,720",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--mute-audio",
        ]
        if want_gpu:
            # Prefer ANGLE EGL (more compatible in headless environments).
            args += [
                "--use-gl=angle",
                "--use-angle=gl-egl",
                "--enable-gpu",
            ]
        else:
            # Avoid GPU init flakiness; rendering may fall back to software but still produces frames.
            args += ["--disable-gpu"]
        if os.geteuid() == 0:
            args.append("--no-sandbox")
        args += extra
        args += [url]
        try:
            out = None
            try:
                if self._headless_log:
                    out = open(self._headless_log, "ab", buffering=0)
            except Exception:
                out = None
            self._headless_proc = subprocess.Popen(
                args,
                stdout=out or subprocess.DEVNULL,
                stderr=out or subprocess.DEVNULL,
                close_fds=True,
            )
            print(
                f"[ADV_VISER] headless client started: {os.path.basename(browser)} gpu={want_gpu} url={url}",
                flush=True,
            )
        except Exception as e:
            print(f"[ADV_VISER] headless client failed: {e}", flush=True)
            self._headless_proc = None

    def _viser_loop(self) -> None:
        # Start buffers in background thread; failures are tolerated.
        try:
            self._runtime.start_hardware()
        except Exception:
            pass
        try:
            self._motors.start()
        except Exception:
            pass

        try:
            import viser

            host = os.environ.get("RGW2_ADV_VISER_HOST", "0.0.0.0")
            port = int(os.environ.get("RGW2_ADV_VISER_PORT", "8088"))
            dbg_port = int(os.environ.get("RGW2_ADV_VISER_DEBUG_PORT", "8089"))

            server = viser.ViserServer(host=host, port=port, label="ADV (render)")
            self._viser_server = server
            self._render.attach_server(server)
            print(f"[ADV_VISER] Viser(render) http://127.0.0.1:{server.get_port()}/", flush=True)

            server_dbg = None
            if dbg_port and int(dbg_port) != int(port):
                try:
                    server_dbg = viser.ViserServer(host=host, port=int(dbg_port), label="ADV (debug)")
                    self._viser_server_debug = server_dbg
                    # Allow raster capture from debug port clients too (useful when only debug is opened).
                    self._render.attach_server(server_dbg)
                    print(f"[ADV_VISER] Viser(debug)  http://127.0.0.1:{server_dbg.get_port()}/", flush=True)
                except Exception as e:
                    print(f"[ADV_VISER] failed to start debug ViserServer: {e}", flush=True)
                    server_dbg = None
        except Exception as e:
            print(f"[ADV_VISER] failed to start ViserServer: {e}", flush=True)
            return

        servers = [server] + ([server_dbg] if server_dbg is not None else [])
        # Start local headless client ONLY for render port.
        # Chrome headless does not support multiple targets (multiple URLs) in one process.
        try:
            self._start_headless_client(f"http://127.0.0.1:{server.get_port()}/")
        except Exception:
            pass

        view = self._world.get("view") or {}
        zn = float(view.get("z_near") or 0.25)
        zf = float(view.get("z_far") or 3.5)
        robot = self._world.get("robot_overlay") or {}

        # Optional full G1 MuJoCo model (if available).
        g1_states: Dict[int, Any] = {}
        g1_update_fn = None
        try:
            from services.advanced_render.g1_mujoco_viser import try_setup_g1_mujoco_viser, update_g1_mujoco_viser

            for s in servers:
                try:
                    g1_states[id(s)] = try_setup_g1_mujoco_viser(s)
                except Exception:
                    g1_states[id(s)] = None
            g1_update_fn = update_g1_mujoco_viser
        except Exception:
            g1_update_fn = None

        # Fallback rig (lines / trimesh).
        try:
            from services.advanced_render.procedural_robot_trimesh import TRIMESH_AVAILABLE, build_spine_rig_trimesh
            from services.advanced_render.robot_overlay_math import polyline_to_line_segments, spine_chain_points_world
            from services.advanced_render.robot_dynamics import apply_if_enabled
        except Exception:
            TRIMESH_AVAILABLE = False
            build_spine_rig_trimesh = None  # type: ignore
            polyline_to_line_segments = None  # type: ignore
            spine_chain_points_world = None  # type: ignore
            apply_if_enabled = None  # type: ignore

        logged_rig = False
        logged_lines = False

        while not self._stop_evt.is_set():
            try:
                pos, col, mmeta = self._runtime.sample_merged()
                if pos.shape[0] > 0:
                    rgb = col[:, ::-1].astype(np.uint8)
                    for s in servers:
                        s.scene.add_point_cloud("/world/merged", points=pos, colors=rgb, point_size=0.02)

                if robot.get("enabled", True):
                    tmono = time.monotonic()
                    q_raw, _ = self._motors.snapshot()

                    # If we have MuJoCo model, update per-server.
                    if g1_update_fn is not None and any(g1_states.get(id(s)) is not None for s in servers):
                        bx, by = base_shift_visual(tmono)
                        for s in servers:
                            st = g1_states.get(id(s))
                            if st is None:
                                continue
                            try:
                                g1_update_fn(st, q_raw, (bx, by))  # type: ignore[misc]
                            except Exception:
                                pass
                    else:
                        if apply_if_enabled is not None:
                            q_vis, base_shift = apply_if_enabled(q_raw, tmono)
                        else:
                            q_vis, base_shift = q_raw, (0.0, 0.0)

                        if spine_chain_points_world is not None:
                            pts_w = spine_chain_points_world(q_vis, robot, zn, zf, base_xy_shift=base_shift)
                            mesh = None
                            if TRIMESH_AVAILABLE and build_spine_rig_trimesh is not None:
                                try:
                                    mesh = build_spine_rig_trimesh(pts_w)
                                except Exception:
                                    mesh = None
                            if mesh is not None:
                                try:
                                    for s in servers:
                                        s.scene.add_mesh_trimesh("/world/robot/rig", mesh=mesh, visible=True)
                                    if not logged_rig:
                                        print("[ADV_VISER] robot: trimesh rig (fallback, no MuJoCo)", flush=True)
                                        logged_rig = True
                                except Exception:
                                    mesh = None
                            if mesh is None and polyline_to_line_segments is not None:
                                segs = polyline_to_line_segments(pts_w)
                                if segs.shape[0] > 0:
                                    cols2 = np.full((segs.shape[0], 2, 3), 220, dtype=np.uint8)
                                    try:
                                        for s in servers:
                                            s.scene.add_line_segments(
                                                "/world/robot/spine",
                                                points=segs,
                                                colors=cols2,
                                                line_width=2.5,
                                            )
                                        if not logged_lines:
                                            print("[ADV_VISER] robot: line rig (fallback)", flush=True)
                                            logged_lines = True
                                    except Exception:
                                        pass

                set_stats(mmeta, {"mode": "viser", "points": int(pos.shape[0])}, self._world_path)
                try:
                    now = time.time()
                    if now - float(self._last_diag_ts or 0.0) >= 2.0:
                        self._last_diag_ts = now
                        hp = None
                        try:
                            hp = None if self._headless_proc is None else self._headless_proc.poll()
                        except Exception:
                            hp = None
                        n_clients = 0
                        for s in servers:
                            if s is None:
                                continue
                            try:
                                n_clients += len(s.get_clients() or {})
                            except Exception:
                                pass
                        print(
                            f"[ADV_VISER] points={int(pos.shape[0])} headless={'run' if hp is None else 'dead'} clients={n_clients}",
                            flush=True,
                        )
                except Exception:
                    pass
            except Exception:
                pass

            self._stop_evt.wait(0.20)

    def get_latest_frame(
        self,
        width: int = None,
        height: int = None,
        quality: int = 80,
        wait: bool = True,
    ) -> Optional[bytes]:
        # If we keep failing to get_render(), try restarting headless periodically.
        try:
            now_m = time.monotonic()
            if (now_m - float(self._last_good_mono or 0.0)) >= self._headless_restart_sec:
                if (now_m - float(self._headless_last_try_mono or 0.0)) >= self._headless_restart_sec:
                    self._headless_last_try_mono = now_m
                    try:
                        if self._headless_proc is not None and self._headless_proc.poll() is None:
                            self._headless_proc.terminate()
                    except Exception:
                        pass
                    try:
                        if self._viser_server is not None:
                            self._start_headless_client(f"http://127.0.0.1:{self._viser_server.get_port()}/")
                    except Exception:
                        pass
        except Exception:
            pass

        jpg = self._render.get_latest_frame(width=width, height=height, quality=quality, wait=wait)
        if jpg:
            try:
                now_m = time.monotonic()
                self._last_good_jpg = jpg
                self._last_good_mono = now_m
                if self._save_path and (now_m - float(self._last_save_mono or 0.0)) >= self._save_every_s:
                    self._last_save_mono = now_m
                    tmp = f"{self._save_path}.tmp"
                    with open(tmp, "wb") as f:
                        f.write(jpg)
                    os.replace(tmp, self._save_path)
            except Exception:
                pass
        # Reuse last good JPEG briefly so WebRTC doesn't flap while headless reconnects.
        try:
            if jpg is None and self._last_good_jpg is not None:
                if (time.monotonic() - float(self._last_good_mono or 0.0)) <= 2.0:
                    return self._last_good_jpg
        except Exception:
            pass
        return jpg

    def get_capture_fps(self) -> float:
        # Rendering happens in the client; we don't have a meaningful server-side capture fps here.
        return 0.0


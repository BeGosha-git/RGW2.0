#!/usr/bin/env python3
"""
Тест advanced world: Viser (облако + модель робота по rt/lowstate), опционально WebRTC
(та же проекция и оверлей робота, NumPy+Pillow).

Usage:
  python3 services/advanced_render/test_world_viewer.py --world data/advanced_world.json --host 0.0.0.0 --port 8088
  python3 services/advanced_render/test_world_viewer.py --port 8088 --webrtc --http-port 8890 --http-host 0.0.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

# Repo root on sys.path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def probe_sdks() -> dict:
    out = {}
    try:
        import numpy as np

        out["numpy"] = {"ok": True, "note": np.__version__}
    except Exception as e:
        out["numpy"] = {"ok": False, "note": str(e)}

    try:
        import pyrealsense2 as rs  # noqa: F401

        out["pyrealsense2"] = {"ok": True, "note": "import ok"}
    except Exception as e:
        out["pyrealsense2"] = {"ok": False, "note": str(e)}

    try:
        from unitree_sdk2py.core.channel import ChannelFactory  # noqa: F401

        out["unitree_sdk2py"] = {"ok": True, "note": "import ok"}
    except Exception as e:
        out["unitree_sdk2py"] = {"ok": False, "note": str(e)}

    try:
        import viser  # noqa: F401

        out["viser"] = {"ok": True, "note": "import ok"}
    except Exception as e:
        out["viser"] = {"ok": False, "note": f"{e} (pip install viser)"}

    try:
        import aiortc  # noqa: F401

        out["aiortc"] = {"ok": True, "note": "import ok"}
    except Exception as e:
        out["aiortc"] = {"ok": False, "note": str(e)}

    try:
        import flask  # noqa: F401

        out["flask"] = {"ok": True, "note": "import ok"}
    except Exception as e:
        out["flask"] = {"ok": False, "note": str(e)}

    try:
        import PIL  # noqa: F401

        out["pillow"] = {"ok": True, "note": getattr(PIL, "__version__", "ok")}
    except Exception as e:
        out["pillow"] = {"ok": False, "note": str(e)}

    try:
        import trimesh  # noqa: F401

        out["trimesh"] = {"ok": True, "note": getattr(trimesh, "__version__", "ok")}
    except Exception as e:
        out["trimesh"] = {"ok": False, "note": f"{e} (pip install trimesh)"}

    try:
        import mujoco  # noqa: F401

        out["mujoco"] = {"ok": True, "note": getattr(mujoco, "__version__", "ok")}
    except Exception as e:
        out["mujoco"] = {"ok": False, "note": f"{e} (pip install mujoco)"}

    return out


def _html_page(viser_port: int) -> str:
    vp = int(viser_port)
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>World preview — Viser + WebRTC</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #111; color: #ddd; }}
    h1 {{ font-size: 1rem; padding: 8px 12px; margin: 0; background: #222; }}
    .row {{ display: flex; flex-wrap: wrap; gap: 8px; padding: 8px; align-items: flex-start; }}
    .pane {{ flex: 1; min-width: 320px; background: #1a1a1a; border-radius: 8px; overflow: hidden; }}
    iframe {{ width: 100%; height: 480px; border: 0; background: #000; }}
    video {{ width: 100%; max-height: 480px; background: #000; display: block; }}
    .hint {{ font-size: 12px; color: #888; padding: 8px 12px; }}
    #status {{ color: #fa0; padding: 4px 12px; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Advanced world: Viser + WebRTC — облако и робот (углы с rt/lowstate)</h1>
  <p id="status">Connecting WebRTC…</p>
  <div class="row">
    <div class="pane">
      <div class="hint">Viser (WebGL в браузере)</div>
      <iframe id="viserFrame" title="viser"></iframe>
    </div>
    <div class="pane">
      <div class="hint">WebRTC — JPEG с вида 3D-окна Viser (растр get_render с клиента в iframe); если клиента нет — плоская проекция облака</div>
      <video id="vid" autoplay playsinline muted></video>
    </div>
  </div>
  <script>
    const VISER_PORT = {vp};
    (function() {{
      const iframe = document.getElementById('viserFrame');
      if (VISER_PORT > 0) {{
        iframe.src = window.location.protocol + '//' + window.location.hostname + ':' + VISER_PORT + '/';
      }} else {{
        iframe.style.display = 'none';
        iframe.parentElement.querySelector('.hint').textContent = 'Viser: укажите --port';
      }}
    }})();

    async function startWebRTC() {{
      const status = document.getElementById('status');
      const video = document.getElementById('vid');
      try {{
        const pc = new RTCPeerConnection({{ iceServers: [{{ urls: 'stun:stun.l.google.com:19302' }}] }});
        pc.addTransceiver('video', {{ direction: 'recvonly' }});
        pc.ontrack = (ev) => {{
          video.srcObject = ev.streams[0];
          status.textContent = 'WebRTC: track received';
        }};
        pc.onconnectionstatechange = () => {{
          status.textContent = 'WebRTC state: ' + pc.connectionState;
        }};
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        const res = await fetch('/world-preview/webrtc/offer', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ sdp: offer.sdp, type: offer.type, quality: 'high' }})
        }});
        const data = await res.json();
        if (!data.success) {{
          status.textContent = 'WebRTC offer failed: ' + (data.message || JSON.stringify(data));
          return;
        }}
        await pc.setRemoteDescription({{ type: data.type, sdp: data.sdp }});
        if (data.capture_fps != null) status.textContent += ' | capture_fps≈' + data.capture_fps;
      }} catch (e) {{
        status.textContent = 'WebRTC error: ' + e;
      }}
    }}
    startWebRTC();
  </script>
</body>
</html>
"""


def _run_flask(preview_stream, host: str, port: int, viser_port: int) -> None:
    from flask import Flask, Response, jsonify, request

    from services.camera_stream.webrtc_handler import handle_custom_stream_offer

    app = Flask(__name__)
    app.config["PREVIEW_STREAM"] = preview_stream

    @app.route("/")
    def index():
        return Response(_html_page(viser_port), mimetype="text/html")

    @app.route("/world-preview/webrtc/offer", methods=["POST"])
    def webrtc_offer():
        stream = app.config["PREVIEW_STREAM"]
        data = request.get_json(force=True, silent=True) or {}
        sdp = data.get("sdp")
        typ = data.get("type") or "offer"
        quality = data.get("quality") or "high"
        if not sdp:
            return jsonify({"success": False, "message": "sdp required"}), 400
        out = handle_custom_stream_offer(stream, sdp, typ, quality_mode=str(quality), label="world_preview_test")
        return jsonify(out), (200 if out.get("success") else 500)

    app.run(host=host, port=int(port), threaded=True, use_reloader=False)


def _viser_loop(
    rt,
    stop_evt: threading.Event,
    host: str,
    port: int,
    world_path: str,
    world: dict,
    motor_buffer,
    viser_render=None,
) -> None:
    import time

    import numpy as np

    from services.advanced_render.procedural_robot_trimesh import TRIMESH_AVAILABLE, build_spine_rig_trimesh
    from services.advanced_render.g1_mujoco_viser import (
        try_setup_g1_mujoco_viser,
        update_g1_mujoco_viser,
    )
    from services.advanced_render.robot_dynamics import apply_if_enabled, base_shift_visual
    from services.advanced_render.robot_overlay_math import polyline_to_line_segments, spine_chain_points_world
    from services.advanced_render.world_stats import set_stats

    try:
        import viser

        server = viser.ViserServer(host=host, port=port)
    except Exception as e:
        print(f"[viser thread] failed: {e}", flush=True)
        return

    if viser_render is not None:
        try:
            viser_render.attach_server(server)
        except Exception as e:
            print(f"[viser] ViserRenderStream.attach_server: {e}", flush=True)

    view = world.get("view") or {}
    zn = float(view.get("z_near") or 0.25)
    zf = float(view.get("z_far") or 3.5)
    robot = world.get("robot_overlay") or {}

    g1_mujoco = try_setup_g1_mujoco_viser(server)

    logged_rig = False
    logged_fallback = False
    plane_quad_handles: list = []

    while not stop_evt.is_set():
        try:
            pos, col, mmeta = rt.sample_merged()
            if pos.shape[0] > 0:
                rgb = col[:, ::-1].astype(np.uint8)
                server.scene.add_point_cloud("/world/merged", points=pos, colors=rgb, point_size=0.02)
            pq_list = []
            if isinstance(mmeta, dict):
                pq_list = mmeta.get("plane_quads") or []
                if not pq_list and mmeta.get("plane_quad"):
                    pq_list = [mmeta["plane_quad"]]
            if TRIMESH_AVAILABLE and pq_list:
                try:
                    import trimesh

                    while len(plane_quad_handles) < len(pq_list):
                        plane_quad_handles.append(None)
                    for i in range(len(pq_list), len(plane_quad_handles)):
                        h = plane_quad_handles[i]
                        if h is not None:
                            try:
                                h.visible = False
                            except Exception:
                                pass
                    plane_quad_handles = plane_quad_handles[: len(pq_list)]

                    for i, pq in enumerate(pq_list):
                        if not pq or not pq.get("corners"):
                            if i < len(plane_quad_handles) and plane_quad_handles[i] is not None:
                                try:
                                    plane_quad_handles[i].visible = False
                                except Exception:
                                    pass
                            continue
                        verts = np.asarray(pq["corners"], dtype=np.float32)
                        faces = np.array([[0, 1, 2], [0, 2, 3], [0, 2, 1], [0, 3, 2]], dtype=np.int64)
                        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
                        c = pq.get("color") or [120, 170, 240]
                        r, g, b = int(c[0]), int(c[1]), int(c[2])
                        mesh.visual.face_colors = np.full((4, 4), [r, g, b, 160], dtype=np.uint8)
                        path = f"/world/plane_fit_quad_{i}"
                        plane_quad_handles[i] = server.scene.add_mesh_trimesh(
                            path,
                            mesh=mesh,
                            wxyz=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                            position=np.zeros(3, dtype=np.float32),
                            visible=True,
                        )
                        try:
                            plane_quad_handles[i].visible = True
                        except Exception:
                            pass
                except Exception:
                    pass
            elif plane_quad_handles:
                for h in plane_quad_handles:
                    if h is not None:
                        try:
                            h.visible = False
                        except Exception:
                            pass
                plane_quad_handles = []
            if motor_buffer is not None and robot.get("enabled", True):
                tmono = time.monotonic()
                q_raw, _ = motor_buffer.snapshot()
                if g1_mujoco is not None:
                    bx, by = base_shift_visual(tmono)
                    update_g1_mujoco_viser(g1_mujoco, q_raw, (bx, by))
                else:
                    q_vis, base_shift = apply_if_enabled(q_raw, tmono)
                if g1_mujoco is None:
                    pts_w = spine_chain_points_world(q_vis, robot, zn, zf, base_xy_shift=base_shift)
                    mesh = None
                    if TRIMESH_AVAILABLE:
                        mesh = build_spine_rig_trimesh(pts_w)
                    if mesh is not None:
                        try:
                            server.scene.add_mesh_trimesh("/world/robot/rig", mesh=mesh, visible=True)
                            if not logged_rig:
                                print(
                                    "[viser] робот: упрощённая trimesh-модель (нет g1.xml для MuJoCo — RGW2_G1_MJCF)",
                                    flush=True,
                                )
                                logged_rig = True
                        except Exception:
                            mesh = None
                    if mesh is None:
                        segs = polyline_to_line_segments(pts_w)
                        if segs.shape[0] > 0:
                            cols = np.full((segs.shape[0], 2, 3), 220, dtype=np.uint8)
                            try:
                                server.scene.add_line_segments(
                                    "/world/robot/spine",
                                    points=segs,
                                    colors=cols,
                                    line_width=2.5,
                                )
                            except Exception:
                                pass
                        if not logged_fallback:
                            if not TRIMESH_AVAILABLE:
                                print("[viser] trimesh не установлен — только линии. pip install trimesh", flush=True)
                            else:
                                print("[viser] trimesh есть, но меш не собран — показаны линии", flush=True)
                            logged_fallback = True
            set_stats(mmeta, {"mode": "viser", "points": int(pos.shape[0])}, world_path)
        except Exception:
            pass
        stop_evt.wait(0.33)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=str, default="data/advanced_world.json")
    ap.add_argument("--host", type=str, default="0.0.0.0", help="Viser bind host")
    ap.add_argument("--port", type=int, default=8088, help="Viser port")
    ap.add_argument("--wait-hw-sec", type=float, default=2.0, help="Wait for RealSense/DDS before capture")
    ap.add_argument("--webrtc", action="store_true", help="Страница HTML + WebRTC (JPEG)")
    ap.add_argument(
        "--webrtc-flat-only",
        action="store_true",
        help="WebRTC только 2D-проекция облака (без растра Viser get_render)",
    )
    ap.add_argument("--http-host", type=str, default="0.0.0.0", help="Flask host for WebRTC page")
    ap.add_argument("--http-port", type=int, default=8890, help="Flask port for WebRTC page")
    args = ap.parse_args()

    print("=== SDK probe ===")
    sdk = probe_sdks()
    for k, v in sdk.items():
        print(f"  {k}: ok={v.get('ok')} {v.get('note', '')}")

    try:
        from utils.data_bootstrap import bootstrap_data_files
        from utils.path_utils import get_project_root

        bootstrap_data_files(get_project_root())
    except Exception:
        pass

    world_path = Path(args.world)
    try:
        from services.advanced_render.world import ensure_advanced_world_file

        ensure_advanced_world_file(world_path)
    except Exception:
        pass

    probe_path = world_path.resolve().parent / "world_viewer_sdk_probe.json"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    probe_path.write_text(json.dumps(sdk, indent=2), encoding="utf-8")

    if not sdk.get("viser", {}).get("ok"):
        print("Нужен пакет viser: pip install viser (см. requirements.txt)", flush=True)
        return 2

    from services.advanced_render.lowstate_motor_buffer import LowStateMotorBuffer
    from services.advanced_render.world import load_world
    from services.advanced_render.world_runtime import WorldSceneRuntime

    world = load_world(world_path)
    os.environ.setdefault("RGW2_ADV_WORLD_PATH", str(world_path.resolve()))

    ro = world.get("robot_overlay") or {}
    n_j = int(ro.get("joints") or 29)
    motor_buffer = LowStateMotorBuffer(n_j)
    motor_buffer.start()

    rt = WorldSceneRuntime(world)
    rt.start_hardware()
    time.sleep(max(0.0, float(args.wait_hw_sec)))

    stop_evt = threading.Event()
    viser_cap = None
    if args.webrtc and not args.webrtc_flat_only:
        try:
            from services.advanced_render.viser_render_stream import ViserRenderStream

            rs = next(
                (s for s in (world.get("sources") or []) if str(s.get("type")) == "realsense_depth"),
                None,
            )
            vw = int(rs.get("width") or 640) if rs else 640
            vh = int(rs.get("height") or 480) if rs else 480
            viser_cap = ViserRenderStream(base_width=vw, base_height=vh)
        except Exception as e:
            print(f"[viser] ViserRenderStream не создан: {e}", flush=True)

    viser_thread = threading.Thread(
        target=_viser_loop,
        args=(rt, stop_evt, args.host, int(args.port), str(world_path), world, motor_buffer, viser_cap),
        daemon=True,
    )
    viser_thread.start()
    print(f"Viser: http://127.0.0.1:{args.port}/ (host={args.host})", flush=True)

    if not sdk.get("mujoco", {}).get("ok"):
        print(
            "G1 в Viser: pip install mujoco и RGW2_G1_MJCF=/путь/g1.xml (+ каталог assets/ со STL).",
            flush=True,
        )

    preview_stream = None
    flask_thread: threading.Thread | None = None
    if args.webrtc:
        if not sdk.get("flask", {}).get("ok"):
            print("Flask не установлен.", flush=True)
            stop_evt.set()
            motor_buffer.stop()
            rt.stop_hardware()
            return 2
        if not sdk.get("aiortc", {}).get("ok"):
            print("aiortc не установлен.", flush=True)
            stop_evt.set()
            motor_buffer.stop()
            rt.stop_hardware()
            return 2
        if not sdk.get("pillow", {}).get("ok"):
            print("Pillow не установлен (нужен для JPEG трека).", flush=True)
            stop_evt.set()
            motor_buffer.stop()
            rt.stop_hardware()
            return 2

        from services.advanced_render.world_preview_stream import WorldPreviewStream
        from services.advanced_render.viser_render_stream import ChainedPreviewStream

        flat_stream = WorldPreviewStream(world=world, runtime=rt, motor_buffer=motor_buffer)
        if viser_cap is not None:
            preview_stream = ChainedPreviewStream(viser_cap, flat_stream)
            print(
                "[webrtc] приоритет: растр с вида Viser (откройте URL Viser в браузере); "
                "иначе — плоская проекция облака.",
                flush=True,
            )
        else:
            preview_stream = flat_stream
        flask_thread = threading.Thread(
            target=_run_flask,
            args=(preview_stream, args.http_host, int(args.http_port), int(args.port)),
            daemon=True,
        )
        flask_thread.start()
        print(
            f"WebRTC страница: http://127.0.0.1:{args.http_port}/  (POST /world-preview/webrtc/offer)",
            flush=True,
        )

    print("Ctrl+C — выход.", flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    stop_evt.set()
    motor_buffer.stop()
    rt.stop_hardware()
    if preview_stream is not None:
        preview_stream.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

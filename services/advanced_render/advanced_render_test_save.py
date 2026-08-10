#!/usr/bin/env python3
"""
Test renderer for /advanced WebRTC.

Starts `AdvancedRenderStream`, grabs one JPEG frame and saves it to disk.
Useful to debug rendering without relying on the full WebRTC pipeline.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data", help="Directory to save debug images")
    parser.add_argument("--base-w", type=int, default=640)
    parser.add_argument("--base-h", type=int, default=480)
    parser.add_argument("--quality", type=int, default=80)
    parser.add_argument("--wait-sec", type=float, default=3.0, help="Max time to wait for at least one frame")
    parser.add_argument("--min-depth-points", type=int, default=1, help="Try until depth_points_drawn >= this value")
    parser.add_argument("--save-every-frame", action="store_true", help="Save each received frame (can be spammy)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        os.environ["RGW2_ADV_DEBUG"] = "1"

    # Ensure repo root is importable as `services.*`
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from services.advanced_render.advanced_render_stream import AdvancedRenderStream

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stream = AdvancedRenderStream(
        base_width=args.base_w,
        base_height=args.base_h,
        max_age_sec=float(os.environ.get("RGW2_CAMERA_MAX_AGE_SEC", "0.5")),
    )
    if not stream.start():
        # This dev environment may not have OpenCV installed.
        # Still save a simple image so you can verify the file path + pipeline.
        try:
            import numpy as np

            out_img = np.zeros((args.base_h, args.base_w, 3), dtype=np.uint8)
            cy = args.base_h // 2
            cx = args.base_w // 2
            # Cyan-ish "spot" where the 2D skeleton root marker should appear.
            out_img[cy - 5 : cy + 5, cx - 5 : cx + 5] = np.array([0, 180, 255], dtype=np.uint8)

            ppm_path = out_dir / "advanced_render_debug_last.ppm"
            header = f"P6\n{args.base_w} {args.base_h}\n255\n".encode("ascii")
            with open(ppm_path, "wb") as f:
                f.write(header)
                # PPM expects RGB; our array is BGR-like in the renderer.
                rgb = out_img[:, :, ::-1].tobytes()
                f.write(rgb)
            print(f"[ADV_TEST] OpenCV missing: saved placeholder {ppm_path}")
            return 0
        except Exception as e:
            print(f"[ADV_TEST] Failed to start AdvancedRenderStream and save placeholder: {e}")
            return 2

    def _save_stats(stats: dict, suffix: str) -> None:
        import json as _json

        stats_path = out_dir / f"advanced_render_debug_stats_{suffix}.json"
        try:
            stats_path.write_text(_json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    t0 = time.time()
    jpeg = None
    saved_count = 0

    while time.time() - t0 < args.wait_sec:
        jpeg_try = stream.get_latest_frame(width=args.base_w, height=args.base_h, quality=args.quality, wait=True)
        stats = stream.get_debug_stats() if hasattr(stream, "get_debug_stats") else {}

        if jpeg_try is not None and (args.save_every_frame or jpeg is None):
            jpeg = jpeg_try
            if not args.save_every_frame:
                # save only last
                pass

            if args.save_every_frame:
                ts = time.strftime("%Y%m%d_%H%M%S")
                frame_path = out_dir / f"advanced_render_debug_{ts}.jpg"
                try:
                    frame_path.write_bytes(jpeg_try)
                    saved_count += 1
                except Exception:
                    pass

            _save_stats(stats, "last")
            depth_pts = int(stats.get("depth_points_drawn") or 0)
            print(
                f"[ADV_TEST] frame_bytes={len(jpeg_try)} depth_ok={stats.get('depth_ok')} depth_points={depth_pts} "
                f"age={stats.get('depth_age_sec')} in_frame={stats.get('depth_points_in_frame')}",
                flush=True,
            )

            if depth_pts >= args.min_depth_points:
                break

        if jpeg is None:
            time.sleep(0.05)

    ts = time.strftime("%Y%m%d_%H%M%S")
    last_path = out_dir / "advanced_render_debug_last.jpg"
    if jpeg is not None:
        try:
            last_path.write_bytes(jpeg)
        except Exception:
            pass
        stamped = out_dir / f"advanced_render_debug_{ts}.jpg"
        try:
            stamped.write_bytes(jpeg)
        except Exception:
            pass

        # Save final stats snapshot.
        try:
            _save_stats(stream.get_debug_stats(), ts)
        except Exception:
            pass

        print(f"[ADV_TEST] Saved {last_path} ({len(jpeg)} bytes), saved_every_frame={args.save_every_frame}, saved_count={saved_count}")
        stream.stop()
        return 0

    print("[ADV_TEST] No frame produced within timeout (jpeg is None)")
    stream.stop()
    return 3


if __name__ == "__main__":
    raise SystemExit(main())


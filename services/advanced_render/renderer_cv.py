"""Project 3D points + optional robot overlay to BGR (OpenCV)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2

    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
    cv2 = None  # type: ignore


def rot_x(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], dtype=np.float32)


def rot_y(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], dtype=np.float32)


def project_points_to_bgr(
    positions: np.ndarray,
    colors: np.ndarray,
    out_w: int,
    out_h: int,
    view_yaw: float,
    view_pitch: float,
    z_near: float,
    z_far: float,
    low_density_threshold: int = 5000,
    point_radius_low: int = 2,
) -> Tuple[Any, Dict[str, Any]]:
    """Returns BGR uint8 image (H,W,3) and stats."""
    stats: Dict[str, Any] = {"points_in": int(positions.shape[0]), "points_drawn": 0, "points_in_frame": 0}
    if not CV2_AVAILABLE:
        return None, stats
    img = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    if positions.shape[0] == 0:
        return img, stats

    view_R = rot_y(float(view_yaw)) @ rot_x(float(view_pitch))
    pts_v = (view_R @ positions.T).T
    z = pts_v[:, 2]
    good = z > float(z_near)
    pts_v = pts_v[good]
    z = z[good]
    if colors.shape[0] == positions.shape[0]:
        cols = colors[good]
    else:
        cols = np.zeros((pts_v.shape[0], 3), np.uint8)

    stats["points_drawn"] = int(pts_v.shape[0])
    if pts_v.shape[0] == 0:
        return img, stats

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
    stats["points_in_frame"] = int(xi.shape[0])

    if xi.shape[0] == 0:
        return img, stats

    if stats["points_drawn"] <= low_density_threshold and point_radius_low >= 2:
        for px, py, col in zip(xi.tolist(), yi.tolist(), cols.tolist()):
            cv2.circle(img, (int(px), int(py)), int(point_radius_low), tuple(int(c) for c in col), -1)
    else:
        img[yi, xi] = cols

    return img, stats


def draw_robot_overlay(
    img: Any,
    motor_q: Optional[List[float]],
    world_robot: Dict[str, Any],
    view_yaw: float,
    view_pitch: float,
    z_near: float,
    z_far: float,
    depth_center_z: float = 1.0,
) -> None:
    if not CV2_AVAILABLE or img is None:
        return
    n_j = int(world_robot.get("joints") or 29)
    seg_len = float(world_robot.get("seg_len") or 0.05)
    chain_step_px = float(world_robot.get("chain_step_px") or 18)
    rest_wobble = float(world_robot.get("rest_wobble") or 0.22)
    q = motor_q if (motor_q is not None and len(motor_q) > 0) else [0.0 for _ in range(n_j)]

    out_h, out_w = img.shape[:2]
    view_R = rot_y(float(view_yaw)) @ rot_x(float(view_pitch))

    base_z = max(z_near + 0.1, min(z_far - 0.1, float(depth_center_z)))
    base = np.array([0.0, 0.0, base_z], dtype=np.float32)
    pts_chain = [base]
    cur_dir = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    cur_pt = base
    for i in range(min(n_j, len(q))):
        ang = float(q[i])
        Rm = rot_y(ang) if i % 2 == 0 else rot_x(ang)
        cur_dir = Rm @ cur_dir
        cur_dir = cur_dir / (np.linalg.norm(cur_dir) + 1e-6)
        cur_pt = cur_pt + cur_dir * seg_len
        pts_chain.append(cur_pt)

    pts_arr = np.stack(pts_chain, axis=0)
    pts_v = (view_R @ pts_arr.T).T
    z = pts_v[:, 2]
    safe_z = np.where(z > (z_near + 1e-3), z, (z_near + 1e-3))
    f = 0.9 * min(out_w, out_h)
    cx = out_w * 0.5
    cy = out_h * 0.5
    xs = (pts_v[:, 0] / safe_z) * f + cx
    ys = (-pts_v[:, 1] / safe_z) * f + cy
    proj = np.stack([xs, ys], axis=1).astype(np.int32)

    for i in range(len(proj) - 1):
        x1, y1 = int(proj[i][0]), int(proj[i][1])
        x2, y2 = int(proj[i + 1][0]), int(proj[i + 1][1])
        if 0 <= x1 < out_w and 0 <= y1 < out_h and 0 <= x2 < out_w and 0 <= y2 < out_h:
            cv2.line(img, (x1, y1), (x2, y2), (255, 255, 255), 3, lineType=cv2.LINE_AA)

    center_x = int(out_w * 0.5)
    center_y = int(out_h * 0.55)
    sx, sy = float(center_x), float(center_y)
    cv2.circle(img, (int(sx), int(sy)), 10, (0, 180, 255), -1)
    accum = 0.0
    for i in range(min(n_j, len(q))):
        accum += float(q[i]) * 0.05
        ang = accum * 0.25 + float(i) * rest_wobble
        screen_dir = np.array([float(np.sin(ang)), float(-np.cos(ang))], dtype=np.float32)
        nx = sx + screen_dir[0] * chain_step_px
        ny = sy + screen_dir[1] * chain_step_px
        x1, y1 = int(sx), int(sy)
        x2, y2 = int(nx), int(ny)
        x2 = max(0, min(out_w - 1, x2))
        y2 = max(0, min(out_h - 1, y2))
        if 0 <= x1 < out_w and 0 <= y1 < out_h:
            cv2.line(img, (x1, y1), (x2, y2), (0, 255, 255), 6, lineType=cv2.LINE_AA)
        cv2.circle(img, (x2, y2), 6, (255, 255, 0), -1)
        sx, sy = float(x2), float(y2)

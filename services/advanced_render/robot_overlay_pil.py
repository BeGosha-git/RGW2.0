"""Оверлей робота на RGB-кадр (Pillow), та же проекция, что и в renderer_cv (без жёлтой «декор»-цепочки)."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

import numpy as np
from PIL import ImageDraw

from services.advanced_render.robot_overlay_math import rot_x, rot_y, spine_chain_points_world


def draw_robot_overlay_rgb(
    img_rgb,
    motor_q: Optional[Sequence[float]],
    world_robot: dict,
    view_yaw: float,
    view_pitch: float,
    z_near: float,
    z_far: float,
    depth_center_z: float = 1.0,
    base_xy_shift: Union[Tuple[float, float], Sequence[float]] = (0.0, 0.0),
) -> None:
    """Рисует поверх PIL Image в режиме RGB (in-place)."""
    if world_robot.get("enabled", True) is False:
        return

    out_w, out_h = img_rgb.size
    dr = ImageDraw.Draw(img_rgb)

    pts_world = spine_chain_points_world(
        motor_q, world_robot, z_near, z_far, depth_center_z, base_xy_shift=base_xy_shift
    )
    view_r = rot_y(float(view_yaw)) @ rot_x(float(view_pitch))
    pts_v = (view_r @ pts_world.T).T
    z = pts_v[:, 2]
    safe_z = np.where(z > (z_near + 1e-3), z, (z_near + 1e-3))
    f = 0.9 * min(out_w, out_h)
    cx = out_w * 0.5
    cy = out_h * 0.5
    xs = (pts_v[:, 0] / safe_z) * f + cx
    ys = (-pts_v[:, 1] / safe_z) * f + cy
    proj = np.stack([xs, ys], axis=1)

    for i in range(len(proj) - 1):
        x1, y1 = int(proj[i][0]), int(proj[i][1])
        x2, y2 = int(proj[i + 1][0]), int(proj[i + 1][1])
        if 0 <= x1 < out_w and 0 <= y1 < out_h and 0 <= x2 < out_w and 0 <= y2 < out_h:
            dr.line((x1, y1, x2, y2), fill=(255, 255, 255), width=3)

    # Маркер базы (оранжевый круг), без жёлтой псевдо-цепочки по экрану
    if len(proj) > 0:
        x0, y0 = int(proj[0][0]), int(proj[0][1])
        if 0 <= x0 < out_w and 0 <= y0 < out_h:
            r0 = 8
            dr.ellipse((x0 - r0, y0 - r0, x0 + r0, y0 + r0), fill=(255, 160, 80))

"""Геометрия упрощённой цепочки робота (numpy, без OpenCV)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple, Union

import numpy as np


def rot_x(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]], dtype=np.float32)


def rot_y(a: float) -> np.ndarray:
    ca = float(np.cos(a))
    sa = float(np.sin(a))
    return np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]], dtype=np.float32)


def spine_chain_points_world(
    motor_q: Optional[Sequence[float]],
    world_robot: dict,
    z_near: float,
    z_far: float,
    depth_center_z: float = 1.0,
    base_xy_shift: Union[Tuple[float, float], Sequence[float]] = (0.0, 0.0),
) -> np.ndarray:
    """
    Вершины «позвоночника» в мировых координатах (как в renderer_cv.draw_robot_overlay).
    Форма (K, 3), float32.
    """
    n_j = int(world_robot.get("joints") or 29)
    seg_len = float(world_robot.get("seg_len") or 0.05)
    q: List[float]
    if motor_q is not None and len(motor_q) > 0:
        q = [float(x) for x in motor_q[:n_j]]
    else:
        q = [0.0] * n_j
    while len(q) < n_j:
        q.append(0.0)

    base_z = max(z_near + 0.1, min(z_far - 0.1, float(depth_center_z)))
    base = np.array([0.0, 0.0, base_z], dtype=np.float32)
    pts_chain: list[np.ndarray] = [base.copy()]
    cur_dir = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    cur_pt = base.copy()
    for i in range(n_j):
        ang = float(q[i])
        rm = rot_y(ang) if i % 2 == 0 else rot_x(ang)
        cur_dir = rm @ cur_dir
        cur_dir = cur_dir / (np.linalg.norm(cur_dir) + 1e-6)
        cur_pt = cur_pt + cur_dir * seg_len
        pts_chain.append(cur_pt.copy())
    out = np.stack(pts_chain, axis=0).astype(np.float32)
    sx = float(base_xy_shift[0])
    sy = float(base_xy_shift[1])
    if sx != 0.0 or sy != 0.0:
        out[:, 0] += sx
        out[:, 1] += sy
    return out


def polyline_to_line_segments(pts: np.ndarray) -> np.ndarray:
    """(N,3) -> (N-1, 2, 3) для viser.scene.add_line_segments."""
    if pts.shape[0] < 2:
        return np.zeros((0, 2, 3), dtype=np.float32)
    a = pts[:-1].astype(np.float32, copy=False)
    b = pts[1:].astype(np.float32, copy=False)
    return np.stack([a, b], axis=1)

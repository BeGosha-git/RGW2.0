"""
Объёмная «модель» робота для Viser: торс (бокс) + сегменты цепочки (цилиндры) + суставы (сферы).
Без внешних GLB — выглядит как упрощённый humanoid, но не как жёлтая линия.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import trimesh

    TRIMESH_AVAILABLE = True
except Exception:
    TRIMESH_AVAILABLE = False
    trimesh = None  # type: ignore


def _rot_align_pos_z_to_unit(u: np.ndarray) -> np.ndarray:
    """R: e_z -> u (единичный вектор)."""
    u = np.asarray(u, dtype=np.float64).reshape(3)
    n = np.linalg.norm(u)
    if n < 1e-12:
        return np.eye(3)
    u = u / n
    z = np.array([0.0, 0.0, 1.0])
    if np.dot(u, z) > 1.0 - 1e-9:
        return np.eye(3)
    if np.dot(u, z) < -1.0 + 1e-9:
        return np.diag([1.0, -1.0, -1.0]).astype(np.float64)
    v = np.cross(z, u)
    s = np.linalg.norm(v)
    c = float(np.dot(z, u))
    vx = np.array([[0.0, -v[2], v[1]], [v[2], 0.0, -v[0]], [-v[1], v[0], 0.0]])
    return np.eye(3) + vx + vx @ vx * ((1.0 - c) / (s * s))


def _cylinder_segment(p0: np.ndarray, p1: np.ndarray, radius: float, sections: int = 10):
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    d = p1 - p0
    h = float(np.linalg.norm(d))
    if h < 1e-7:
        return None
    u = d / h
    cyl = trimesh.creation.cylinder(radius=radius, height=h, sections=sections)
    mid = (p0 + p1) * 0.5
    R = _rot_align_pos_z_to_unit(u)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = mid
    cyl.apply_transform(T)
    return cyl


def _set_face_rgba(mesh, rgba):
    try:
        mesh.visual.face_colors = rgba
    except Exception:
        pass


def build_spine_rig_trimesh(pts_world: np.ndarray) -> Optional["trimesh.Trimesh"]:
    """
    pts_world: (K, 3) — цепочка из spine_chain_points_world.
    """
    if not TRIMESH_AVAILABLE or trimesh is None:
        return None
    pts = np.asarray(pts_world, dtype=np.float64)
    if pts.shape[0] < 2:
        return None

    parts = []
    p0 = pts[0]
    p1 = pts[1]
    up = p1 - p0
    ln = np.linalg.norm(up)
    if ln < 1e-6:
        up = np.array([0.0, 0.0, 1.0])
    else:
        up = up / ln

    # Торс
    torso = trimesh.creation.box(extents=[0.24, 0.16, 0.32])
    chest = p0 + up * 0.20
    R = _rot_align_pos_z_to_unit(up)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = chest
    torso.apply_transform(T)
    _set_face_rgba(torso, [140, 148, 158, 255])
    parts.append(torso)

    # «Голова»
    if pts.shape[0] >= 3:
        top_dir = pts[min(2, pts.shape[0] - 1)] - p0
        if np.linalg.norm(top_dir) > 1e-6:
            top_dir = top_dir / np.linalg.norm(top_dir)
        else:
            top_dir = up
        head_c = p0 + top_dir * 0.42
        head = trimesh.creation.icosphere(subdivisions=2, radius=0.09)
        head.apply_translation(head_c)
        _set_face_rgba(head, [180, 175, 170, 255])
        parts.append(head)

    # Сегменты позвоночника
    for i in range(pts.shape[0] - 1):
        c = _cylinder_segment(pts[i], pts[i + 1], radius=0.034, sections=10)
        if c is not None:
            _set_face_rgba(c, [70, 120, 190, 255])
            parts.append(c)

    # Суставы
    for i, p in enumerate(pts):
        r = 0.045 if i % 3 == 0 else 0.036
        sph = trimesh.creation.icosphere(subdivisions=2, radius=float(r))
        sph.apply_translation(p)
        tone = [210, 200, 60, 255] if i == 0 else [200, 200, 215, 255]
        _set_face_rgba(sph, tone)
        parts.append(sph)

    try:
        return trimesh.util.concatenate(parts)
    except Exception:
        try:
            for p in parts:
                p.visual = None
            return trimesh.util.concatenate(parts)
        except Exception:
            return None

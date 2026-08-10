"""Deterministic simulated point cloud (floor + walls + noise) for tests."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np


def sample_simulated(cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Returns:
        positions (N,3) float32 camera-ish frame (x right, y down, z forward approx)
        colors (N,3) uint8 BGR-like for OpenCV
        meta dict
    """
    n = int(cfg.get("num_points") or 5000)
    seed = int(cfg.get("seed") or 42)
    rng = np.random.default_rng(seed)
    room = cfg.get("room") or {}
    hx = float(room.get("half_x", 1.0))
    hy = float(room.get("half_y", 1.0))
    hz = float(room.get("half_z", 0.8))
    fz = float(room.get("floor_z", -0.3))
    noise = float(cfg.get("noise") or 0.02)

    n_floor = n // 2
    n_wall = n - n_floor
    pts: list[np.ndarray] = []
    cols: list[np.ndarray] = []

    # Floor in xz plane at y=fz, x/z spread
    xf = rng.uniform(-hx, hx, size=n_floor).astype(np.float32)
    zf = rng.uniform(0.2, hz + 0.5, size=n_floor).astype(np.float32)
    yf = np.full(n_floor, fz, dtype=np.float32) + rng.normal(0, noise, n_floor).astype(np.float32)
    floor_pts = np.stack([xf, yf, zf], axis=1)
    pts.append(floor_pts)
    g = (rng.random(n_floor) * 80 + 40).astype(np.uint8)
    floor_col = np.stack([g // 2, g, 80 - g // 3], axis=1).astype(np.uint8)
    cols.append(floor_col)

    # Two walls: x=±hx and y varies
    n1 = n_wall // 2
    n2 = n_wall - n1
    yw = rng.uniform(fz, fz + 2 * hz, size=n1).astype(np.float32)
    zw = rng.uniform(0.2, hz + 0.5, size=n1).astype(np.float32)
    xw = np.full(n1, hx, dtype=np.float32) * rng.choice([-1.0, 1.0], size=n1).astype(np.float32)
    w1 = np.stack([xw, yw, zw], axis=1)
    pts.append(w1)
    cols.append(np.stack([rng.integers(60, 180, size=n1), rng.integers(100, 220, size=n1), rng.integers(80, 200, size=n1)], axis=1).astype(np.uint8))

    yw2 = rng.uniform(fz, fz + 2 * hz, size=n2).astype(np.float32)
    xw2 = rng.uniform(-hx, hx, size=n2).astype(np.float32)
    zw2 = np.full(n2, hz + 0.2, dtype=np.float32)
    w2 = np.stack([xw2, yw2, zw2], axis=1)
    pts.append(w2)
    cols.append(np.stack([rng.integers(80, 200, size=n2), rng.integers(60, 180, size=n2), rng.integers(100, 255, size=n2)], axis=1).astype(np.uint8))

    positions = np.concatenate(pts, axis=0).astype(np.float32)
    colors = np.concatenate(cols, axis=0).astype(np.uint8)
    meta = {"source": "simulated", "count": int(positions.shape[0])}
    return positions, colors, meta

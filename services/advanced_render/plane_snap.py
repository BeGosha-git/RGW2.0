"""Плоскости в облаке: тройка ближайших к затравке → связное наращивание + уточнение плоскости (SVD) и донабор точек по близости."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _aabb_extent(pos: np.ndarray) -> float:
    mn = pos.min(axis=0)
    mx = pos.max(axis=0)
    return float(np.linalg.norm(mx - mn))


def _median_kth_neighbor_distance(
    pos: np.ndarray,
    *,
    k: int = 8,
    n_anchors: int = 400,
    neighbor_pool: int = 512,
    rng: np.random.Generator,
) -> float:
    n = pos.shape[0]
    if n < k + 2:
        return 1e-4
    k = min(int(k), n - 1)
    na = min(int(n_anchors), n)
    pool = min(int(neighbor_pool), max(1, n - 1))
    anchors = rng.choice(n, size=na, replace=False)
    dists_k: List[float] = []
    for a in anchors:
        take = min(pool, n - 1)
        rnd = rng.integers(0, n - 1, size=take, dtype=np.int64)
        jj = rnd + (rnd >= int(a))
        d = np.linalg.norm(pos[jj] - pos[a], axis=1)
        if d.size < k:
            continue
        dk = float(np.partition(d, k - 1)[k - 1])
        dists_k.append(dk)
    if not dists_k:
        return 1e-4
    return float(np.median(np.asarray(dists_k, dtype=np.float64)))


def _fit_plane_svd(pts: np.ndarray) -> Tuple[np.ndarray, float]:
    """МНК-плоскость через SVD; нормаль единичная, d в n·x+d=0."""
    c = pts.mean(axis=0)
    x = pts - c
    if x.shape[0] < 3:
        n = np.array([0.0, 0.0, 1.0], dtype=np.float64)
        return n, float(-np.dot(n, c))
    _, _, vh = np.linalg.svd(x, full_matrices=False)
    n = np.asarray(vh[-1], dtype=np.float64)
    n = n / (np.linalg.norm(n) + 1e-12)
    d = float(-np.dot(n, c))
    return n, d


def _bfs_within_radius(
    pos: np.ndarray,
    *,
    seed_mask: np.ndarray,
    band_mask: np.ndarray,
    radius: float,
) -> np.ndarray:
    """Связная компонента: старт seed_mask, можно добавлять только band_mask, шаг ≤ radius (решётка)."""
    npt = pos.shape[0]
    out = seed_mask.astype(bool).copy()
    if radius < 1e-9 or not np.any(band_mask):
        return out
    inv_r = 1.0 / max(radius, 1e-9)
    buckets: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for i in np.flatnonzero(band_mask):
        key = tuple(np.floor(pos[i] * inv_r).astype(np.int32))
        buckets[key].append(int(i))

    q: deque[int] = deque(int(i) for i in np.flatnonzero(seed_mask) if band_mask[i])
    r2 = radius * radius
    while q:
        u = q.popleft()
        bu = np.floor(pos[u] * inv_r).astype(np.int32)
        for ax in (-1, 0, 1):
            for ay in (-1, 0, 1):
                for az in (-1, 0, 1):
                    key = (int(bu[0] + ax), int(bu[1] + ay), int(bu[2] + az))
                    for v in buckets.get(key, ()):
                        if out[v] or not band_mask[v]:
                            continue
                        du = pos[u] - pos[v]
                        if float(du @ du) <= r2 + 1e-9:
                            out[v] = True
                            q.append(v)
    return out


def _triangle_longest_edge(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray) -> float:
    return float(
        max(
            np.linalg.norm(p1 - p0),
            np.linalg.norm(p2 - p0),
            np.linalg.norm(p2 - p1),
        )
    )


def _quad_from_inliers(pos: np.ndarray, col: np.ndarray, inlier: np.ndarray) -> Dict[str, Any]:
    pts_in = pos[inlier]
    col_in = col[inlier]
    c = np.cross(pts_in[1] - pts_in[0], pts_in[2] - pts_in[0])
    ln = np.linalg.norm(c)
    n = c / (ln + 1e-12)
    p0 = pts_in[0]
    if abs(n[0]) < 0.9:
        aux = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    else:
        aux = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    u = np.cross(n, aux)
    u = u / (np.linalg.norm(u) + 1e-12)
    v = np.cross(n, u)
    v = v / (np.linalg.norm(v) + 1e-12)
    rel = pts_in - p0
    s = rel @ u
    t = rel @ v
    smin, smax = float(s.min()), float(s.max())
    tmin, tmax = float(t.min()), float(t.max())
    corners = np.stack(
        [
            p0 + smin * u + tmin * v,
            p0 + smax * u + tmin * v,
            p0 + smax * u + tmax * v,
            p0 + smin * u + tmax * v,
        ],
        axis=0,
    ).astype(np.float32)
    if col_in.ndim == 2 and col_in.shape[1] >= 3:
        cmean = col_in[:, :3].mean(axis=0)
        cmean = np.clip(cmean, 0, 255).astype(np.uint8)
    else:
        cmean = np.array([128, 180, 255], dtype=np.uint8)
    return {"corners": corners, "color": cmean}


def _one_connected_plane(
    pos: np.ndarray,
    col: np.ndarray,
    *,
    tolerance_rel_cap: float,
    knn_scale: float,
    knn_k: int,
    min_inliers: int,
    n_seed_tries: int,
    rng: np.random.Generator,
    link_edge_factor: float = 1.65,
    link_bridge_k: float = 2.85,
    eps_l_factor: float = 0.16,
    eps_knn_factor: float = 1.75,
    expand_iters: int = 12,
    expand_radius_mul: float = 1.45,
    expand_min_bridge_k: float = 2.65,
) -> Tuple[Optional[Dict[str, Any]], np.ndarray, float]:
    """
    Затравка: точка + две ближайшие → плоскость, L = длинная сторона треугольника.
    Шаг связи: max(link_edge_factor·L, link_bridge_k·d_knn), чтобы закрыть разреженность.
    После BFS — SVD-плоскость и итеративный донабор точек в eps и в expand_radius от компоненты.
    """
    npt = pos.shape[0]
    inlier_empty = np.zeros(npt, dtype=bool)
    if npt < 3:
        return None, inlier_empty, 0.0

    d_loc = _median_kth_neighbor_distance(pos, k=knn_k, rng=rng)
    extent = _aabb_extent(pos)
    if extent < 1e-5:
        return None, inlier_empty, 0.0
    cap = max(1e-5, float(tolerance_rel_cap) * extent)
    base_eps = float(min(cap, max(1e-5, float(knn_scale) * d_loc)))

    best_mask: Optional[np.ndarray] = None
    best_cnt = 0
    best_eps = base_eps
    best_r_link = max(1e-4, float(link_bridge_k) * d_loc)

    for _ in range(max(1, int(n_seed_tries))):
        seed = int(rng.integers(0, npt))
        d0 = np.linalg.norm(pos - pos[seed], axis=1)
        if npt < 3:
            break
        nn = np.argpartition(d0, 2)[:3]
        i0, i1, i2 = int(nn[0]), int(nn[1]), int(nn[2])
        p0, p1, p2 = pos[i0], pos[i1], pos[i2]
        L = _triangle_longest_edge(p0, p1, p2)
        if L < 1e-9:
            continue
        r_link = max(float(link_edge_factor) * L, float(link_bridge_k) * d_loc)
        eps_plane = min(
            base_eps,
            max(1e-6, float(eps_l_factor) * L, float(eps_knn_factor) * d_loc),
        )

        v1, v2 = p1 - p0, p2 - p0
        cn = np.cross(v1, v2)
        ln = np.linalg.norm(cn)
        if ln < 1e-10:
            continue
        cn = cn / ln
        dd = -float(np.dot(cn, p0))
        dist_plane = np.abs(pos @ cn + dd)

        candidates = np.flatnonzero(dist_plane < eps_plane)
        if candidates.size < min_inliers:
            continue

        inv_r = 1.0 / max(r_link, 1e-9)
        buckets: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
        for idx in candidates:
            cell = tuple(np.floor(pos[idx] * inv_r).astype(np.int32))
            buckets[cell].append(int(idx))

        q: deque[int] = deque()
        visited = np.zeros(npt, dtype=bool)
        for s in (i0, i1, i2):
            if dist_plane[s] < eps_plane:
                visited[s] = True
                q.append(s)
        if len(q) < 3:
            continue

        r2 = r_link * r_link
        while q:
            u = q.popleft()
            bu = np.floor(pos[u] * inv_r).astype(np.int32)
            for ax in (-1, 0, 1):
                for ay in (-1, 0, 1):
                    for az in (-1, 0, 1):
                        key = (int(bu[0] + ax), int(bu[1] + ay), int(bu[2] + az))
                        for v in buckets.get(key, ()):
                            if visited[v]:
                                continue
                            du = pos[u] - pos[v]
                            if float(du @ du) <= r2 + 1e-9:
                                visited[v] = True
                                q.append(v)

        cnt = int(np.sum(visited))
        if cnt > best_cnt:
            best_cnt = cnt
            best_mask = visited.copy()
            best_eps = eps_plane
            best_r_link = r_link
        if cnt >= max(min_inliers, int(0.88 * npt)):
            break

    if best_mask is None or best_cnt < min_inliers:
        return None, inlier_empty, float(best_eps)

    mask = best_mask.astype(bool)
    r_expand = max(
        float(best_r_link) * float(expand_radius_mul),
        float(expand_min_bridge_k) * d_loc,
    )
    report_eps = float(best_eps)

    for _ in range(max(1, int(expand_iters))):
        idxs = np.flatnonzero(mask)
        if idxs.size < 3:
            break
        nfit, dfit = _fit_plane_svd(pos[idxs])
        dist_all = np.abs(pos @ nfit + dfit)
        med_in = float(np.median(dist_all[mask]))
        eps_adapt = min(
            base_eps,
            max(float(best_eps), med_in * 3.0 + 1e-6, 1.4 * d_loc),
        )
        report_eps = max(report_eps, eps_adapt)
        band = dist_all < eps_adapt
        if not np.any(band):
            break
        mask = np.logical_and(mask, band)
        if int(np.sum(mask)) < 3:
            break
        grown = _bfs_within_radius(pos, seed_mask=mask, band_mask=band, radius=r_expand)
        if int(np.sum(grown)) == int(np.sum(mask)):
            break
        mask = grown

    if int(np.sum(mask)) < min_inliers:
        return None, inlier_empty, float(report_eps)

    quad = _quad_from_inliers(pos, col, mask)
    return quad, mask, float(report_eps)


def dominant_planes_rectangles(
    positions: np.ndarray,
    colors: np.ndarray,
    *,
    tolerance_rel_cap: float = 0.1,
    knn_scale: float = 2.5,
    knn_k: int = 8,
    max_planes: int = 8,
    min_inlier_ratio: float = 0.04,
    min_points_remain: int = 80,
    n_seed_tries: int = 36,
    link_edge_factor: float = 1.65,
    link_bridge_k: float = 2.85,
    eps_l_factor: float = 0.16,
    eps_knn_factor: float = 1.75,
    expand_iters: int = 12,
    expand_radius_mul: float = 1.45,
    expand_min_bridge_k: float = 2.65,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]], List[float]]:
    """
    Итеративно: связная плоскость + SVD и донабор; inlier'ы удаляются между итерациями.
    """
    if positions is None or positions.size == 0:
        return positions, colors, [], []

    rng = rng or np.random.default_rng()
    pos = np.asarray(positions, dtype=np.float64)
    col = np.asarray(colors)
    quads: List[Dict[str, Any]] = []
    thresholds_used: List[float] = []

    for _ in range(max(1, int(max_planes))):
        npt = pos.shape[0]
        if npt < 60:
            break
        min_inliers = max(30, int(min_inlier_ratio * npt))

        quad, inlier, eps_u = _one_connected_plane(
            pos,
            col,
            tolerance_rel_cap=tolerance_rel_cap,
            knn_scale=knn_scale,
            knn_k=knn_k,
            min_inliers=min_inliers,
            n_seed_tries=n_seed_tries,
            rng=rng,
            link_edge_factor=link_edge_factor,
            link_bridge_k=link_bridge_k,
            eps_l_factor=eps_l_factor,
            eps_knn_factor=eps_knn_factor,
            expand_iters=expand_iters,
            expand_radius_mul=expand_radius_mul,
            expand_min_bridge_k=expand_min_bridge_k,
        )
        thresholds_used.append(eps_u)
        if quad is None or not np.any(inlier):
            break

        quads.append(quad)
        pos = pos[~inlier].astype(np.float64)
        col = col[~inlier]
        if pos.shape[0] < min_points_remain:
            break

    return pos.astype(np.float32), col, quads, thresholds_used


def dominant_plane_single_rectangle(
    positions: np.ndarray,
    colors: np.ndarray,
    *,
    tolerance_rel: float = 0.1,
    min_inlier_ratio: float = 0.04,
    rng: Optional[np.random.Generator] = None,
    knn_scale: float = 2.5,
    knn_k: int = 8,
    n_seed_tries: int = 36,
    link_edge_factor: float = 1.65,
    link_bridge_k: float = 2.85,
    eps_l_factor: float = 0.16,
    eps_knn_factor: float = 1.75,
    expand_iters: int = 12,
    expand_radius_mul: float = 1.45,
    expand_min_bridge_k: float = 2.65,
) -> Tuple[np.ndarray, np.ndarray, Optional[Dict[str, Any]]]:
    pos_o, col_o, quads, _ = dominant_planes_rectangles(
        positions,
        colors,
        tolerance_rel_cap=tolerance_rel,
        knn_scale=knn_scale,
        knn_k=knn_k,
        max_planes=1,
        min_inlier_ratio=min_inlier_ratio,
        rng=rng,
        n_seed_tries=n_seed_tries,
        link_edge_factor=link_edge_factor,
        link_bridge_k=link_bridge_k,
        eps_l_factor=eps_l_factor,
        eps_knn_factor=eps_knn_factor,
        expand_iters=expand_iters,
        expand_radius_mul=expand_radius_mul,
        expand_min_bridge_k=expand_min_bridge_k,
    )
    return pos_o, col_o, (quads[0] if quads else None)

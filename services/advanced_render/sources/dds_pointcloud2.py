"""DDS sensor_msgs/PointCloud2 → numpy XYZ (best-effort, topic autodiscovery)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Vendored SDK lives under services/unitree_motor_control
_UMC = Path(__file__).resolve().parents[2] / "unitree_motor_control"
if _UMC.is_dir() and str(_UMC) not in sys.path:
    sys.path.insert(0, str(_UMC))

# ROS PointField datatypes
FLOAT32 = 7
FLOAT64 = 8


def _field_offsets(fields: Any) -> Tuple[Optional[int], Optional[int], Optional[int], int]:
    x_off = y_off = z_off = None
    point_step = 0
    try:
        fl = list(fields)
    except Exception:
        return None, None, None, 0
    for f in fl:
        name = str(getattr(f, "name", "") or "").lower()
        off = int(getattr(f, "offset", 0))
        if name == "x":
            x_off = off
        elif name == "y":
            y_off = off
        elif name == "z":
            z_off = off
    return x_off, y_off, z_off, point_step


def parse_pointcloud2_to_xyz(msg: Any, max_points: int) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Parse cyclonedds PointCloud2_ message to (N,3) float32."""
    meta: Dict[str, Any] = {"source": "dds_pointcloud2", "count": 0}
    try:
        point_step = int(getattr(msg, "point_step", 0) or 0)
        width = int(getattr(msg, "width", 0) or 0)
        height = int(getattr(msg, "height", 0) or 0)
        data_seq = getattr(msg, "data", None)
        if data_seq is None or point_step <= 0 or width <= 0:
            return np.zeros((0, 3), np.float32), meta
        raw = bytes(bytearray(data_seq))
        n_decl = width * height if height > 0 else width
        n_buf = len(raw) // point_step
        n_points = min(n_decl, n_buf)
        if n_points <= 0:
            return np.zeros((0, 3), np.float32), meta

        fields = getattr(msg, "fields", [])
        x_off = y_off = z_off = None
        x_dt = y_dt = z_dt = FLOAT32
        try:
            for f in list(fields):
                name = str(getattr(f, "name", "") or "").lower()
                off = int(getattr(f, "offset", 0))
                dt = int(getattr(f, "datatype", FLOAT32))
                if name == "x":
                    x_off, x_dt = off, dt
                elif name == "y":
                    y_off, y_dt = off, dt
                elif name == "z":
                    z_off, z_dt = off, dt
        except Exception:
            pass
        if x_off is None or y_off is None or z_off is None:
            meta["error"] = "missing_xyz_fields"
            return np.zeros((0, 3), np.float32), meta

        view = np.frombuffer(raw, dtype=np.uint8, count=n_points * point_step)
        view = view.reshape(n_points, point_step)

        def read_comp(row: np.ndarray, off: int, dt: int) -> float:
            sl = row[off : off + (8 if dt == FLOAT64 else 4)]
            if dt == FLOAT64:
                return float(np.frombuffer(sl.tobytes(), dtype=np.float64, count=1)[0])
            return float(np.frombuffer(sl.tobytes(), dtype=np.float32, count=1)[0])

        # Subsample if too many
        if n_points > max_points:
            idx = np.random.choice(n_points, max_points, replace=False)
        else:
            idx = np.arange(n_points, dtype=np.int64)

        out = np.empty((idx.shape[0], 3), dtype=np.float32)
        for i, j in enumerate(idx.tolist()):
            row = view[j]
            try:
                out[i, 0] = read_comp(row, x_off, x_dt)
                out[i, 1] = read_comp(row, y_off, y_dt)
                out[i, 2] = read_comp(row, z_off, z_dt)
            except Exception:
                out[i, :] = 0.0
        # Drop NaN
        m = np.isfinite(out).all(axis=1) & (np.abs(out).sum(axis=1) > 1e-6)
        out = out[m]
        meta["count"] = int(out.shape[0])
        return out, meta
    except Exception as e:
        meta["error"] = str(e)
        return np.zeros((0, 3), np.float32), meta


def _dds_init() -> Tuple[bool, str, int]:
    network = os.environ.get("RGW2_UNITREE_DDS_IF", "eth0")
    domain = int(os.environ.get("RGW2_UNITREE_DDS_DOMAIN", "0"))
    try:
        import services_manager

        m = services_manager.get_services_manager()
        p = m.get_service_parameters("unitree_motor_control")
        network = p.get("network", network)
        domain = int(p.get("id", domain))
    except Exception:
        pass
    try:
        from unitree_sdk2py.core.channel import ChannelFactory

        ChannelFactory().Init(id=domain, networkInterface=network)
        return True, network, domain
    except Exception as e:
        return False, str(e), domain


def read_pointcloud2_once(topic: str, timeout_sec: float = 0.5) -> Tuple[np.ndarray, Dict[str, Any]]:
    meta: Dict[str, Any] = {"topic": topic, "source": "dds_pointcloud2"}
    ok, net_or_err, _ = _dds_init()
    if not ok:
        meta["error"] = f"dds_init:{net_or_err}"
        return np.zeros((0, 3), np.float32), meta
    try:
        from unitree_sdk2py.core.channel import ChannelSubscriber
        from unitree_sdk2py.idl.sensor_msgs.msg.dds_ import PointCloud2_

        sub = ChannelSubscriber(topic, PointCloud2_)
        sub.Init()
        msg = sub.Read(timeout=float(timeout_sec))
        try:
            sub.Close()
        except Exception:
            pass
        if msg is None:
            meta["error"] = "no_sample"
            return np.zeros((0, 3), np.float32), meta
        max_p = int(os.environ.get("RGW2_DDS_POINTCLOUD_MAX_PARSE", "50000"))
        pts, pm = parse_pointcloud2_to_xyz(msg, max_p)
        meta.update(pm)
        return pts, meta
    except Exception as e:
        meta["error"] = str(e)
        return np.zeros((0, 3), np.float32), meta


def autodiscover_topic(candidates: List[str], timeout_per_topic: float = 0.35) -> Tuple[Optional[str], np.ndarray, Dict[str, Any]]:
    for t in candidates:
        pts, meta = read_pointcloud2_once(t, timeout_sec=timeout_per_topic)
        if pts.shape[0] > 0:
            return t, pts, meta
    return None, np.zeros((0, 3), np.float32), {"error": "no_topic_matched"}


def xyz_to_colors_by_range(pts: np.ndarray, z_near: float = 0.1, z_far: float = 30.0) -> np.ndarray:
    if pts.shape[0] == 0:
        return np.zeros((0, 3), np.uint8)
    # use distance from origin for coloring
    d = np.linalg.norm(pts, axis=1).astype(np.float32)
    t = 1.0 - np.clip((d - z_near) / max(1e-3, (z_far - z_near)), 0.0, 1.0)
    v = (t * 255.0).astype(np.uint8)
    return np.stack([v, 255 - v // 2, v // 2], axis=1).astype(np.uint8)


class DDSPointCloudBuffer:
    """Background DDS reader; keeps latest XYZ + resolved topic."""

    def __init__(self, cfg: Dict[str, Any]):
        self._cfg = cfg
        self._lock = threading.Lock()
        self._pts = np.zeros((0, 3), np.float32)
        self._cols = np.zeros((0, 3), np.uint8)
        self._ts = 0.0
        self._topic: Optional[str] = None
        self._meta: Dict[str, Any] = {}
        self._running = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if self._running:
            return True
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        cfg = self._cfg
        explicit = cfg.get("topic")
        candidates: List[str] = []
        if explicit:
            candidates = [str(explicit)]
        else:
            env_t = os.environ.get("RGW2_DDS_POINTCLOUD_TOPIC", "").strip()
            if env_t:
                candidates.append(env_t)
            for c in cfg.get("candidate_topics") or []:
                if c and c not in candidates:
                    candidates.append(str(c))
        timeout = float(cfg.get("read_timeout_sec") or 0.35)
        max_points = int(cfg.get("max_points") or 20000)
        z_near = float(os.environ.get("RGW2_ADV_Z_NEAR", "0.25"))
        z_far = float(os.environ.get("RGW2_ADV_Z_FAR", "20"))

        resolved = None
        if candidates:
            resolved, pts0, meta0 = autodiscover_topic(candidates, timeout_per_topic=timeout)
            if resolved and pts0.shape[0] > 0:
                self._topic = resolved
                cols0 = xyz_to_colors_by_range(pts0, z_near, z_far)
                with self._lock:
                    self._pts = pts0
                    self._cols = cols0
                    self._ts = time.time()
                    self._meta = {**meta0, "topic": resolved}

        persistent_sub = None
        while self._running and not self._stop.is_set():
            topic = self._topic
            if not topic:
                time.sleep(0.5)
                continue
            try:
                if persistent_sub is None:
                    from unitree_sdk2py.core.channel import ChannelSubscriber
                    from unitree_sdk2py.idl.sensor_msgs.msg.dds_ import PointCloud2_

                    persistent_sub = ChannelSubscriber(topic, PointCloud2_)
                    persistent_sub.Init()
                msg = persistent_sub.Read(timeout=float(timeout))
                if msg is None:
                    time.sleep(0.02)
                    continue
                max_p = int(os.environ.get("RGW2_DDS_POINTCLOUD_MAX_PARSE", "50000"))
                pts, meta = parse_pointcloud2_to_xyz(msg, max_p)
            except Exception:
                pts = np.zeros((0, 3), np.float32)
                meta = {"error": "read_failed"}
                try:
                    if persistent_sub is not None:
                        persistent_sub.Close()
                except Exception:
                    pass
                persistent_sub = None
                time.sleep(0.2)
                continue

            if pts.shape[0] > max_points:
                idx = np.random.choice(pts.shape[0], max_points, replace=False)
                pts = pts[idx]
            if pts.shape[0] > 0:
                cols = xyz_to_colors_by_range(pts, z_near, z_far)
                with self._lock:
                    self._pts = pts
                    self._cols = cols
                    self._ts = time.time()
                    self._meta = {**meta, "topic": topic, "id": cfg.get("id", "dds")}
            else:
                time.sleep(0.02)

    def snapshot(self) -> Tuple[np.ndarray, np.ndarray, float, Dict[str, Any]]:
        with self._lock:
            return (
                self._pts.copy(),
                self._cols.copy(),
                float(self._ts),
                dict(self._meta),
            )

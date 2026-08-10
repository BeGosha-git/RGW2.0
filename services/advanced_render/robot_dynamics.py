"""Визуальная «живая» динамика поверх реальных q (для превью, не физика)."""

from __future__ import annotations

import math
import os
from typing import List, Optional, Sequence, Tuple


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


def dynamics_enabled() -> bool:
    return os.environ.get("RGW2_VISER_DYNAMICS", "1").lower() not in ("0", "false", "no", "off")


def visual_motor_offsets(
    motor_q: Sequence[float],
    t: float,
    *,
    joint_amp_rad: Optional[float] = None,
    joint_hz: Optional[float] = None,
    base_amp_m: Optional[float] = None,
    base_hz: Optional[float] = None,
) -> Tuple[List[float], Tuple[float, float]]:
    """
    Возвращает (q с лёгкими синусами по суставам, (dx, dy) сдвиг базы в XY в метрах)).
    """
    if joint_amp_rad is None:
        joint_amp_rad = _env_float("RGW2_VISER_DYNAMICS_JOINT_AMP", 0.065)
    if joint_hz is None:
        joint_hz = _env_float("RGW2_VISER_DYNAMICS_JOINT_HZ", 0.38)
    if base_amp_m is None:
        base_amp_m = _env_float("RGW2_VISER_DYNAMICS_BASE_AMP", 0.024)
    if base_hz is None:
        base_hz = _env_float("RGW2_VISER_DYNAMICS_BASE_HZ", 0.17)

    w = 2.0 * math.pi
    q_list = [float(x) for x in motor_q]
    q_out = [
        q + joint_amp_rad * math.sin(w * joint_hz * t + i * 0.41 + 0.1 * math.sin(w * 0.09 * t))
        for i, q in enumerate(q_list)
    ]
    bx = base_amp_m * math.sin(w * base_hz * t)
    by = base_amp_m * math.cos(w * base_hz * t * 0.87)
    return q_out, (bx, by)


def apply_if_enabled(motor_q: Sequence[float], t: float) -> Tuple[List[float], Tuple[float, float]]:
    if not dynamics_enabled():
        return [float(x) for x in motor_q], (0.0, 0.0)
    return visual_motor_offsets(motor_q, t)


def base_shift_visual(t: float) -> Tuple[float, float]:
    """
    Только сдвиг «базы» в XY для превью (без изменения углов суставов).
    Используется вместе с FK G1, чтобы не портить q из lowstate синусами.
    """
    if not dynamics_enabled():
        return (0.0, 0.0)
    base_amp_m = _env_float("RGW2_VISER_DYNAMICS_BASE_AMP", 0.024)
    base_hz = _env_float("RGW2_VISER_DYNAMICS_BASE_HZ", 0.17)
    w = 2.0 * math.pi
    bx = base_amp_m * math.sin(w * base_hz * t)
    by = base_amp_m * math.cos(w * base_hz * t * 0.87)
    return (bx, by)

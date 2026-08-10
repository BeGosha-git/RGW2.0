"""
G1 в Viser только через MuJoCo (без mjlab / без USD): MJCF g1.xml, меши из MjModel,
склейка геомов в trimesh, позы — mj_forward + xpos/xmat.

Путь к модели: переменная RGW2_G1_MJCF (полный путь к g1.xml).
Если не задана — ищется файл рядом с проектом или в ~/unitree_rl_mjlab/... (только как путь к XML, пакет mjlab не нужен).
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import trimesh
import trimesh.visual

try:
    import mujoco
except ImportError:
    mujoco = None  # type: ignore

try:
    import viser.transforms as vtf
except ImportError:
    vtf = None  # type: ignore

G1_NUM_MOTORS = 29

# Порядок = lowstate[i] / примеры SDK (как в MJCF g1.xml).
G1_ACTUATED_JOINT_NAMES: Tuple[str, ...] = (
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)


def resolve_g1_mjcf_path() -> Optional[Path]:
    env = os.environ.get("RGW2_G1_MJCF", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_file() else None

    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    candidates = [
        repo_root / "data" / "unitree_model" / "G1" / "mjcf" / "g1.xml",
        Path.home() / "unitree_rl_mjlab" / "mjlab" / "asset_zoo" / "robots" / "unitree_g1" / "xmls" / "g1.xml",
        Path("/home/g100/unitree_rl_mjlab/mjlab/asset_zoo/robots/unitree_g1/xmls/g1.xml"),
    ]
    extra = os.environ.get("RGW2_G1_MJCF_SEARCH_DIR", "").strip()
    if extra:
        d = Path(extra).expanduser().resolve()
        if d.is_dir():
            candidates.insert(0, d / "g1.xml")

    for p in candidates:
        if p.is_file():
            return p
    return None


def _get_body_name(mj_model: Any, body_id: int) -> str:
    n = mujoco.mj_id2name(mj_model, mujoco.mjtObj.mjOBJ_BODY, body_id)
    return n if n else f"body_{body_id}"


def _is_fixed_body(mj_model: Any, body_id: int) -> bool:
    is_weld = mj_model.body_weldid[body_id] == 0
    root_id = mj_model.body_rootid[body_id]
    root_is_mocap = mj_model.body_mocapid[root_id] >= 0
    return bool(is_weld and not root_is_mocap)


def _mujoco_mesh_to_trimesh_local(mj_model: Any, geom_idx: int) -> trimesh.Trimesh:
    """MjModel mesh geom → trimesh (вершины/грани + цвет материала)."""
    mesh_id = mj_model.geom_dataid[geom_idx]
    vert_start = int(mj_model.mesh_vertadr[mesh_id])
    vert_count = int(mj_model.mesh_vertnum[mesh_id])
    face_start = int(mj_model.mesh_faceadr[mesh_id])
    face_count = int(mj_model.mesh_facenum[mesh_id])
    vertices = np.array(
        mj_model.mesh_vert[vert_start : vert_start + vert_count], dtype=np.float64
    )
    faces = np.array(
        mj_model.mesh_face[face_start : face_start + face_count], dtype=np.int64
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    matid = mj_model.geom_matid[geom_idx]
    if matid >= 0 and matid < mj_model.nmat:
        rgba = mj_model.mat_rgba[matid]
        rgba_255 = (rgba * 255).astype(np.uint8)
        mesh.visual = trimesh.visual.ColorVisuals(
            vertex_colors=np.tile(rgba_255, (len(mesh.vertices), 1))
        )
    else:
        c = np.array([31, 128, 230, 255], dtype=np.uint8)
        mesh.visual = trimesh.visual.ColorVisuals(vertex_colors=np.tile(c, (len(mesh.vertices), 1)))
    return mesh


def _merge_geoms_local(mj_model: Any, geom_ids: List[int]) -> trimesh.Trimesh:
    meshes: List[trimesh.Trimesh] = []
    for geom_id in geom_ids:
        gt = mj_model.geom_type[geom_id]
        if int(gt) != int(mujoco.mjtGeom.mjGEOM_MESH):
            continue
        m = _mujoco_mesh_to_trimesh_local(mj_model, geom_id)
        pos = mj_model.geom_pos[geom_id]
        quat = mj_model.geom_quat[geom_id]
        transform = np.eye(4, dtype=np.float64)
        if vtf is not None:
            transform[:3, :3] = vtf.SO3(np.asarray(quat, dtype=np.float64)).as_matrix()
        else:
            rot9 = np.zeros(9, dtype=np.float64)
            mujoco.mju_quat2Mat(rot9, quat)
            transform[:3, :3] = rot9.reshape(3, 3)
        transform[:3, 3] = pos
        m.apply_transform(transform)
        meshes.append(m)
    if not meshes:
        b = trimesh.creation.box([0.001, 0.001, 0.001])
        b.visual.face_colors = [40, 40, 45, 255]
        return b
    if len(meshes) == 1:
        return meshes[0]
    return trimesh.util.concatenate(meshes)


def g1_mujoco_viser_enabled() -> bool:
    return os.environ.get("RGW2_VISER_G1_MUJOCO", "1").lower() not in ("0", "false", "no", "off")


def try_setup_g1_mujoco_viser(server: Any) -> Optional[Dict[str, Any]]:
    """
    Один merged trimesh на пару (body, geom_group); обновление из mj_forward.
    """
    if mujoco is None or not g1_mujoco_viser_enabled():
        return None
    xml = resolve_g1_mjcf_path()
    if xml is None:
        print(
            "[viser] G1 MuJoCo: нет g1.xml — укажите RGW2_G1_MJCF=/полный/путь/g1.xml "
            "(рядом с XML должна быть папка assets/ со STL, как в модели Unitree).",
            flush=True,
        )
        return None
    try:
        mj_model = mujoco.MjModel.from_xml_path(str(xml))
        mj_data = mujoco.MjData(mj_model)
    except Exception as e:
        print(f"[viser] G1 MuJoCo: не удалось загрузить MJCF: {e}", flush=True)
        return None

    body_group_geoms: Dict[Tuple[int, int], List[int]] = {}
    for i in range(mj_model.ngeom):
        body_id = int(mj_model.geom_bodyid[i])
        if _is_fixed_body(mj_model, body_id):
            continue
        gid = int(mj_model.geom_group[i])
        key = (body_id, gid)
        body_group_geoms.setdefault(key, []).append(i)

    handles: Dict[Tuple[int, int], Any] = {}
    try:
        import contextlib

        try:
            ctx = server.atomic()
        except AttributeError:
            ctx = contextlib.nullcontext()
        with ctx:
            for (body_id, group_id), geom_indices in body_group_geoms.items():
                if not geom_indices:
                    continue
                mesh = _merge_geoms_local(mj_model, geom_indices)
                # Один сегмент под /world: иначе Viser строит родителя по пути, и мировые
                # xpos/xmat из mj_forward ошибочно трактуются как локальные — суставы «не двигаются».
                path = f"/world/rgw_g1_b{body_id}_g{group_id}"
                h = server.scene.add_mesh_trimesh(
                    path,
                    mesh=mesh,
                    wxyz=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    position=np.zeros(3, dtype=np.float32),
                    visible=(group_id == 2),
                )
                handles[(body_id, group_id)] = h
    except Exception as e:
        print(f"[viser] G1 MuJoCo: создание мешей: {e}", flush=True)
        return None

    # Индексы qpos для приводов
    fj = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_JOINT, "floating_base_joint")
    if fj < 0:
        print("[viser] G1 MuJoCo: в модели нет floating_base_joint", flush=True)
        return None
    free_qadr = int(mj_model.jnt_qposadr[fj])

    joint_jids: List[int] = []
    for jn in G1_ACTUATED_JOINT_NAMES:
        jid = mujoco.mj_name2id(mj_model, mujoco.mjtObj.mjOBJ_JOINT, jn)
        if jid < 0:
            print(f"[viser] G1 MuJoCo: нет сустава {jn!r}", flush=True)
            return None
        joint_jids.append(int(jid))

    print(f"[viser] G1 MuJoCo: {xml} ({len(handles)} узлов)", flush=True)
    return {
        "mj_model": mj_model,
        "mj_data": mj_data,
        "handles": handles,
        "free_qadr": free_qadr,
        "joint_jids": joint_jids,
    }


def _limb_synth_blend(motor_q: Sequence[float], mode: str, i0: int, i1: int) -> float:
    """0 = только реальные углы; 1 = полная амплитуда синтеза на диапазоне моторов [i0, i1)."""
    m = mode.strip().lower()
    if m in ("0", "false", "no", "off"):
        return 0.0
    if m == "always":
        return 1.0
    mx = 0.0
    for j in range(i0, min(i1, len(motor_q))):
        mx = max(mx, abs(float(motor_q[j])))
    return float(max(0.0, min(1.0, 1.0 - mx / 0.22)))


def update_g1_mujoco_viser(
    state: Dict[str, Any],
    motor_q: Sequence[float],
    base_xy: Tuple[float, float],
) -> None:
    mj_model = state["mj_model"]
    mj_data = state["mj_data"]
    d = mj_data
    m = mj_model

    d.qpos[:] = m.qpos0
    fq = int(state["free_qadr"])
    d.qpos[fq : fq + 3] = [float(base_xy[0]), float(base_xy[1]), float(m.qpos0[fq + 2])]
    d.qpos[fq + 3 : fq + 7] = m.qpos0[fq + 3 : fq + 7]

    synth_mode = os.environ.get("RGW2_VISER_G1_ARM_SYNTH", "auto")
    leg_amp = float(os.environ.get("RGW2_VISER_G1_LEG_SYNTH_RAD", "0.14"))
    leg_hz = float(os.environ.get("RGW2_VISER_G1_LEG_SYNTH_HZ", "0.34"))
    arm_amp = float(os.environ.get("RGW2_VISER_G1_ARM_SYNTH_RAD", "0.16"))
    arm_hz = float(os.environ.get("RGW2_VISER_G1_ARM_SYNTH_HZ", "0.45"))
    blend_leg = _limb_synth_blend(motor_q, synth_mode, 0, 12)
    blend_arm = _limb_synth_blend(motor_q, synth_mode, 15, 29)
    t = time.monotonic()
    omega_leg = 2.0 * math.pi * max(0.05, leg_hz)
    omega_arm = 2.0 * math.pi * max(0.05, arm_hz)

    jids: List[int] = state["joint_jids"]
    for i, jid in enumerate(jids):
        adr = int(m.jnt_qposadr[jid])
        q = float(motor_q[i]) if i < len(motor_q) else 0.0
        if blend_leg > 1e-6 and 0 <= i < 12:
            q += blend_leg * leg_amp * math.sin(omega_leg * t + 0.41 * float(i))
        if blend_arm > 1e-6 and 15 <= i < 29:
            q += blend_arm * arm_amp * math.sin(omega_arm * t + 0.55 * float(i))
        lo, hi = float(m.jnt_range[jid, 0]), float(m.jnt_range[jid, 1])
        if hi > lo:
            q = float(np.clip(q, lo, hi))
        d.qpos[adr] = q

    mujoco.mj_forward(m, d)

    handles: Dict[Tuple[int, int], Any] = state["handles"]
    for (body_id, _gid), h in handles.items():
        xpos = np.array(d.xpos[body_id], dtype=np.float64)
        # xmat в плоском виде — порядок осей зависит от раскладки; xquat из MuJoCo совпадает с кинематикой.
        q_b = np.asarray(d.xquat[body_id], dtype=np.float64)
        wxyz = np.array([q_b[0], q_b[1], q_b[2], q_b[3]], dtype=np.float32)
        try:
            h.wxyz = wxyz
            h.position = xpos.astype(np.float32)
        except Exception:
            pass

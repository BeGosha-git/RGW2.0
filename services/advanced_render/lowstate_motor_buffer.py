"""Подписка на rt/lowstate (Unitree DDS) → углы моторов q для оверлея и Viser."""

from __future__ import annotations

import os
import threading
import time
from typing import List, Optional, Tuple


class LowStateMotorBuffer:
    def __init__(self, n_joints: int):
        self._n_joints = int(n_joints)
        self._lock = threading.Lock()
        self._motor_q: List[float] = [0.0] * self._n_joints
        self._motor_last_ts: float = 0.0
        self._running = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop.set()

    def snapshot(self) -> Tuple[List[float], float]:
        with self._lock:
            return list(self._motor_q), float(self._motor_last_ts)

    def _loop(self) -> None:
        sub = None
        try:
            from unitree_sdk2py.core.channel import ChannelFactory, ChannelSubscriber

            network_interface = os.environ.get("RGW2_UNITREE_DDS_IF", "eth0")
            domain_id = int(os.environ.get("RGW2_UNITREE_DDS_DOMAIN", "0"))
            try:
                import services_manager

                manager = services_manager.get_services_manager()
                params = manager.get_service_parameters("unitree_motor_control")
                network_interface = params.get("network", network_interface)
                domain_id = int(params.get("id", domain_id))
            except Exception:
                pass

            ChannelFactory().Init(id=domain_id, networkInterface=network_interface)

            lowstate_hg = None
            lowstate_go = None
            try:
                from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_ as HGLowState_

                lowstate_hg = HGLowState_
            except Exception:
                lowstate_hg = None
            try:
                from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_ as GoLowState_

                lowstate_go = GoLowState_
            except Exception:
                lowstate_go = None

            msg_type = lowstate_hg or lowstate_go
            if msg_type is None:
                return

            sub = ChannelSubscriber("rt/lowstate", msg_type)
            sub.Init()

            while self._running and not self._stop.is_set():
                msg = sub.Read(timeout=0.2)
                if msg is None:
                    continue
                ms_any = getattr(msg, "motor_state", None)
                if ms_any is None:
                    continue
                try:
                    ms_list = list(ms_any)
                except Exception:
                    ms_list = []

                q_list: List[float] = []
                for i, m in enumerate(ms_list):
                    if i >= self._n_joints:
                        break
                    try:
                        q_list.append(float(getattr(m, "q", 0.0)))
                    except Exception:
                        q_list.append(0.0)

                with self._lock:
                    if len(q_list) >= self._n_joints:
                        self._motor_q = q_list[: self._n_joints]
                    else:
                        self._motor_q = q_list + [0.0] * (self._n_joints - len(q_list))
                    self._motor_last_ts = time.time()
        except Exception:
            return
        finally:
            if sub is not None:
                try:
                    sub.Close()
                except Exception:
                    pass

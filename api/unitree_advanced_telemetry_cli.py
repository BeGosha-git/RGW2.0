#!/usr/bin/env python3
"""
Read advanced Unitree telemetry via DDS (motor angles & dynamics).

We run this in a separate process (invoked by api/robot.py) to reduce the
risk of native CycloneDDS crashes taking down rgw2.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional


def _json_out(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _to_list(motor_state_any: Any) -> List[Any]:
    # cyclonedds arrays are iterable, but be defensive.
    try:
        return list(motor_state_any)
    except Exception:
        return []


def main() -> int:
    if len(sys.argv) < 4:
        _json_out({"success": False, "message": "args: <project_root> <network_interface> <domain_id>"})
        return 2

    project_root = sys.argv[1]
    network_interface = sys.argv[2]
    domain_id = int(sys.argv[3])

    # Make vendored SDK available
    sys.path.insert(0, f"{project_root.rstrip('/')}/services/unitree_motor_control")

    try:
        from unitree_sdk2py.core.channel import ChannelFactory, ChannelSubscriber
    except Exception as e:
        _json_out({"success": False, "message": f"Failed to import unitree_sdk2py: {e}"})
        return 3

    # Init DDS
    try:
        ChannelFactory().Init(id=domain_id, networkInterface=network_interface)
    except Exception as e:
        _json_out({"success": False, "message": f"DDS init failed: {e}", "network": network_interface, "domain_id": domain_id})
        return 4

    lowstate = None
    mode = None

    def try_read_lowstate_go(timeout_s: float = 2.0) -> bool:
        nonlocal lowstate, mode
        try:
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_ as GoLowState_

            sub = ChannelSubscriber("rt/lowstate", GoLowState_)
            sub.Init()
            lowstate = sub.Read(timeout=timeout_s)
            sub.Close()
            if lowstate is not None:
                mode = "go_lowstate"
                return True
        except Exception:
            return False
        return False

    def try_read_lowstate_hg(timeout_s: float = 2.0) -> bool:
        nonlocal lowstate, mode
        try:
            from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_ as HGLowState_

            sub = ChannelSubscriber("rt/lowstate", HGLowState_)
            sub.Init()
            lowstate = sub.Read(timeout=timeout_s)
            sub.Close()
            if lowstate is not None:
                mode = "hg_lowstate"
                return True
        except Exception:
            return False
        return False

    ok = try_read_lowstate_go() or try_read_lowstate_hg()

    motor_q: List[Optional[float]] = []
    motor_dq: List[Optional[float]] = []
    motor_ddq: List[Optional[float]] = []
    motor_tau_est: List[Optional[float]] = []
    motor_temp0: List[Optional[float]] = []
    motor_temp1: List[Optional[float]] = []

    motor_count = 0

    if ok and lowstate is not None:
        try:
            ms_any = getattr(lowstate, "motor_state", None)
            motor_state = _to_list(ms_any) if ms_any is not None else []
            motor_count = len(motor_state)

            for m in motor_state:
                motor_q.append(float(getattr(m, "q", 0.0)))
                motor_dq.append(float(getattr(m, "dq", 0.0)))
                motor_ddq.append(float(getattr(m, "ddq", 0.0)))
                motor_tau_est.append(float(getattr(m, "tau_est", 0.0)))

                temps = getattr(m, "temperature", None)
                # temps is array[2] for both GO/HG in this SDK.
                if temps is None:
                    motor_temp0.append(None)
                    motor_temp1.append(None)
                else:
                    temps_l = _to_list(temps)
                    if len(temps_l) >= 2:
                        motor_temp0.append(float(temps_l[0]))
                        motor_temp1.append(float(temps_l[1]))
                    elif len(temps_l) == 1:
                        motor_temp0.append(float(temps_l[0]))
                        motor_temp1.append(None)
                    else:
                        motor_temp0.append(None)
                        motor_temp1.append(None)
        except Exception:
            # Keep whatever we collected (possibly empty).
            pass

    out: Dict[str, Any] = {
        "success": bool(ok and lowstate is not None and motor_count > 0),
        "mode": mode,
        "motor_count": motor_count,
        "motor_q": motor_q,
        "motor_dq": motor_dq,
        "motor_ddq": motor_ddq,
        "motor_tau_est": motor_tau_est,
        "motor_temp0": motor_temp0,
        "motor_temp1": motor_temp1,
        "ts": time.time(),
    }
    if not out["success"]:
        out["message"] = "No lowstate samples received (check DDS network interface/domain id/robot power)"

    _json_out(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


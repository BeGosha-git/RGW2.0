#!/usr/bin/env python3
"""
Read Unitree telemetry (battery + motor temps) via DDS in a subprocess.

We run this in a separate process to avoid native CycloneDDS crashes taking down rgw2.

Usage:
  python3 api/unitree_telemetry_cli.py <project_root> <network_interface> <domain_id>
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, List, Optional


def _json_out(obj: Dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _summarize_motor_temps(values: List[float]) -> Dict[str, Any]:
    xs = [float(x) for x in values if x is not None]
    if not xs:
        return {"count": 0}
    xs_sorted = sorted(xs)
    return {
        "count": len(xs_sorted),
        "min": xs_sorted[0],
        "max": xs_sorted[-1],
        "avg": sum(xs_sorted) / len(xs_sorted),
    }


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

    # Try reading lowstate (GO) first, then HG (G1/H1), then try BmsState_ topic for HG.
    lowstate = None
    mode = None

    def try_read_lowstate_go(timeout_s: float = 2.0):
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

    def try_read_lowstate_hg(timeout_s: float = 2.0):
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

    # G1 uses unitree_hg LowState_ on rt/lowstate; topic name confirmed by Unitree SDK2 docs.
    ok = try_read_lowstate_go() or try_read_lowstate_hg()

    soc: Optional[float] = None
    battery_current: Optional[float] = None
    motor_temps: List[float] = []
    bms_temps: List[float] = []
    mainboard_temps: List[float] = []
    extra: Dict[str, Any] = {}

    if ok and lowstate is not None:
        # Battery (present in GO LowState)
        try:
            bms = getattr(lowstate, "bms_state", None)
            if bms is not None and hasattr(bms, "soc"):
                soc = float(getattr(bms, "soc"))
                battery_current = float(getattr(bms, "current", 0.0))
        except Exception:
            pass

        # Motor temperatures
        try:
            ms = getattr(lowstate, "motor_state", None)
            if ms is not None:
                # cyclonedds arrays are iterable, but guard just in case
                seq = list(ms) if not isinstance(ms, list) else ms
                for m in seq:
                    t = getattr(m, "temperature", None)
                    if t is None:
                        continue
                    # GO: uint8; HG: array[int16,2]
                    if isinstance(t, (list, tuple)):
                        for x in t:
                            try:
                                motor_temps.append(float(x))
                            except Exception:
                                pass
                    else:
                        try:
                            motor_temps.append(float(t))
                        except Exception:
                            pass
        except Exception:
            pass

        # Extra board temps if present (GO LowState has temperature_ntc1/2)
        try:
            ntc1 = getattr(lowstate, "temperature_ntc1", None)
            ntc2 = getattr(lowstate, "temperature_ntc2", None)
            if ntc1 is not None:
                extra["ntc1"] = float(ntc1)
            if ntc2 is not None:
                extra["ntc2"] = float(ntc2)
        except Exception:
            pass

    # HG LowState_ (G1/H1) does not always include BMS in our IDL.
    # Try separate HG BmsState topic name variants (best-effort).
    if soc is None:
        try:
            from unitree_sdk2py.idl.unitree_hg.msg.dds_ import BmsState_ as HGBmsState_

            # Include the real topic discovered on your G1:
            #   rt/lf/bmsstate
            # plus other known variants.
            for topic in (
                "rt/lf/bmsstate",
                "rt/lf/bms_state",
                "rt/lf/bms",
                "rt/lf/bmsState",
                "rt/lf/bmsState_",
                "rt/bmsstate",
                "rt/bms_state",
                "rt/bms",
                "rt/bmsState",
                "rt/bmsState_",
            ):
                try:
                    sub = ChannelSubscriber(topic, HGBmsState_)
                    sub.Init()
                    msg = sub.Read(timeout=2.5)
                    sub.Close()
                    if msg is not None and hasattr(msg, "soc"):
                        soc = float(getattr(msg, "soc"))
                        battery_current = float(getattr(msg, "current", 0.0))
                        try:
                            temps = getattr(msg, "temperature", None)
                            if temps is not None:
                                for x in list(temps):
                                    try:
                                        bms_temps.append(float(x))
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        extra["bms_topic"] = topic
                        break
                except Exception:
                    continue
        except Exception:
            pass

    # Mainboard temperatures (discovered topic on your G1: rt/lf/mainboardstate).
    try:
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import MainBoardState_ as HGMainBoardState_
        for topic in (
            "rt/lf/mainboardstate",
            "rt/lf/mainboard_state",
            "rt/lf/mainboard",
            "rt/mainboardstate",
            "rt/mainboard_state",
        ):
            try:
                sub = ChannelSubscriber(topic, HGMainBoardState_)
                sub.Init()
                msg = sub.Read(timeout=2.0)
                sub.Close()
                if msg is not None and hasattr(msg, "temperature"):
                    temps = getattr(msg, "temperature", None)
                    if temps is not None:
                        for x in list(temps):
                            try:
                                mainboard_temps.append(float(x))
                            except Exception:
                                pass
                    extra["mainboard_topic"] = topic
                    # stop after first successful read
                    if mainboard_temps:
                        break
            except Exception:
                continue
    except Exception:
        pass

    out = {
        "success": True if (soc is not None or motor_temps) else False,
        "mode": mode,
        "soc": soc,
        "battery_current": battery_current,
        # Backward/compat fields for UI and debugging.
        "motor_temps": _summarize_motor_temps(motor_temps + bms_temps + mainboard_temps),
        "bms_temps": _summarize_motor_temps(bms_temps),
        "battery_temps": _summarize_motor_temps(bms_temps + mainboard_temps),
        "extra": extra,
        "ts": time.time(),
    }
    if not out["success"]:
        out["message"] = "No telemetry samples received (check DDS network interface, domain id, and robot power)"
    _json_out(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


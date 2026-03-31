"""
G1 loco (FSM/mode) helper executed in a subprocess.

We keep all Unitree SDK imports isolated here to avoid crashing the main RGW2 process
in case DDS/native init is unstable on some machines.

CLI:
  python3 api/g1_loco_cli.py <PROJECT_ROOT> <net_if> <domain_id> <op> <payload_json>

Outputs one JSON line to stdout.
"""

from __future__ import annotations

import json
import sys


def _fail(message: str, **extra):
    out = {"success": False, "message": message}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    raise SystemExit(0)


def main(argv: list[str]) -> int:
    if len(argv) < 6:
        _fail("usage: g1_loco_cli.py <PROJECT_ROOT> <net_if> <domain_id> <op> <payload_json>")

    project_root = argv[1]
    net_if = argv[2]
    try:
        domain_id = int(argv[3])
    except Exception:
        _fail("invalid domain_id", domain_id=argv[3])
    op = str(argv[4] or "").strip().lower()
    try:
        payload = json.loads(argv[5])
    except Exception:
        _fail("invalid payload_json")

    sys.path.insert(0, project_root)
    # unitree_sdk2py lives inside services/unitree_motor_control in this repo
    sys.path.insert(0, f"{project_root.rstrip('/')}/services/unitree_motor_control")

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

    ChannelFactoryInitialize(domain_id, net_if)
    service_name = str(payload.get("service_name") or "").strip().lower() or "sport"
    c = None

    def do(service: str) -> dict:
        client = LocoClient(service_name=service)
        try:
            client.SetTimeout(5.0)
        except Exception:
            pass
        client.Init()

        rc = 0

        if op == "mode":
            mode = str(payload.get("mode", "")).strip().lower()
            args = payload.get("args", [])
            if not isinstance(args, list):
                args = [args]

            if mode == "start":
                rc = client.Start()
            elif mode == "damp":
                rc = client.Damp()
            elif mode == "zero_torque":
                rc = client.ZeroTorque()
            elif mode == "sit":
                rc = client.Sit()
            elif mode == "lie_to_stand":
                rc = client.Lie2StandUp()
            elif mode == "squat_to_stand":
                rc = client.Squat2StandUp()
            elif mode == "high_stand":
                rc = client.HighStand()
            elif mode == "low_stand":
                rc = client.LowStand()
            elif mode == "stop_move":
                rc = client.StopMove()
            elif mode == "move":
                vx = float(args[0]) if len(args) > 0 else 0.0
                vy = float(args[1]) if len(args) > 1 else 0.0
                om = float(args[2]) if len(args) > 2 else 0.0
                cont = bool(args[3]) if len(args) > 3 else False
                rc = client.Move(vx, vy, om, cont)
            elif mode == "wave_hand":
                turn_flag = bool(args[0]) if len(args) > 0 else False
                rc = client.WaveHand(turn_flag)
            elif mode == "shake_hand":
                stage = int(args[0]) if len(args) > 0 else -1
                rc = client.ShakeHand(stage)
            else:
                return {"success": False, "message": "unknown mode", "mode": mode, "op": op, "service": service}

            return {"success": rc == 0, "code": rc, "op": op, "mode": mode, "service": service}

        if op == "set_fsm":
            fsm_id = payload.get("fsm_id")
            if fsm_id is None:
                return {"success": False, "message": "fsm_id required", "op": op, "service": service}
            rc = client.SetFsmId(int(fsm_id))
            return {"success": rc == 0, "code": rc, "op": op, "fsm_id": int(fsm_id), "service": service}

        if op == "set_balance_mode":
            balance_mode = payload.get("balance_mode")
            if balance_mode is None:
                return {"success": False, "message": "balance_mode required", "op": op, "service": service}
            rc = client.SetBalanceMode(int(balance_mode))
            return {"success": rc == 0, "code": rc, "op": op, "balance_mode": int(balance_mode), "service": service}

        if op == "set_stand_height":
            stand_height = payload.get("stand_height")
            if stand_height is None:
                return {"success": False, "message": "stand_height required", "op": op, "service": service}
            rc = client.SetStandHeight(float(stand_height))
            return {"success": rc == 0, "code": rc, "op": op, "stand_height": float(stand_height), "service": service}

        if op == "set_task_id":
            task_id = payload.get("task_id")
            if task_id is None:
                return {"success": False, "message": "task_id required", "op": op, "service": service}
            rc = client.SetTaskId(float(task_id))
            return {"success": rc == 0, "code": rc, "op": op, "task_id": float(task_id), "service": service}

        return {"success": False, "message": "unknown op", "op": op, "service": service}

    requested = service_name
    res = do(requested)
    if (not res.get("success")) and int(res.get("code") or 0) == 3102 and requested != "loco":
        # common mismatch: LOCO_SERVICE_NAME should be "loco" on some versions
        res2 = do("loco")
        if res2.get("success") or int(res2.get("code") or 0) != 3102:
            res = res2

    if (not res.get("success")) and int(res.get("code") or 0) == 3102:
        res.setdefault("hint", "Если это G1: возможно нужен другой service_name ('loco' вместо 'sport') или робот/ai_sport не готов к high-level командам.")

    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


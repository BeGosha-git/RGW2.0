from __future__ import annotations

from flask import Blueprint, jsonify, request

import api.robot as robot_api

bp = Blueprint("robot", __name__)


@bp.route("/api/robot/execute", methods=["POST"])
def api_robot_execute():
    data = request.get_json() or {}
    command = data.get("command")
    args = data.get("args", [])
    if not command:
        return jsonify({"success": False, "message": "command required"}), 400
    return jsonify(robot_api.RobotAPI.execute_command(command, args))


@bp.route("/api/robot/commands", methods=["GET"])
def api_robot_commands():
    include_all = str(request.args.get("all", "")).strip() in ("1", "true", "yes", "on")
    return jsonify(robot_api.RobotAPI.get_commands(include_all=include_all))


@bp.route("/api/robot/telemetry", methods=["GET"])
def api_robot_telemetry():
    return jsonify(robot_api.RobotAPI.get_unitree_telemetry()), 200


@bp.route("/api/robot/g1/arm_actions", methods=["GET"])
def api_robot_g1_arm_actions():
    return jsonify(robot_api.RobotAPI.get_g1_arm_actions())


@bp.route("/api/robot/g1/arm_actions/execute", methods=["POST"])
def api_robot_g1_arm_actions_execute():
    data = request.get_json() or {}
    action_name = str(data.get("action", "")).strip()
    if not action_name:
        return jsonify({"success": False, "message": "action required"}), 400
    result = robot_api.RobotAPI.execute_command("g1_arm_action", [action_name])
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/loco/modes", methods=["GET"])
def api_robot_g1_loco_modes():
    return jsonify(robot_api.RobotAPI.get_g1_loco_modes())


@bp.route("/api/robot/g1/loco/execute", methods=["POST"])
def api_robot_g1_loco_execute():
    data = request.get_json() or {}
    mode = str(data.get("mode", "")).strip()
    args = data.get("args", [])
    if not mode:
        return jsonify({"success": False, "message": "mode required"}), 400
    result = robot_api.RobotAPI.execute_command("g1_loco", [mode] + (args if isinstance(args, list) else [args]))
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/loco/set_fsm", methods=["POST"])
def api_robot_g1_loco_set_fsm():
    data = request.get_json() or {}
    fsm_id = data.get("fsm_id", None)
    if fsm_id is None:
        return jsonify({"success": False, "message": "fsm_id required"}), 400
    result = robot_api.RobotAPI.execute_g1_loco_op("set_fsm", {"fsm_id": fsm_id})
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/loco/set_balance_mode", methods=["POST"])
def api_robot_g1_loco_set_balance_mode():
    data = request.get_json() or {}
    balance_mode = data.get("balance_mode", None)
    if balance_mode is None:
        return jsonify({"success": False, "message": "balance_mode required"}), 400
    result = robot_api.RobotAPI.execute_g1_loco_op("set_balance_mode", {"balance_mode": balance_mode})
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/loco/set_stand_height", methods=["POST"])
def api_robot_g1_loco_set_stand_height():
    data = request.get_json() or {}
    stand_height = data.get("stand_height", None)
    if stand_height is None:
        return jsonify({"success": False, "message": "stand_height required"}), 400
    result = robot_api.RobotAPI.execute_g1_loco_op("set_stand_height", {"stand_height": stand_height})
    return jsonify(result), (200 if result.get("success") else 400)


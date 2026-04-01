from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("status", __name__)


@bp.route("/api/status", methods=["GET"])
def api_status():
    try:
        import status

        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({"success": False, "message": f"Error getting status: {str(e)}"}), 500


@bp.route("/status", methods=["GET"])
def status_short():
    try:
        import status

        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({"success": False, "message": f"Error getting status: {str(e)}"}), 500


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "RGW API"})


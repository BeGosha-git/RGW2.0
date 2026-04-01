from __future__ import annotations

import json
from flask import Blueprint, jsonify, request

from api._paths import PROJECT_ROOT

bp = Blueprint("version", __name__)


@bp.route("/api/version/refresh", methods=["POST"])
def api_version_refresh():
    """Refresh local data/version.json file list (no version bump)."""
    try:
        data = request.get_json(silent=True) or {}
        skip = bool(data.get("skip_venv_archive", True))
        import update

        update.update_version_file(skip_venv_archive=skip)
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/version", methods=["GET"])
def api_version_get():
    """Return parsed data/version.json (used by network update)."""
    try:
        version_file = PROJECT_ROOT / "data" / "version.json"
        if not version_file.exists():
            try:
                import update

                update.check_and_update_version()
            except Exception:
                pass
        if not version_file.exists():
            return jsonify({"success": False, "message": "data/version.json not found"}), 404
        raw = version_file.read_text(encoding="utf-8")
        data = json.loads(raw)
        return jsonify({"success": True, "version": data}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, send_file

import api.files as files_api
from api._paths import resolve_under_root, safe_relpath

bp = Blueprint("files", __name__)
files = files_api.FilesAPI()


@bp.route("/api/files/info", methods=["GET"])
def api_files_info():
    """File info endpoint used by updater."""
    filepath = safe_relpath(request.args.get("filepath", ""))
    if not filepath:
        return jsonify({"success": False, "message": "filepath required"}), 400
    fp = resolve_under_root(filepath)
    if fp is None:
        return jsonify({"success": False, "message": "invalid filepath"}), 400
    return jsonify(files.get_file_info(str(fp)))


@bp.route("/api/files/download", methods=["GET", "HEAD"])
def api_files_download():
    """Download a file by relative path (used by updater)."""
    path = safe_relpath(request.args.get("path", ""))
    if not path:
        return jsonify({"success": False, "message": "path required"}), 400
    try:
        fp = resolve_under_root(path)
        if fp is None:
            return jsonify({"success": False, "message": "invalid path"}), 400
        if not fp.exists() or not fp.is_file():
            return jsonify({"success": False, "message": f"File not found: {path}"}), 404
        if request.method == "HEAD":
            resp = Response("", status=200)
            resp.headers["Content-Length"] = str(fp.stat().st_size)
            return resp
        return send_file(str(fp), as_attachment=False)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


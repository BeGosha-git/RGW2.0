from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("cameras", __name__)


@bp.route("/api/cameras/list", methods=["GET"])
def get_cameras_list():
    try:
        from services.camera_stream.camera_stream import get_selected_cameras

        cameras = get_selected_cameras()
        return jsonify({"success": True, "cameras": cameras, "count": len(cameras)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "cameras": []}), 500


@bp.route("/api/cameras/udp", methods=["GET"])
def get_udp_streams():
    try:
        from services.camera_stream.camera_stream import get_selected_cameras, get_camera_stream, start_camera_stream

        cameras = get_selected_cameras()
        udp_streams = []
        for camera_info in cameras:
            camera_id = camera_info.get("id")
            if not camera_id or not camera_id.startswith("usb_"):
                continue
            udp_port = 5005 if camera_id == "usb_2" else 5006
            stream = get_camera_stream(camera_id)
            if not stream and start_camera_stream(camera_id, udp_port=udp_port):
                stream = get_camera_stream(camera_id)
            if stream and stream.running:
                udp_streams.append(
                    {
                        "camera_id": camera_id,
                        "camera_name": camera_info.get("name", camera_id),
                        "udp_port": udp_port,
                        "udp_host": "127.0.0.1",
                    }
                )
        return jsonify({"success": True, "udp_streams": udp_streams, "count": len(udp_streams)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "udp_streams": []}), 500


@bp.route("/api/cameras/<camera_id>/mjpeg", methods=["GET"])
def camera_mjpeg_stream(camera_id):
    try:
        from services.camera_stream.camera_stream import get_selected_cameras, get_camera_stream, start_camera_stream

        selected_ids = [cam.get("id") for cam in get_selected_cameras()]
        if camera_id not in selected_ids:
            return jsonify({"success": False, "message": f"Camera '{camera_id}' not available"}), 404
        stream = get_camera_stream(camera_id)
        if not stream:
            udp_port = 5005 if camera_id == "usb_2" else 5006
            if not start_camera_stream(camera_id, udp_port=udp_port):
                return jsonify({"success": False, "message": f"Camera '{camera_id}' not found or failed to start"}), 404
            stream = get_camera_stream(camera_id)
            if not stream:
                return jsonify({"success": False, "message": "Stream failed to initialize"}), 500

        def generate():
            while True:
                frame = stream.get_latest_frame(quality=60, wait=True)
                if frame:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "Access-Control-Allow-Origin": "*",
                "Cross-Origin-Resource-Policy": "cross-origin",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/cameras/<camera_id>/webrtc/offer", methods=["POST", "OPTIONS"])
def webrtc_offer(camera_id):
    if request.method == "OPTIONS":
        return "", 204
    try:
        from services.camera_stream import webrtc_handler

        data = request.get_json(force=True) or {}
        offer_sdp = data.get("sdp", "")
        offer_type = data.get("type", "offer")
        quality_mode = data.get("quality", "high")
        if not offer_sdp:
            return jsonify({"success": False, "message": "sdp field required"}), 400

        result = webrtc_handler.handle_offer(camera_id, offer_sdp, offer_type, quality_mode=quality_mode)
        if result.get("success"):
            return jsonify(result), 200
        msg = str(result.get("message", "")).lower()
        if "aiortc" in msg or "av" in msg or "not installed" in msg:
            return jsonify(result), 503
        if "sdp" in msg or "not in list" in msg or "invalid" in msg:
            return jsonify(result), 400
        if "not found" in msg or "failed to start" in msg or "unavailable" in msg:
            return jsonify(result), 404
        return jsonify(result), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/cameras/<camera_id>/webrtc/<conn_id>", methods=["DELETE", "OPTIONS"])
def webrtc_close(camera_id, conn_id):
    if request.method == "OPTIONS":
        return "", 204
    try:
        from services.camera_stream import webrtc_handler

        result = webrtc_handler.close_peer(conn_id)
        return jsonify(result), (200 if result.get("success") else 500)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/cameras/webrtc/connections", methods=["GET"])
def webrtc_connections():
    try:
        from services.camera_stream import webrtc_handler

        return jsonify({"success": True, "connections": webrtc_handler.get_active_connections()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


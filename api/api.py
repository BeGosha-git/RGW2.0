"""
RGW camera API.
"""
from flask import Flask, Response, jsonify, request

import api.robot as robot_api

app = Flask(__name__)


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE,OPTIONS")
    return response


@app.route("/api/cameras/list", methods=["GET"])
def get_cameras_list():
    try:
        from services.camera_stream.camera_stream import get_selected_cameras
        cameras = get_selected_cameras()
        return jsonify({"success": True, "cameras": cameras, "count": len(cameras)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "cameras": []}), 500


@app.route("/api/cameras/udp", methods=["GET"])
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
                udp_streams.append({
                    "camera_id": camera_id,
                    "camera_name": camera_info.get("name", camera_id),
                    "udp_port": udp_port,
                    "udp_host": "127.0.0.1",
                })
        return jsonify({"success": True, "udp_streams": udp_streams, "count": len(udp_streams)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "udp_streams": []}), 500


@app.route("/api/cameras/<camera_id>/mjpeg", methods=["GET"])
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
                frame = stream.get_latest_frame(quality=80, wait=True)
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


@app.route("/api/cameras/<camera_id>/webrtc/offer", methods=["POST", "OPTIONS"])
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


@app.route("/api/cameras/<camera_id>/webrtc/<conn_id>", methods=["DELETE", "OPTIONS"])
def webrtc_close(camera_id, conn_id):
    if request.method == "OPTIONS":
        return "", 204
    try:
        from services.camera_stream import webrtc_handler
        result = webrtc_handler.close_peer(conn_id)
        return jsonify(result), (200 if result.get("success") else 500)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/cameras/webrtc/connections", methods=["GET"])
def webrtc_connections():
    try:
        from services.camera_stream import webrtc_handler
        return jsonify({"success": True, "connections": webrtc_handler.get_active_connections()})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        import status
        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({"success": False, "message": f"Error getting status: {str(e)}"}), 500


@app.route("/api/robot/execute", methods=["POST"])
def api_robot_execute():
    """Выполняет команду на роботе."""
    data = request.get_json() or {}
    command = data.get("command")
    args = data.get("args", [])
    if not command:
        return jsonify({"success": False, "message": "command required"}), 400
    return jsonify(robot_api.RobotAPI.execute_command(command, args))


@app.route("/api/robot/commands", methods=["GET"])
def api_robot_commands():
    """Возвращает команды из commands.json с фильтрацией по RobotType."""
    return jsonify(robot_api.RobotAPI.get_commands())


@app.route("/api/robot/g1/arm_actions", methods=["GET"])
def api_robot_g1_arm_actions():
    """Возвращает список доступных arm-actions для G1."""
    return jsonify(robot_api.RobotAPI.get_g1_arm_actions())


@app.route("/api/robot/g1/arm_actions/execute", methods=["POST"])
def api_robot_g1_arm_actions_execute():
    """Выполняет arm-action для G1."""
    data = request.get_json() or {}
    action_name = str(data.get("action", "")).strip()
    if not action_name:
        return jsonify({"success": False, "message": "action required"}), 400
    result = robot_api.RobotAPI.execute_g1_arm_action(action_name)
    return jsonify(result), (200 if result.get("success") else 400)


@app.route("/status", methods=["GET"])
def status_short():
    try:
        import status
        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({"success": False, "message": f"Error getting status: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "RGW API"})


def run_api(host="0.0.0.0", port=5000, debug=False):
    app.run(host=host, port=port, debug=debug, threaded=True)


def run():
    import services_manager
    try:
        manager = services_manager.get_services_manager()
        port = manager.get_service_parameters("api").get("port", 5000)
    except Exception:
        port = 5000
    print(f"Starting API service on port {port}...", flush=True)
    run_api(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run()

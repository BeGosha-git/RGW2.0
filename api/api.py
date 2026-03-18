"""
Минимальный API для UDP стримов камер (только usb_2 и usb_3).
"""
from flask import Flask, request, jsonify

app = Flask(__name__)


@app.after_request
def after_request(response):
    """Добавляет CORS заголовки ко всем ответам."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/api/cameras/list', methods=['GET'])
def get_cameras_list():
    """Возвращает список выбранных камер: usb_2 и еще одну из usb_1, usb_3, usb_4, usb_5."""
    try:
        from services.camera_stream.camera_stream import get_selected_cameras
        
        cameras = get_selected_cameras()
        
        return jsonify({
            "success": True,
            "cameras": cameras,
            "count": len(cameras)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "cameras": []}), 500


@app.route('/api/cameras/udp', methods=['GET'])
def get_udp_streams():
    """Возвращает информацию о UDP стримах для выбранных камер. Автоматически запускает камеры."""
    try:
        from services.camera_stream.camera_stream import (
            get_selected_cameras,
            get_camera_stream, start_camera_stream
        )
        
        # Получаем выбранные камеры (usb_2 + одна из 1,3,4,5)
        cameras = get_selected_cameras()
        
        udp_streams = []
        udp_ports = {5005: False, 5006: False}  # Порты для камер
        
        for camera_info in cameras:
            camera_id = camera_info.get("id")
            if not camera_id or not camera_id.startswith("usb_"):
                continue
            
            # Определяем UDP порт (usb_2 -> 5005, остальные -> 5006)
            if camera_id == "usb_2":
                udp_port = 5005
            else:
                # Используем 5006 для второй камеры
                udp_port = 5006
            
            # Запускаем стрим если не запущен
            stream = get_camera_stream(camera_id)
            if not stream:
                if start_camera_stream(camera_id, udp_port=udp_port):
                    stream = get_camera_stream(camera_id)
            
            if stream and stream.running:
                udp_streams.append({
                    "camera_id": camera_id,
                    "camera_name": camera_info.get("name", camera_id),
                    "udp_port": udp_port,
                    "udp_host": "127.0.0.1"
                })
        
        return jsonify({
            "success": True,
            "udp_streams": udp_streams,
            "count": len(udp_streams)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "udp_streams": []}), 500


@app.route('/api/cameras/<camera_id>/mjpeg', methods=['GET'])
def camera_mjpeg_stream(camera_id):
    """MJPEG поток с камеры (для выбранных камер: usb_2 и еще одной из usb_1, usb_3, usb_4, usb_5)."""
    try:
        from services.camera_stream.camera_stream import get_selected_cameras
        
        # Проверяем, что камера в списке выбранных
        selected_cameras = get_selected_cameras()
        camera_ids = [cam.get("id") for cam in selected_cameras]
        
        if camera_id not in camera_ids:
            return jsonify({"success": False, "message": f"Camera '{camera_id}' not available"}), 404
    except Exception:
        # Если не удалось получить список, разрешаем только usb_2 для совместимости
        if camera_id != "usb_2":
            return jsonify({"success": False, "message": f"Camera '{camera_id}' not available"}), 404
    
    from flask import Response
    from services.camera_stream.camera_stream import get_camera_stream, start_camera_stream
    
    # Запускаем поток если ещё не запущен
    stream = get_camera_stream(camera_id)
    if not stream:
        # Определяем UDP порт (usb_2 -> 5005, остальные -> 5006)
        udp_port = 5005 if camera_id == "usb_2" else 5006
        if not start_camera_stream(camera_id, udp_port=udp_port):
            return jsonify({
                "success": False,
                "message": f"Camera '{camera_id}' not found or failed to start"
            }), 404
        stream = get_camera_stream(camera_id)
        if not stream:
            return jsonify({"success": False, "message": "Stream failed to initialize"}), 500

    def generate():
        no_frame_count = 0
        max_no_frame = 30
        try:
            while True:
                frame = stream.get_latest_frame(quality=80, wait=True)
                if frame:
                    no_frame_count = 0
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    no_frame_count += 1
                    if no_frame_count >= max_no_frame:
                        print(f"[API] MJPEG stream: no frames for {max_no_frame} iterations, closing connection", flush=True)
                        break
        except GeneratorExit:
            pass
        except Exception as e:
            print(f"[API] MJPEG generator error: {e}", flush=True)

    return Response(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Access-Control-Allow-Origin': '*',
            'Cross-Origin-Resource-Policy': 'cross-origin',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


@app.route('/api/status', methods=['GET'])
def api_status():
    """Возвращает статус робота."""
    try:
        import status
        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error getting status: {str(e)}"
        }), 500


@app.route('/status', methods=['GET'])
def status_short():
    """Короткий путь для /status (используется в network_api)."""
    try:
        import status
        return jsonify(status.get_robot_status())
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error getting status: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья API."""
    return jsonify({"status": "ok", "service": "RGW API"})


def run_api(host='0.0.0.0', port=5000, debug=False):
    """Запускает API сервер."""
    app.run(host=host, port=port, debug=debug, threaded=True)


def check_port_available(check_port):
    """Проверяет, свободен ли порт."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex(('127.0.0.1', check_port))
        sock.close()
        return result != 0
    except Exception:
        sock.close()
        return False


def run():
    """Функция для запуска API как сервиса из run.py."""
    import services_manager
    import subprocess
    import time
    
    try:
        manager = services_manager.get_services_manager()
        params = manager.get_service_parameters("api")
        port = params.get("port", 5000)
    except Exception:
        port = 5000
    
    # Проверяем, свободен ли порт
    if not check_port_available(port):
        print(f"Port {port} is in use by another program. Trying to free it...", flush=True)
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], 
                          capture_output=True, timeout=2, stderr=subprocess.DEVNULL)
            time.sleep(1)
        except Exception:
            pass
        
        if not check_port_available(port):
            print(f"Port {port} is still in use. Trying alternative ports...", flush=True)
            # Порты 5005 и 5006 зарезервированы для UDP-стримов камер, не используем их
            for try_port in [5000, 5001, 5002, 5003, 5004, 5007, 5008]:
                if try_port != port and check_port_available(try_port):
                    port = try_port
                    print(f"Port {try_port} is available. Using it instead...", flush=True)
                    break
            else:
                print(f"Error: All fallback API ports are in use.", flush=True)
                return
    
    print(f"Starting API service on port {port}...", flush=True)
    import sys
    sys.stdout.flush()
    try:
        run_api(host='0.0.0.0', port=port, debug=False)
    except OSError as e:
        error_msg = str(e)
        if "Address already in use" in error_msg:
            print(f"Port {port} is in use by another program.", flush=True)
        else:
            print(f"Error starting API server: {error_msg}", flush=True)


if __name__ == '__main__':
    run()

"""
Централизованный API для работы с системой.
Объединяет все API модули.
"""
from flask import Flask, request, jsonify
from typing import Dict, Any
import time
import api.files as files_api
import api.robot as robot_api
import api.network_api as network_api_module

app = Flask(__name__)

# Инициализация API модулей
files = files_api.FilesAPI()
robot = robot_api.RobotAPI()
network_api = network_api_module.NetworkAPI()


@app.after_request
def after_request(response):
    """Добавляет CORS заголовки ко всем ответам."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/api/status', methods=['GET'])
def status():
    """Возвращает статус робота."""
    return jsonify(robot.get_robot_status())


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Получает настройки робота."""
    return jsonify(robot.get_settings())


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Обновляет настройки робота."""
    data = request.get_json() or {}
    return jsonify(robot.update_settings(data))


@app.route('/api/version', methods=['GET'])
def get_version():
    """Получает версию робота."""
    return jsonify(robot.get_version())


@app.route('/api/version/refresh', methods=['POST'])
def refresh_version_file():
    """Обновляет version.json по текущим файлам (актуализирует список и размеры). Вызывается перед сравнением версий. Body: {"skip_venv_archive": true} — без пересборки venv (быстро)."""
    try:
        import update
        data = request.get_json(silent=True) or {}
        skip_venv = data.get("skip_venv_archive", False)
        ok = update.update_version_file(skip_venv_archive=bool(skip_venv))
        return jsonify({"success": bool(ok), "message": "version.json updated" if ok else "update_version_file failed"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/get_actual_version', methods=['GET'])
def get_actual_version():
    """Получает самую актуальную версию от других роботов."""
    robot_ips = request.args.getlist('robot_ips')
    return jsonify(network_api.get_actual_version(robot_ips if robot_ips else None))


@app.route('/api/files/create', methods=['POST'])
def create_file():
    """Создает файл."""
    data = request.get_json() or {}
    filepath = data.get('filepath')
    content = data.get('content', '')
    return jsonify(files.create_file(filepath, content))


@app.route('/api/files/delete', methods=['POST'])
def delete_file():
    """Удаляет файл."""
    data = request.get_json() or {}
    filepath = data.get('filepath')
    return jsonify(files.delete_file(filepath))


@app.route('/api/files/read', methods=['GET'])
def read_file():
    """Читает файл."""
    filepath = request.args.get('filepath')
    return jsonify(files.read_file(filepath))


@app.route('/api/files/write', methods=['POST'])
def write_file():
    """Записывает в файл."""
    data = request.get_json() or {}
    filepath = data.get('filepath')
    content = data.get('content', '')
    return jsonify(files.write_file(filepath, content))


@app.route('/api/files/info', methods=['GET'])
def get_file_info():
    """Получает информацию о файле."""
    filepath = request.args.get('filepath')
    return jsonify(files.get_file_info(filepath))


@app.route('/api/files/list', methods=['GET'])
def list_directory():
    """Списывает содержимое директории."""
    dirpath = request.args.get('dirpath', '.')
    return jsonify(files.list_directory(dirpath))


@app.route('/api/files/download', methods=['GET'])
def download_file():
    """Скачивает файл. path — относительно корня проекта (RGW2.0)."""
    from flask import send_file
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    filepath = request.args.get('path')
    if not filepath:
        return jsonify({"success": False, "message": "path parameter required"}), 400

    try:
        # Путь всегда относительно корня проекта, не от cwd
        abs_path = (PROJECT_ROOT / filepath).resolve()
        # Запрет path traversal: файл должен быть внутри PROJECT_ROOT
        if not str(abs_path).startswith(str(PROJECT_ROOT.resolve())):
            return jsonify({"success": False, "message": "Access denied"}), 403
        # venv-{version}.tar.gz: создаём архив если нет, обновляем если venv обновился
        if filepath.strip().startswith("venv-") and filepath.strip().endswith(".tar.gz"):
            try:
                import update
                # Извлекаем версию из имени файла (venv-3.11.tar.gz -> 3.11)
                version = filepath.strip().replace("venv-", "").replace(".tar.gz", "")
                if version in ["3.8", "3.11", "3.13"]:
                    update.ensure_venv_archive(PROJECT_ROOT, version)
            except Exception:
                pass
            abs_path = (PROJECT_ROOT / filepath).resolve()
        if abs_path.exists() and abs_path.is_file():
            return send_file(str(abs_path), as_attachment=True, download_name=abs_path.name)
        return jsonify({"success": False, "message": f"File not found: {filepath}"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": f"Error accessing file {filepath}: {str(e)}"}), 500


@app.route('/api/directory/create', methods=['POST'])
def create_directory():
    """Создает директорию."""
    data = request.get_json() or {}
    dirpath = data.get('dirpath')
    return jsonify(files.create_directory(dirpath))


@app.route('/api/directory/delete', methods=['POST'])
def delete_directory():
    """Удаляет директорию."""
    data = request.get_json() or {}
    dirpath = data.get('dirpath')
    return jsonify(files.delete_directory(dirpath))


@app.route('/api/files/rename', methods=['POST'])
def rename_file():
    """Переименовывает файл или директорию."""
    data = request.get_json() or {}
    old_path = data.get('old_path')
    new_path = data.get('new_path')
    return jsonify(files.rename_file(old_path, new_path))


@app.route('/api/robot/execute', methods=['POST'])
def execute_command():
    """Выполняет команду на роботе."""
    data = request.get_json() or {}
    command = data.get('command')
    args = data.get('args', [])
    return jsonify(robot.execute_command(command, args))


@app.route('/api/network/send', methods=['POST'])
def send_data():
    """Отправляет данные другому роботу."""
    data = request.get_json() or {}
    target_ip = data.get('target_ip')
    endpoint = data.get('endpoint')
    payload = data.get('data', {})
    return jsonify(network_api.send_data(target_ip, endpoint, payload))


@app.route('/api/network/receive', methods=['GET'])
def receive_data():
    """Получает данные от другого робота."""
    source_ip = request.args.get('source_ip')
    endpoint = request.args.get('endpoint')
    return jsonify(network_api.receive_data(source_ip, endpoint))


@app.route('/api/network/find_robots', methods=['GET'])
def find_robots():
    """Ищет роботов в сети."""
    return jsonify(network_api.find_robots())


@app.route('/api/network/scanned_ips', methods=['GET'])
def get_scanned_ips():
    """Возвращает сохраненные IP адреса из последнего сканирования."""
    try:
        import json
        from pathlib import Path
        
        ips_file = Path("data/ips.json")
        
        if not ips_file.exists():
            return jsonify({
                "success": True,
                "last_scan": None,
                "scan_count": 0,
                "ips": [],
                "history": []
            })
        
        with open(ips_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return jsonify({
            "success": True,
            **data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error reading scanned IPs: {str(e)}"
        })


@app.route('/api/network/download_file', methods=['POST'])
def download_file_from_robot():
    """Скачивает файл с другого робота."""
    data = request.get_json() or {}
    source_ip = data.get('source_ip')
    filepath = data.get('filepath')
    local_path = data.get('local_path')
    return jsonify(network_api.download_file_from_robot(source_ip, filepath, local_path))


@app.route('/api/cameras/list', methods=['GET'])
def list_cameras():
    """Возвращает список доступных камер."""
    try:
        from services.camera_stream.camera_stream import detect_cameras
        cameras = detect_cameras()
        return jsonify({"success": True, "cameras": cameras, "count": len(cameras)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "cameras": []}), 500


@app.route('/api/cameras/<camera_id>/mjpeg', methods=['GET'])
def camera_mjpeg_stream(camera_id):
    """
    MJPEG поток с камеры.
    URL: /api/cameras/<camera_id>/mjpeg[?width=W&height=H&quality=Q]
    Примеры:
      /api/cameras/realsense_0/mjpeg
      /api/cameras/usb_0/mjpeg?width=640&height=480&quality=75
    """
    from flask import Response
    from services.camera_stream.camera_stream import get_camera_stream, start_camera_stream

    width   = request.args.get('width',   type=int)
    height  = request.args.get('height',  type=int)
    quality = request.args.get('quality', type=int, default=80)

    # Запускаем поток если ещё не запущен
    stream = get_camera_stream(camera_id)
    if not stream:
        if not start_camera_stream(camera_id, width=width, height=height):
            return jsonify({
                "success": False,
                "message": f"Camera '{camera_id}' not found or failed to start"
            }), 404
        stream = get_camera_stream(camera_id)
        if not stream:
            return jsonify({"success": False, "message": "Stream failed to initialize"}), 500

    def generate():
        try:
            while True:
                frame = stream.get_latest_frame(width=width, height=height,
                                                quality=quality, wait=True)
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        except GeneratorExit:
            pass
        except Exception:
            pass

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


@app.route('/api/cameras/<camera_id>/start', methods=['POST'])
def start_camera(camera_id):
    """Запускает поток с камеры."""
    try:
        from services.camera_stream.camera_stream import start_camera_stream
        data = request.get_json(silent=True) or {}
        udp_port = data.get('udp_port')
        if start_camera_stream(camera_id, udp_port=udp_port):
            return jsonify({"success": True, "message": f"Camera {camera_id} started"})
        return jsonify({"success": False, "message": f"Camera '{camera_id}' not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/cameras/<camera_id>/stop', methods=['POST'])
def stop_camera(camera_id):
    """Останавливает поток с камеры."""
    try:
        from services.camera_stream.camera_stream import stop_camera_stream
        if stop_camera_stream(camera_id):
            return jsonify({"success": True, "message": f"Camera {camera_id} stopped"})
        return jsonify({"success": False, "message": f"Camera '{camera_id}' not running"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/cameras/streams', methods=['GET'])
def get_active_streams():
    """Возвращает активные потоки с UDP портами."""
    try:
        from services.camera_stream.camera_stream import get_all_streams
        streams = get_all_streams()
        return jsonify({"success": True, "streams": streams, "count": len(streams)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "streams": {}}), 500


@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья API."""
    return jsonify({"status": "ok", "service": "RGW API"})


def run_api(host='0.0.0.0', port=5000, debug=False):
    """
    Запускает API сервер.
    
    Args:
        host: Хост для прослушивания
        port: Порт для прослушивания
        debug: Режим отладки
    """
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
    except:
        sock.close()
        return False


def run():
    """
    Функция для запуска API как сервиса из run.py.
    Запускает API сервер на порту из конфигурации (по умолчанию 5000).
    """
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
            # Пробуем освободить порт
            subprocess.run(["fuser", "-k", f"{port}/tcp"], 
                         capture_output=True, timeout=2, stderr=subprocess.DEVNULL)
            time.sleep(1)
        except Exception:
            pass
        
        # Если порт все еще занят, пробуем альтернативные порты
        if not check_port_available(port):
            print(f"Port {port} is still in use. Trying alternative ports...", flush=True)
            for try_port in [5000, 5001, 5002, 5003, 5004, 5005]:
                if try_port != port and check_port_available(try_port):
                    port = try_port
                    print(f"Port {try_port} is available. Using it instead...", flush=True)
                    break
            else:
                print(f"Error: All ports 5000-5005 are in use. Please free a port or kill existing API server.", flush=True)
                return
    
    print(f"Starting API service on port {port}...", flush=True)
    import sys
    sys.stdout.flush()
    try:
        run_api(host='0.0.0.0', port=port, debug=False)
    except OSError as e:
        error_msg = str(e)
        if "Address already in use" in error_msg:
            print(f"Address already in use", flush=True)
            print(f"Port {port} is in use by another program. Either identify and stop that program, or start the server with a different port.", flush=True)
        else:
            print(f"Error starting API server: {error_msg}", flush=True)


if __name__ == '__main__':
    run()
"""
Централизованный API для работы с системой.
Объединяет все API модули.
"""
from flask import Flask, request, jsonify
from typing import Dict, Any
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
    """Скачивает файл."""
    from flask import send_file
    import os
    
    filepath = request.args.get('path')
    if filepath and os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return jsonify({"success": False, "message": "File not found"}), 404


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


def run():
    """
    Функция для запуска API как сервиса из run.py.
    Запускает API сервер в фоне на порту 5000.
    """
    print("Starting API service on port 5000...", flush=True)
    import sys
    sys.stdout.flush()
    run_api(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    run()
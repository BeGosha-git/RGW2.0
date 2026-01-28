"""
Веб-сервис для запуска статического сайта из папки build на порту 80.
Интегрирует Flask API для обработки API запросов напрямую.
"""
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь для импорта модулей
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import http.server
import socketserver
import json
from flask import Flask, request, jsonify
import api.files as files_api
import api.robot as robot_api
import api.network_api as network_api_module
import services_manager

# ============================================================================
# ИНИЦИАЛИЗАЦИЯ FLASK ПРИЛОЖЕНИЯ
# ============================================================================

flask_app = Flask(__name__)

# Инициализация API модулей
files = files_api.FilesAPI()
robot = robot_api.RobotAPI()
network_api = network_api_module.NetworkAPI()

# ============================================================================
# CORS НАСТРОЙКИ
# ============================================================================

@flask_app.after_request
def after_request(response):
    """Добавляет CORS заголовки ко всем ответам."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ============================================================================
# РЕГИСТРАЦИЯ API ENDPOINTS
# ============================================================================

def register_status_endpoints():
    """Регистрирует endpoints для статуса системы."""
    
    @flask_app.route('/api/status', methods=['GET'])
    def api_status():
        """Возвращает статус робота."""
        import status
        return jsonify(status.get_robot_status())
    
    @flask_app.route('/health', methods=['GET'])
    def api_health():
        """Проверка здоровья API."""
        return jsonify({"status": "ok", "service": "RGW API"})


def register_files_endpoints():
    """Регистрирует endpoints для работы с файлами."""
    
    @flask_app.route('/api/files/list', methods=['GET'])
    def api_files_list():
        """Список файлов в директории."""
        dirpath = request.args.get('dirpath', '.')
        return jsonify(files.list_directory(dirpath))
    
    @flask_app.route('/api/files/read', methods=['GET'])
    def api_files_read():
        """Читает файл."""
        filepath = request.args.get('filepath')
        if not filepath:
            return jsonify({"success": False, "message": "filepath parameter required"}), 400
        return jsonify(files.read_file(filepath))
    
    @flask_app.route('/api/files/write', methods=['POST'])
    def api_files_write():
        """Записывает файл."""
        data = request.get_json() or {}
        filepath = data.get('filepath')
        content = data.get('content', '')
        if not filepath:
            return jsonify({"success": False, "message": "filepath required"}), 400
        return jsonify(files.write_file(filepath, content))
    
    @flask_app.route('/api/files/create', methods=['POST'])
    def api_files_create():
        """Создает файл."""
        data = request.get_json() or {}
        filepath = data.get('filepath')
        content = data.get('content', '')
        if not filepath:
            return jsonify({"success": False, "message": "filepath required"}), 400
        return jsonify(files.create_file(filepath, content))
    
    @flask_app.route('/api/files/delete', methods=['POST'])
    def api_files_delete():
        """Удаляет файл."""
        data = request.get_json() or {}
        filepath = data.get('filepath')
        if not filepath:
            return jsonify({"success": False, "message": "filepath required"}), 400
        return jsonify(files.delete_file(filepath))
    
    @flask_app.route('/api/files/rename', methods=['POST'])
    def api_files_rename():
        """Переименовывает файл или директорию."""
        data = request.get_json() or {}
        old_path = data.get('old_path')
        new_path = data.get('new_path')
        if not old_path or not new_path:
            return jsonify({"success": False, "message": "old_path and new_path required"}), 400
        return jsonify(files.rename_file(old_path, new_path))
    
    @flask_app.route('/api/files/info', methods=['GET'])
    def api_files_info():
        """Информация о файле."""
        filepath = request.args.get('filepath')
        if not filepath:
            return jsonify({"success": False, "message": "filepath parameter required"}), 400
        return jsonify(files.get_file_info(filepath))


def register_directory_endpoints():
    """Регистрирует endpoints для работы с директориями."""
    
    @flask_app.route('/api/directory/create', methods=['POST'])
    def api_directory_create():
        """Создает директорию."""
        data = request.get_json() or {}
        dirpath = data.get('dirpath')
        if not dirpath:
            return jsonify({"success": False, "message": "dirpath required"}), 400
        return jsonify(files.create_directory(dirpath))
    
    @flask_app.route('/api/directory/delete', methods=['POST'])
    def api_directory_delete():
        """Удаляет директорию."""
        data = request.get_json() or {}
        dirpath = data.get('dirpath')
        if not dirpath:
            return jsonify({"success": False, "message": "dirpath required"}), 400
        return jsonify(files.delete_directory(dirpath))


def register_network_endpoints():
    """Регистрирует endpoints для сетевого взаимодействия."""
    
    @flask_app.route('/api/network/find_robots', methods=['GET'])
    def api_find_robots():
        """Ищет роботов в сети."""
        return jsonify(network_api.find_robots())
    
    @flask_app.route('/api/network/scanned_ips', methods=['GET'])
    def api_scanned_ips():
        """Возвращает сохраненные IP адреса из последнего сканирования."""
        try:
            ips_file = Path("data/ips.json")
            if not ips_file.exists():
                return jsonify({
                    "success": True,
                    "last_scan": None,
                    "scan_count": 0,
                    "ips": []
                })
            with open(ips_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify({"success": True, **data})
        except Exception as e:
            return jsonify({
                "success": False,
                "message": f"Error reading scanned IPs: {str(e)}"
            }), 500
    
    @flask_app.route('/api/network/send', methods=['POST'])
    def api_network_send():
        """Отправляет данные другому роботу."""
        data = request.get_json() or {}
        target_ip = data.get('target_ip')
        endpoint = data.get('endpoint')
        payload = data.get('data', {})
        if not target_ip or not endpoint:
            return jsonify({"success": False, "message": "target_ip and endpoint required"}), 400
        return jsonify(network_api.send_data(target_ip, endpoint, payload))


def register_robot_endpoints():
    """Регистрирует endpoints для управления роботом."""
    
    @flask_app.route('/api/robot/execute', methods=['POST'])
    def api_robot_execute():
        """Выполняет команду на роботе."""
        data = request.get_json() or {}
        command = data.get('command')
        args = data.get('args', [])
        if not command:
            return jsonify({"success": False, "message": "command required"}), 400
        return jsonify(robot_api.RobotAPI.execute_command(command, args))
    
    @flask_app.route('/api/robot/commands', methods=['GET'])
    def api_robot_commands():
        """Получает список быстрых команд из commands.json."""
        return jsonify(robot_api.RobotAPI.get_commands())
    
    @flask_app.route('/api/robot/commands', methods=['PUT', 'POST'])
    def api_robot_commands_update():
        """Обновляет список быстрых команд в commands.json."""
        data = request.get_json() or {}
        return jsonify(robot_api.RobotAPI.update_commands(data))
    
    @flask_app.route('/api/settings', methods=['POST'])
    def api_settings():
        """Обновляет настройки робота (локально)."""
        data = request.get_json() or {}
        return jsonify(robot_api.RobotAPI.update_settings(data))
    
    @flask_app.route('/api/robot/update_group', methods=['POST'])
    def api_robot_update_group():
        """Обновляет группу робота через сеть."""
        data = request.get_json() or {}
        target_ip = data.get('target_ip')
        robot_group = data.get('robot_group', '')
        
        if not target_ip:
            return jsonify({"success": False, "message": "target_ip required"}), 400
        
        # Отправляем запрос на обновление settings.json на удаленном роботе
        try:
            # Формируем данные для отправки - всегда отправляем RobotGroup, даже если пустая строка
            settings_data = {"RobotGroup": robot_group}
            
            print(f"[update_group] Sending to {target_ip}: {settings_data}")
            result = network_api.send_data(
                target_ip,
                '/api/settings',
                settings_data
            )
            
            print(f"[update_group] Result from {target_ip}: {result}")
            
            # Проверяем структуру ответа
            # network_api.send_data возвращает: {"success": True, "response": {...}}
            # где response - это ответ от удаленного робота
            if result.get('success'):
                remote_response = result.get('response')
                if remote_response:
                    # remote_response - это уже распарсенный JSON ответ от удаленного робота
                    if isinstance(remote_response, dict):
                        if remote_response.get('success'):
                            # Успешно обновлено на удаленном роботе
                            return jsonify({
                                "success": True,
                                "message": "Group updated successfully",
                                "settings": remote_response.get('settings', {})
                            })
                        else:
                            # Ошибка на удаленном роботе
                            return jsonify({
                                "success": False,
                                "message": remote_response.get('message', 'Unknown error')
                            })
                    else:
                        # Неожиданный формат ответа
                        return jsonify({
                            "success": False,
                            "message": f"Unexpected response format: {type(remote_response)}"
                        })
                else:
                    # Нет ответа от удаленного робота
                    return jsonify({
                        "success": False,
                        "message": "No response from remote robot"
                    })
            else:
                # Ошибка при отправке запроса
                return jsonify(result)
        except Exception as e:
            print(f"[update_group] Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"success": False, "message": str(e)}), 500


def register_services_endpoints():
    """Регистрирует endpoints для управления сервисами."""
    
    @flask_app.route('/api/services', methods=['GET'])
    def api_services_list():
        """Получает список всех сервисов."""
        try:
            manager = services_manager.get_services_manager()
            manager.refresh_services()  # Обновляем список
            services = manager.get_all_services()
            return jsonify({
                "success": True,
                "services": services
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    
    @flask_app.route('/api/services/<service_name>', methods=['GET'])
    def api_service_get(service_name):
        """Получает информацию о сервисе."""
        try:
            manager = services_manager.get_services_manager()
            service = manager.get_service(service_name)
            params = manager.get_service_parameters(service_name)
            dependencies = manager.get_service_dependencies(service_name)
            depending_services = manager.get_services_depending_on(service_name)
            return jsonify({
                "success": True,
                "service": service,
                "parameters": params,
                "dependencies": dependencies,
                "depending_services": depending_services
            })
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    
    @flask_app.route('/api/services/<service_name>/status', methods=['POST'])
    def api_service_status(service_name):
        """Обновляет статус сервиса."""
        try:
            data = request.get_json() or {}
            status = data.get('status')
            disable_dependents = data.get('disable_dependents', False)
            
            if status not in ['ON', 'OFF', 'SLEEP']:
                return jsonify({
                    "success": False,
                    "message": "Invalid status. Must be ON, OFF, or SLEEP"
                }), 400
            
            manager = services_manager.get_services_manager()
            
            # Если выключаем сервис, проверяем зависимости
            if status == 'OFF':
                can_disable, depending_services = manager.can_disable_service(service_name)
                if not can_disable and not disable_dependents:
                    return jsonify({
                        "success": False,
                        "message": "Cannot disable service",
                        "depending_services": depending_services,
                        "requires_confirmation": True
                    }), 400
                
                # Если пользователь согласен, выключаем зависимые сервисы
                if disable_dependents and depending_services:
                    for dep_service in depending_services:
                        manager.update_service_status(dep_service, 'OFF')
            
            success = manager.update_service_status(service_name, status)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Status updated to {status}"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Failed to update status"
                }), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    
    @flask_app.route('/api/services/<service_name>/parameter', methods=['POST'])
    def api_service_parameter(service_name):
        """Обновляет параметр сервиса."""
        try:
            data = request.get_json() or {}
            parameter = data.get('parameter')
            value = data.get('value')
            
            if not parameter:
                return jsonify({
                    "success": False,
                    "message": "Parameter name required"
                }), 400
            
            manager = services_manager.get_services_manager()
            success = manager.update_service_parameter(service_name, parameter, value)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Parameter {parameter} updated"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Failed to update parameter"
                }), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    
    @flask_app.route('/api/services/<service_name>/parameter/<parameter>', methods=['DELETE'])
    def api_service_parameter_reset(service_name, parameter):
        """Сбрасывает параметр сервиса к дефолтному значению."""
        try:
            manager = services_manager.get_services_manager()
            success = manager.reset_service_parameter(service_name, parameter)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Parameter {parameter} reset to default"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Failed to reset parameter"
                }), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500


# Регистрация всех endpoints
register_status_endpoints()
register_files_endpoints()
register_directory_endpoints()
register_network_endpoints()
register_robot_endpoints()
register_services_endpoints()

# ============================================================================
# HTTP REQUEST HANDLER
# ============================================================================

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Кастомный обработчик HTTP запросов с поддержкой SPA и встроенного API."""
    
    def __init__(self, *args, **kwargs):
        self.flask_app = kwargs.pop('flask_app', None)
        super().__init__(*args, directory=kwargs.pop('directory', None), **kwargs)
    
    def end_headers(self):
        """Добавляет заголовки CORS если нужно."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        super().end_headers()
    
    def do_OPTIONS(self):
        """Обрабатывает OPTIONS запросы для CORS."""
        self.send_response(200)
        self.end_headers()
    
    def handle_api_request(self, method='GET'):
        """Обрабатывает API запрос напрямую через Flask."""
        try:
            # Читаем тело запроса
            body = None
            if method in ['POST', 'PUT', 'DELETE']:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)
            
            # Используем werkzeug.test.Client для обработки запроса
            from werkzeug.test import Client
            from werkzeug.wrappers import Response
            
            client = Client(self.flask_app, Response)
            
            # Извлекаем path и query string
            path_for_request = self.path
            query_string = None
            if '?' in self.path:
                path_for_request, query_string = self.path.split('?', 1)
            
            # Выполняем запрос в зависимости от метода
            if method == 'GET':
                response = client.get(path_for_request, query_string=query_string) if query_string else client.get(path_for_request)
            elif method == 'POST':
                content_type = self.headers.get('Content-Type', '')
                if body and 'application/json' in content_type:
                    try:
                        json_data = json.loads(body.decode('utf-8'))
                        response = client.post(path_for_request, json=json_data, query_string=query_string, content_type='application/json')
                    except Exception:
                        response = client.post(path_for_request, data=body, query_string=query_string, content_type='application/json')
                else:
                    response = client.post(path_for_request, data=body, query_string=query_string, content_type=content_type)
            elif method == 'PUT':
                content_type = self.headers.get('Content-Type', '')
                if body and 'application/json' in content_type:
                    try:
                        json_data = json.loads(body.decode('utf-8'))
                        response = client.put(path_for_request, json=json_data, query_string=query_string, content_type='application/json')
                    except Exception:
                        response = client.put(path_for_request, data=body, query_string=query_string, content_type='application/json')
                else:
                    response = client.put(path_for_request, data=body, query_string=query_string, content_type=content_type)
            elif method == 'DELETE':
                response = client.delete(path_for_request, query_string=query_string) if query_string else client.delete(path_for_request)
            else:
                response = client.open(path_for_request, method=method, data=body if body else None)
            
            # Отправляем ответ
            self.send_response(response.status_code)
            
            # Копируем заголовки
            for header, value in response.headers.items():
                self.send_header(header, value)
            
            self.end_headers()
            
            # Отправляем тело ответа
            if response.data:
                try:
                    self.wfile.write(response.data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    # Клиент закрыл соединение - это нормально
                    pass
                    
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Клиент закрыл соединение до получения ответа - это нормально
            pass
        except Exception as e:
            error_msg = f"API error: {str(e)}"
            print(f"[WEB ERROR] {error_msg}", flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stderr.flush()
            try:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                error_response = json.dumps({
                    "success": False, 
                    "message": str(e)
                }).encode()
                self.wfile.write(error_response)
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Клиент уже закрыл соединение
                pass
    
    def do_GET(self):
        """Обрабатывает GET запросы."""
        if self.path.startswith('/api') or self.path == '/health':
            self.handle_api_request('GET')
            return
        
        # Если файл не найден, возвращаем index.html (для SPA)
        if not os.path.exists(self.translate_path(self.path)):
            self.path = '/index.html'
        return super().do_GET()
    
    def do_POST(self):
        """Обрабатывает POST запросы."""
        if self.path.startswith('/api'):
            self.handle_api_request('POST')
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_PUT(self):
        """Обрабатывает PUT запросы."""
        if self.path.startswith('/api'):
            self.handle_api_request('PUT')
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_DELETE(self):
        """Обрабатывает DELETE запросы."""
        if self.path.startswith('/api'):
            self.handle_api_request('DELETE')
            return
        
        self.send_response(404)
        self.end_headers()
    
    def log_message(self, format, *args):
        """Логирует запросы."""
        if args:
            print(f"[WEB] {args[0]}", flush=True)
        else:
            print(f"[WEB] {format}", flush=True)
        sys.stdout.flush()
    
    def log_error(self, format, *args):
        """Логирует ошибки."""
        if args:
            print(f"[WEB ERROR] {args[0]}", flush=True)
        else:
            print(f"[WEB ERROR] {format}", flush=True)
        sys.stderr.flush()

# ============================================================================
# WEB SERVER
# ============================================================================

def run_web_server(port: int = 80, build_dir: str = "build"):
    """
    Запускает веб-сервер для статического сайта.
    
    Args:
        port: Порт для прослушивания (по умолчанию 80)
        build_dir: Директория со статическими файлами
    """
    build_path = Path(__file__).parent / build_dir
    
    if not build_path.exists():
        print(f"Build directory '{build_path}' not found. Creating placeholder...")
        build_path.mkdir(parents=True, exist_ok=True)
        
        # Создаем простую заглушку
        index_html = build_path / "index.html"
        with open(index_html, 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>RGW 2.0</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>RGW 2.0 Web Interface</h1>
    <p>Web interface will be available here after build.</p>
</body>
</html>""")
    
    try:
        def handler_factory(*args, **kwargs):
            kwargs['directory'] = str(build_path.absolute())
            kwargs['flask_app'] = flask_app
            return CustomHTTPRequestHandler(*args, **kwargs)
        
        with socketserver.TCPServer(("", port), handler_factory) as httpd:
            print(f"Web server started on port {port}", flush=True)
            print(f"Serving files from: {build_path}", flush=True)
            print(f"API endpoints registered: {len(flask_app.url_map._rules)} routes", flush=True)
            sys.stdout.flush()
            
            httpd.serve_forever()
    except OSError as e:
        if "Permission denied" in str(e) and port < 1024:
            print(f"Error: Cannot bind to port {port}. Try using a port >= 1024 or run with sudo.")
            print(f"Attempting to use port 8080 instead...")
            run_web_server(port=8080, build_dir=build_dir)
        else:
            print(f"Error starting web server: {str(e)}")
    except KeyboardInterrupt:
        print("\nWeb server stopped")


def run():
    """Точка входа для запуска веб-сервера."""
    current_dir = Path(__file__).parent.absolute()
    build_dir = current_dir / "build"
    
    print(f"Web service starting from: {current_dir}", flush=True)
    print(f"Build directory: {build_dir}", flush=True)
    sys.stdout.flush()
    
    run_web_server(port=80, build_dir=str(build_dir))


if __name__ == '__main__':
    run()

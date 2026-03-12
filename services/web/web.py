"""
Веб-сервис для запуска статического сайта из папки build на порту 80.
Интегрирует Flask API для обработки API запросов напрямую.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

venv_path = Path(__file__).parent.parent.parent / "venv"
if venv_path.exists():
    # Динамически определяем версию Python в venv
    venv_lib = venv_path / "lib"
    if venv_lib.exists():
        # Ищем директорию pythonX.Y в lib/
        python_dirs = [d for d in venv_lib.iterdir() if d.is_dir() and d.name.startswith('python')]
        if python_dirs:
            # Берем первую найденную директорию (обычно одна)
            python_version_dir = python_dirs[0]
            venv_site_packages = python_version_dir / "site-packages"
            if venv_site_packages.exists() and str(venv_site_packages) not in sys.path:
                sys.path.insert(0, str(venv_site_packages))

try:
    import flask
except ImportError:
    print("[WEB] ERROR: Flask is not installed", flush=True)
    print(f"[WEB] Python: {sys.executable}", flush=True)
    print(f"[WEB] sys.path: {sys.path[:3]}", flush=True)
    print(f"[WEB] Please install: {sys.executable} -m pip install flask", flush=True)
    sys.exit(1)

import http.server
import socketserver
import json
import threading
import time
from flask import Flask, request, jsonify
import api.files as files_api
import api.robot as robot_api
import api.network_api as network_api_module
import services_manager

UNITREE_MOTOR_AVAILABLE = False
UNITREE_MOTOR_ERROR = None
UNITREE_MOTOR_ERROR_TRACEBACK = None
unitree_motor = None

try:
    import api.unitree_motor as unitree_motor_api
    unitree_motor = unitree_motor_api.UnitreeMotorAPI()
    UNITREE_MOTOR_AVAILABLE = True
except Exception as e:
    import traceback
    UNITREE_MOTOR_ERROR = str(e)
    UNITREE_MOTOR_ERROR_TRACEBACK = traceback.format_exc()

flask_app = Flask(__name__)
files = files_api.FilesAPI()
robot = robot_api.RobotAPI()
network_api = network_api_module.NetworkAPI()

@flask_app.after_request
def after_request(response):
    """Добавляет CORS заголовки ко всем ответам."""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

def register_status_endpoints():
    """Регистрирует endpoints для статуса системы."""
    
    @flask_app.route('/api/status', methods=['GET'])
    def api_status():
        """Возвращает статус робота."""
        import status
        return jsonify(status.get_robot_status())
    
    @flask_app.route('/api/status/service/<service_name>', methods=['GET'])
    def api_status_service(service_name):
        """Возвращает данные конкретного сервиса из status."""
        import status
        service_data = status.get_service_data(service_name)
        if service_data is None:
            return jsonify({
                "success": False,
                "message": f"Service '{service_name}' not found in status registry"
            }), 404
        return jsonify({
            "success": True,
            "service_name": service_name,
            "data": service_data
        })
    
    @flask_app.route('/api/status/services', methods=['GET'])
    def api_status_services():
        """Возвращает все зарегистрированные данные от сервисов."""
        import status
        return jsonify({
            "success": True,
            "services": status.get_all_service_data()
        })
    
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
        port = data.get('port')
        if port is None:
            try:
                import services_manager
                port = services_manager.get_api_port()
            except Exception:
                port = 5000
        timeout = data.get('timeout')  # Опциональный таймаут в секундах
        if not target_ip or not endpoint:
            return jsonify({"success": False, "message": "target_ip and endpoint required"}), 400
        return jsonify(network_api.send_data(target_ip, endpoint, payload, port=port, timeout=timeout))


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
    
    @flask_app.route('/api/settings', methods=['GET'])
    def api_settings_get():
        """Получает настройки робота."""
        return jsonify(robot_api.RobotAPI.get_settings())
    
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
        
        try:
            settings_data = {"RobotGroup": robot_group}
            result = network_api.send_data(target_ip, '/api/settings', settings_data)
            
            if result.get('success'):
                remote_response = result.get('response')
                if remote_response and isinstance(remote_response, dict):
                    if remote_response.get('success'):
                        return jsonify({
                            "success": True,
                            "message": "Group updated successfully",
                            "settings": remote_response.get('settings', {})
                        })
                    else:
                        return jsonify({
                            "success": False,
                            "message": remote_response.get('message', 'Unknown error')
                        })
                else:
                    return jsonify({
                        "success": False,
                        "message": f"Unexpected response format: {type(remote_response)}"
                    })
            else:
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
            
            if status == 'OFF':
                can_disable, depending_services = manager.can_disable_service(service_name)
                if not can_disable and not disable_dependents:
                    return jsonify({
                        "success": False,
                        "message": "Cannot disable service",
                        "depending_services": depending_services,
                        "requires_confirmation": True
                    }), 400
                
                if disable_dependents and depending_services:
                    disabled_list = manager.disable_service_with_dependencies(service_name)
                    return jsonify({
                        "success": True,
                        "message": f"Service and dependencies disabled",
                        "disabled_services": disabled_list
                    })
            
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

    @flask_app.route('/api/services/<service_name>/enabled', methods=['POST'])
    def api_service_enabled(service_name):
        """Обновляет ручной статус запуска сервиса (enabled)."""
        try:
            data = request.get_json() or {}
            enabled = data.get('enabled')
            
            if enabled is None:
                return jsonify({
                    "success": False,
                    "message": "enabled parameter required (true/false)"
                }), 400
            
            if not isinstance(enabled, bool):
                try:
                    enabled = bool(enabled)
                except (ValueError, TypeError):
                    return jsonify({
                        "success": False,
                        "message": "Invalid enabled value. Must be boolean"
                    }), 400
            
            manager = services_manager.get_services_manager()
            success = manager.update_service_enabled(service_name, enabled)
            
            if success:
                return jsonify({
                    "success": True,
                    "message": f"Service {'enabled' if enabled else 'disabled'} for startup"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Failed to update enabled status"
                }), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    
    @flask_app.route('/api/services/<service_name>/shutdown_request', methods=['POST'])
    def api_service_shutdown_request(service_name):
        """Отправляет запрос на выключение сервиса (для unitree_motor_control требуется 3 запроса)."""
        try:
            manager = services_manager.get_services_manager()
            service_info = manager.get_service(service_name)
            
            if not service_info:
                return jsonify({
                    "success": False,
                    "message": f"Service {service_name} not found"
                }), 404
            
            current_status = service_info.get("status", "OFF")
            success = manager.update_service_status(service_name, "OFF")
            
            if success:
                updated_info = manager.get_service(service_name)
                updated_status = updated_info.get("status", "OFF") if updated_info else current_status
                
                if service_name == "unitree_motor_control":
                    if updated_status == "ON":
                        return jsonify({
                            "success": True,
                            "message": "Shutdown request sent (requires 3 consecutive requests)",
                            "status": updated_status,
                            "requires_more_requests": True,
                            "service_name": service_name
                        })
                    else:
                        return jsonify({
                            "success": True,
                            "message": "Service shutdown initiated",
                            "status": updated_status,
                            "requires_more_requests": False,
                            "service_name": service_name
                        })
                else:
                    return jsonify({
                        "success": True,
                        "message": f"Status updated to {updated_status}",
                        "status": updated_status,
                        "service_name": service_name
                    })
            else:
                return jsonify({
                    "success": False,
                    "message": "Failed to update status"
                }), 500
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500


def register_unitree_motor_endpoints():
    """Регистрирует endpoints для управления моторами Unitree."""
    
    @flask_app.route('/api/unitree_motor/status', methods=['GET'])
    def api_unitree_status():
        """Получает статус сервиса моторов и информацию об ошибках."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "available": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        # Проверяем, инициализирован ли контроллер
        try:
            from services.unitree_motor_control.unitree_motor_control import get_controller
            controller = get_controller()
            if controller and controller.initialized:
                return jsonify({
                    "success": True,
                    "available": True,
                    "controller_initialized": True,
                    "message": "Unitree motor service is available and running"
                })
            else:
                return jsonify({
                    "success": False,
                    "available": True,
                    "controller_initialized": False,
                    "message": "Unitree motor service is available but controller is not initialized"
                }), 503
        except Exception as e:
            import traceback
            return jsonify({
                "success": False,
                "available": True,
                "controller_initialized": False,
                "message": f"Error checking controller status: {str(e)}",
                "error": str(e),
                "error_traceback": traceback.format_exc()
            }), 503
    
    @flask_app.route('/api/unitree_motor/set_angle', methods=['POST'])
    def api_unitree_set_angle():
        """Устанавливает угол для одного мотора."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        data = request.get_json() or {}
        motor_index = data.get('motor_index')
        angle = data.get('angle')
        velocity = data.get('velocity', 0.0)
        
        if motor_index is None or angle is None:
            return jsonify({"success": False, "message": "motor_index and angle are required"}), 400
        
        try:
            motor_index = int(motor_index)
            angle = float(angle)
            velocity = float(velocity)
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Invalid motor_index, angle, or velocity"}), 400
        
        try:
            return jsonify(unitree_motor.set_motor_angle(motor_index, angle, velocity))
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in set_motor_angle: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error setting motor angle: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/set_angles', methods=['POST'])
    def api_unitree_set_angles():
        """Устанавливает углы для нескольких моторов. Поддерживает частичные обновления."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        data = request.get_json() or {}
        angles = data.get('angles', {})
        velocity = data.get('velocity', 0.0)
        interpolation = data.get('interpolation', 0.0)
        source = data.get('source', 'api')
        
        if not angles:
            return jsonify({"success": False, "message": "angles dictionary is required"}), 400
        
        try:
            angles_dict = {int(k): round(float(v), 4) for k, v in angles.items()}
            velocity = float(velocity)
            interpolation = float(interpolation)
        except (ValueError, TypeError) as e:
            return jsonify({"success": False, "message": f"Invalid angles, velocity or interpolation: {str(e)}"}), 400
        
        try:
            return jsonify(unitree_motor.set_motor_angles(angles_dict, velocity, source, interpolation))
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in set_motor_angles: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error setting motor angles: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/get_angles', methods=['GET'])
    def api_unitree_get_angles():
        """Получает текущие углы всех моторов."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        try:
            return jsonify(unitree_motor.get_motor_angles())
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in get_motor_angles: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error getting motor angles: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/neural_network', methods=['POST'])
    def api_unitree_neural_network():
        """Устанавливает углы моторов из данных нейронной сети."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        data = request.get_json() or {}
        try:
            return jsonify(unitree_motor.set_motor_angles_from_neural_network(data))
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in neural_network: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error setting motor angles from neural network: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/config', methods=['GET'])
    def api_unitree_config_get():
        """Получает конфигурацию контроллера."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        try:
            return jsonify(unitree_motor.get_controller_config())
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in get_controller_config: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error getting controller config: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/config', methods=['POST'])
    def api_unitree_config_set():
        """Устанавливает конфигурацию контроллера."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        data = request.get_json() or {}
        try:
            return jsonify(unitree_motor.set_controller_config(data))
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in set_controller_config: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error setting controller config: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500
    
    @flask_app.route('/api/unitree_motor/initialize', methods=['POST'])
    def api_unitree_initialize():
        """Инициализирует контроллер моторов."""
        if not UNITREE_MOTOR_AVAILABLE:
            return jsonify({
                "success": False,
                "message": "Unitree motor service is not available",
                "error": UNITREE_MOTOR_ERROR,
                "error_traceback": UNITREE_MOTOR_ERROR_TRACEBACK
            }), 503
        
        try:
            from services.unitree_motor_control.unitree_motor_control import get_controller
            from services_manager import get_services_manager
            
            manager = get_services_manager()
            service_info = manager.get_service("unitree_motor_control")
            params = manager.get_service_parameters("unitree_motor_control")
            
            domain_id = params.get("id", 1)
            network_interface = params.get("network", "lo")
            
            controller = get_controller()
            
            if not controller:
                return jsonify({
                    "success": False,
                    "message": "Controller not available. Service may not be running.",
                    "initialized": False
                }), 503
            
            if controller.initialized:
                try:
                    controller.reinitialize_controller(domain_id=domain_id, network_interface=network_interface)
                    return jsonify({
                        "success": True,
                        "message": "Controller reinitialized successfully",
                        "initialized": True,
                        "domain_id": domain_id,
                        "network_interface": network_interface
                    })
                except Exception as e:
                    import traceback
                    error_traceback = traceback.format_exc()
                    return jsonify({
                        "success": False,
                        "message": f"Error reinitializing controller: {str(e)}",
                        "error": str(e),
                        "error_traceback": error_traceback,
                        "initialized": False
                    }), 500
            
            try:
                controller.init(domain_id=domain_id, network_interface=network_interface)
                controller.start_control()
                return jsonify({
                    "success": True,
                    "message": "Controller initialized successfully",
                    "initialized": True,
                    "domain_id": domain_id,
                    "network_interface": network_interface
                })
            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                return jsonify({
                    "success": False,
                    "message": f"Error initializing controller: {str(e)}",
                    "error": str(e),
                    "error_traceback": error_traceback,
                    "initialized": False
                }), 500
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            print(f"[WEB ERROR] Error in initialize: {e}", flush=True)
            print(f"[WEB ERROR] Traceback:\n{error_traceback}", flush=True)
            return jsonify({
                "success": False,
                "message": f"Error initializing controller: {str(e)}",
                "error": str(e),
                "error_traceback": error_traceback
            }), 500


register_status_endpoints()
register_files_endpoints()
register_directory_endpoints()
register_network_endpoints()
register_robot_endpoints()
register_services_endpoints()
register_unitree_motor_endpoints()

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Кастомный обработчик HTTP запросов с поддержкой SPA и встроенного API."""
    
    def __init__(self, *args, **kwargs):
        self.flask_app = kwargs.pop('flask_app', None)
        self.custom_directory = kwargs.pop('directory', None)
        super().__init__(*args, directory=self.custom_directory, **kwargs)
    
    def translate_path(self, path):
        """Переопределяем translate_path для правильной обработки путей."""
        # Убираем query string если есть
        if '?' in path:
            path = path.split('?')[0]
        
        # Если directory задан, используем его
        if self.custom_directory:
            # Убираем ведущий слэш
            path = path.lstrip('/')
            # Если путь пустой или это директория, добавляем index.html
            if not path or path.endswith('/'):
                path = 'index.html'
            # Формируем полный путь
            full_path = os.path.join(self.custom_directory, path)
            return os.path.normpath(full_path)
        
        # Иначе используем стандартную логику
        return super().translate_path(path)
    
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
            body = None
            if method in ['POST', 'PUT', 'DELETE']:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    body = self.rfile.read(content_length)
            
            from werkzeug.test import Client
            from werkzeug.wrappers import Response
            
            client = Client(self.flask_app, Response)
            
            path_for_request = self.path
            query_string = None
            if '?' in self.path:
                path_for_request, query_string = self.path.split('?', 1)
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
            
            self.send_response(response.status_code)
            for header, value in response.headers.items():
                self.send_header(header, value)
            self.end_headers()
            
            if response.data:
                try:
                    self.wfile.write(response.data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                    
        except (BrokenPipeError, ConnectionResetError, OSError):
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
                pass
    
    def guess_type(self, path):
        """Определяет MIME тип файла с правильной поддержкой JavaScript модулей."""
        import mimetypes
        # Используем mimetypes напрямую вместо super().guess_type() для совместимости
        mimetype, encoding = mimetypes.guess_type(path)
        
        # Исправляем MIME типы для JavaScript модулей
        if path.endswith('.js'):
            mimetype = 'application/javascript'
        elif path.endswith('.mjs'):
            mimetype = 'application/javascript'
        elif path.endswith('.css'):
            mimetype = 'text/css'
        elif path.endswith('.json'):
            mimetype = 'application/json'
        elif path.endswith('.wasm'):
            mimetype = 'application/wasm'
        
        return mimetype, encoding
    
    def send_head(self):
        """Отправляет заголовки ответа с правильными MIME типами."""
        path = self.translate_path(self.path)
        f = None
        try:
            f = open(path, 'rb')
        except OSError:
            # Не используем send_error, чтобы избежать вызова log_error
            self.send_response(404)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            return None
        
        try:
            fs = os.fstat(f.fileno())
            # Используем guess_type для правильного определения MIME типа
            ctype = self.guess_type(self.path)[0]
            if ctype is None:
                ctype = 'application/octet-stream'
            
            # Убеждаемся, что для JavaScript модулей установлен правильный тип
            if self.path.endswith('.js') or self.path.endswith('.mjs'):
                ctype = 'application/javascript; charset=utf-8'
            elif self.path.endswith('.css'):
                ctype = 'text/css; charset=utf-8'
            
            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            if f:
                f.close()
            raise
    
    def do_GET(self):
        """Обрабатывает GET запросы."""
        if self.path.startswith('/api') or self.path == '/health':
            self.handle_api_request('GET')
            return
        
        # Для корневого пути сразу перенаправляем на index.html
        if self.path == '/' or self.path == '':
            self.path = '/index.html'
        
        # Проверяем существование файла
        try:
            file_path = self.translate_path(self.path)
        except Exception:
            file_path = None
        
        # Для статических файлов (assets, css, js и т.д.) не перенаправляем на index.html
        # Перенаправляем только для HTML страниц (SPA routing)
        if file_path is None or not os.path.exists(file_path):
            # Если это статический файл (assets, css, js, images и т.д.), возвращаем 404
            is_static_file = (
                any(self.path.startswith(prefix) for prefix in ['/assets/', '/static/', '/css/', '/js/', '/images/', '/img/', '/fonts/', '/font/']) or
                any(self.path.lower().endswith(ext) for ext in ['.js', '.mjs', '.css', '.json', '.wasm', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot'])
            )
            
            if is_static_file:
                # Статический файл не найден - возвращаем 404
                self.send_response(404)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<h1>404 Not Found</h1>')
                return
            else:
                # Для HTML страниц (SPA routing) перенаправляем на index.html
                original_path = self.path
                self.path = '/index.html'
                # Проверяем существование index.html после изменения пути
                try:
                    index_path = self.translate_path(self.path)
                    # Отладочный вывод (можно убрать после исправления)
                    if not index_path or not os.path.exists(index_path):
                        if os.environ.get('RGW2_DEBUG'):
                            print(f"[WEB DEBUG] index.html not found at: {index_path}", flush=True)
                            print(f"[WEB DEBUG] directory: {self.directory}", flush=True)
                            print(f"[WEB DEBUG] path: {self.path}", flush=True)
                    
                    if index_path and os.path.exists(index_path) and os.path.isfile(index_path):
                        # index.html существует, обрабатываем через send_head и send файл
                        f = self.send_head()
                        if f:
                            try:
                                self.copyfile(f, self.wfile)
                            finally:
                                f.close()
                        return
                    else:
                        # index.html не найден, возвращаем 404
                        self.send_response(404)
                        self.send_header('Content-Type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b'<h1>404 Not Found - index.html not found</h1>')
                        return
                except Exception as e:
                    # Ошибка при проверке, возвращаем 404
                    import traceback
                    print(f"[WEB ERROR] Exception in do_GET: {e}", flush=True)
                    print(f"[WEB ERROR] Traceback: {traceback.format_exc()}", flush=True)
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f'<h1>404 Not Found - Error: {str(e)}</h1>'.encode())
                    return
        
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
        """Логирует запросы. Пропускает частые API запросы для уменьшения шума в логах."""
        if args and args[0]:
            log_line = args[0]
            if '/api' in log_line:
                return
        return
    
    def log_error(self, format, *args):
        """Логирует ошибки."""
        if args:
            print(f"[WEB ERROR] {args[0]}", flush=True)
        else:
            print(f"[WEB ERROR] {format}", flush=True)
        sys.stderr.flush()

def run_web_server(port: int = 80, build_dir: str = "build"):
    """
    Запускает веб-сервер для статического сайта.
    
    Args:
        port: Порт для прослушивания (по умолчанию 80)
        build_dir: Директория со статическими файлами
    """
    build_path = Path(__file__).parent / build_dir
    
    if not build_path.exists():
        if os.environ.get('RGW2_DEBUG'):
            print(f"Build directory '{build_path}' not found. Creating placeholder...")
        build_path.mkdir(parents=True, exist_ok=True)
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
    
    try:
        def handler_factory(*args, **kwargs):
            kwargs['directory'] = str(build_path.absolute())
            kwargs['flask_app'] = flask_app
            return CustomHTTPRequestHandler(*args, **kwargs)
        
        with socketserver.ThreadingTCPServer(("", port), handler_factory) as httpd:
            # Разрешаем переиспользование адреса для быстрого перезапуска
            httpd.allow_reuse_address = True
            if os.environ.get('RGW2_DEBUG'):
                print(f"Web server started on port {port}", flush=True)
                print(f"Serving files from: {build_path}", flush=True)
                print(f"API endpoints registered: {len(flask_app.url_map._rules)} routes", flush=True)
                sys.stdout.flush()
            
            shutdown_requested = threading.Event()
            web_shutdown_allowed = threading.Event()
            
            def check_motor_status_on_shutdown():
                """Проверяет статус моторов при запросе на завершение."""
                while not shutdown_requested.is_set():
                    time.sleep(0.5)
                
                if web_shutdown_allowed.is_set():
                    print("\n[WEB] Motor service shutdown completed. Shutting down web server...", flush=True)
                    httpd.shutdown()
                    return
                
                try:
                    manager = services_manager.get_services_manager()
                    web_dependencies = manager.get_service_dependencies("web")
                    
                    active_dependencies = []
                    for dep_name in web_dependencies:
                        dep_info = manager.get_service(dep_name)
                        if dep_info and dep_info.get("status") == "ON":
                            active_dependencies.append(dep_name)
                    
                    if active_dependencies:
                        print(f"\n[WEB] CRITICAL: Active dependencies detected: {', '.join(active_dependencies)}. Web service will not shut down.", flush=True)
                        print("[WEB] Please shut down dependencies first.", flush=True)
                        shutdown_requested.clear()
                        print("[WEB] Web service continues running...", flush=True)
                    else:
                        print("\n[WEB] All dependencies are inactive. Shutting down web server...", flush=True)
                        httpd.shutdown()
                except Exception as e:
                    print(f"\n[WEB] Warning: Could not check dependencies status: {e}", flush=True)
                    print("[WEB] Shutting down web server...", flush=True)
                    httpd.shutdown()
            
            def monitor_dependencies_shutdown():
                """Мониторит завершение зависимостей для завершения веб-сервера."""
                while True:
                    try:
                        if shutdown_requested.is_set():
                            manager = services_manager.get_services_manager()
                            web_dependencies = manager.get_service_dependencies("web")
                            
                            if not web_dependencies:
                                web_shutdown_allowed.set()
                                if shutdown_requested.is_set():
                                    httpd.shutdown()
                                break
                            
                            all_dependencies_off = True
                            for dep_name in web_dependencies:
                                dep_info = manager.get_service(dep_name)
                                dep_status = dep_info.get("status", "OFF") if dep_info else "OFF"
                                
                                if dep_status == "ON":
                                    all_dependencies_off = False
                                    break
                                
                                import run
                                try:
                                    runner = run.ServiceRunner()
                                    if hasattr(runner, 'services') and hasattr(runner, 'threads'):
                                        dep_thread_alive = False
                                        for i, service_info in enumerate(runner.services):
                                            if service_info.get("service_name") == dep_name:
                                                if i < len(runner.threads):
                                                    dep_thread_alive = runner.threads[i].is_alive()
                                                break
                                        
                                        if dep_thread_alive:
                                            all_dependencies_off = False
                                            break
                                except Exception:
                                    pass
                            
                            if all_dependencies_off and shutdown_requested.is_set():
                                print("[WEB] All dependencies shutdown detected. Allowing web server shutdown...", flush=True)
                                web_shutdown_allowed.set()
                                httpd.shutdown()
                                break
                    except Exception as e:
                        pass
                    time.sleep(1)
            
            check_thread = threading.Thread(target=check_motor_status_on_shutdown, daemon=True)
            monitor_thread = threading.Thread(target=monitor_dependencies_shutdown, daemon=True)
            check_thread.start()
            monitor_thread.start()
            
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                shutdown_requested.set()
                check_thread.join(timeout=2.0)
                if check_thread.is_alive():
                    print("\n[WEB] Shutting down web server...", flush=True)
                    httpd.shutdown()
    except OSError as e:
        error_msg = str(e)
        if "Permission denied" in error_msg and port < 1024:
            print(f"Error: Cannot bind to port {port}. Try using a port >= 1024 or run with sudo.", flush=True)
            for try_port in [8080, 8081, 8082, 8083, 8084, 8085]:
                if check_port_available(try_port):
                    print(f"Port {try_port} is available. Using it instead...", flush=True)
                    run_web_server(port=try_port, build_dir=build_dir)
                    return
            print(f"Error: All ports 8080-8085 are in use. Please free a port or kill existing web server.", flush=True)
        elif "Address already in use" in error_msg:
            print(f"Port {port} is already in use. Trying alternative ports...", flush=True)
            found_port = None
            for try_port in [8080, 8081, 8082, 8083, 8084, 8085]:
                if try_port != port and check_port_available(try_port):
                    found_port = try_port
                    break
            if found_port:
                print(f"Port {found_port} is available. Using it instead...", flush=True)
                run_web_server(port=found_port, build_dir=build_dir)
                return
        else:
                print(f"Error: All ports 8080-8085 are in use. Please free a port or kill existing web server.", flush=True)
                print(f"Attempting to kill process on port {port}...", flush=True)
                try:
                    import subprocess
                    subprocess.run(["fuser", "-k", f"{port}/tcp"], 
                                 capture_output=True, timeout=2, stderr=subprocess.DEVNULL)
                    time.sleep(1)
                    if check_port_available(port):
                        print(f"Port {port} is now available. Retrying...", flush=True)
                        run_web_server(port=port, build_dir=build_dir)
                        return
                except Exception:
                    pass
                print(f"Error: Could not free port {port}. Please manually kill the process using it.", flush=True)
    except Exception as e:
        print(f"Error starting web server: {str(e)}", flush=True)
    except KeyboardInterrupt:
        print("\n[WEB] Web server stopped", flush=True)


def run():
    """Точка входа для запуска веб-сервера."""
    current_dir = Path(__file__).parent.absolute()
    build_dir = current_dir / "build"
    
    try:
        manager = services_manager.get_services_manager()
        params = manager.get_service_parameters("web")
        port = params.get("port", 8080)
    except Exception:
        port = 8080
    
    if os.environ.get('RGW2_DEBUG'):
        print(f"Web service starting from: {current_dir}", flush=True)
        print(f"Build directory: {build_dir}", flush=True)
        print(f"Port: {port}", flush=True)
        sys.stdout.flush()
    
    run_web_server(port=port, build_dir=str(build_dir))


if __name__ == '__main__':
    run()

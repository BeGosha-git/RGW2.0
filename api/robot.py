"""
API модуль для работы с данным роботом.
"""
import json
import os
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
import status

# Определяем корень проекта
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Повторные HTTP-запросы с тем же command+args, пока выполнение не завершено — отклоняются.
_execution_inflight: set[str] = set()
_execution_lock = threading.Lock()


class RobotAPI:
    """API для работы с текущим роботом."""

    @staticmethod
    def _execution_fingerprint(command: str, args: Optional[list]) -> str:
        norm_args = list(args or [])
        try:
            return json.dumps({"c": str(command), "a": norm_args}, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            return json.dumps({"c": str(command), "a": [str(x) for x in norm_args]}, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _execution_begin(key: str) -> bool:
        with _execution_lock:
            if key in _execution_inflight:
                return False
            _execution_inflight.add(key)
            return True

    @staticmethod
    def _execution_end(key: str) -> None:
        with _execution_lock:
            _execution_inflight.discard(key)
    
    @staticmethod
    def get_robot_status() -> Dict[str, Any]:
        """
        Получает статус текущего робота.
        
        Returns:
            Статус робота
        """
        try:
            return status.get_robot_status()
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting robot status: {str(e)}"
            }
    
    @staticmethod
    def get_settings() -> Dict[str, Any]:
        """
        Получает настройки робота.
        
        Returns:
            Настройки робота
        """
        try:
            settings_path = PROJECT_ROOT / "data" / "settings.json"
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return {
                        "success": True,
                        "settings": json.load(f)
                    }
            else:
                return {
                    "success": False,
                    "message": "settings.json not found"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error reading settings: {str(e)}"
            }
    
    @staticmethod
    def update_settings(new_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет настройки робота (обновляет существующие и добавляет новые).
        
        Args:
            new_settings: Новые настройки
            
        Returns:
            Результат операции
        """
        try:
            # Создаем папку data если её нет
            data_dir = PROJECT_ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            settings_path = data_dir / "settings.json"
            current_settings = {}
            
            # Читаем текущие настройки
            if settings_path.exists():
                with open(settings_path, 'r', encoding='utf-8') as f:
                    current_settings = json.load(f)
            
            # Обновляем существующие параметры и добавляем новые
            updated = False
            for key, value in new_settings.items():
                if current_settings.get(key) != value:
                    current_settings[key] = value
                    updated = True
            
            if updated:
                with open(settings_path, 'w', encoding='utf-8') as f:
                    json.dump(current_settings, f, indent=4, ensure_ascii=False)
                
                return {
                    "success": True,
                    "message": "Settings updated successfully",
                    "settings": current_settings
                }
            else:
                return {
                    "success": True,
                    "message": "No settings to update",
                    "settings": current_settings
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating settings: {str(e)}"
            }
    
    @staticmethod
    def get_version() -> Dict[str, Any]:
        """
        Получает версию робота.
        
        Returns:
            Информация о версии
        """
        try:
            version_path = PROJECT_ROOT / "data" / "version.json"
            if version_path.exists():
                with open(version_path, 'r', encoding='utf-8') as f:
                    return {
                        "success": True,
                        "version": json.load(f)
                    }
            else:
                return {
                    "success": False,
                    "message": "version.json not found"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error reading version: {str(e)}"
            }
    
    @staticmethod
    def execute_command(command: str, args: list = None) -> Dict[str, Any]:
        """
        Выполняет команду на роботе.
        
        Args:
            command: Команда для выполнения
            args: Аргументы команды
            
        Returns:
            Результат выполнения
        """
        key = RobotAPI._execution_fingerprint(command, args)
        if not RobotAPI._execution_begin(key):
            return {
                "success": False,
                "message": "Такая команда уже выполняется",
                "duplicate": True,
                "command": command,
                "args": args or [],
            }
        try:
            try:
                if command == "g1_arm_action":
                    action_name = ""
                    if args and len(args) > 0:
                        action_name = str(args[0]).strip()
                    if not action_name:
                        return {
                            "success": False,
                            "message": "g1_arm_action requires action name in args[0]"
                        }
                    return RobotAPI.execute_g1_arm_action(action_name)

                import execute
                
                # Собираем stdout и stderr
                output_lines = []
                error_lines = []
                
                def log_callback(line: str):
                    """Callback для сбора вывода команды."""
                    if line.startswith("ERROR: "):
                        error_lines.append(line[7:])  # Убираем префикс "ERROR: "
                    else:
                        output_lines.append(line)
                
                executor = execute.CommandExecutor(log_callback=log_callback)
                
                # Определяем, нужен ли shell режим
                # Shell нужен для команд, которые требуют интерпретации (sudo, bash, sh и т.д.)
                # или когда есть аргументы и команда не является исполняемым файлом
                use_shell = command in ['sudo', 'bash', 'sh', 'zsh', 'fish', 'python3', 'python']
                
                if use_shell and args:
                    # Объединяем команду и аргументы в одну строку для shell
                    full_command = f"{command} {' '.join(str(arg) for arg in args)}"
                    return_code = executor.execute(full_command, shell=True)
                elif args:
                    # Если есть аргументы, но shell не нужен, передаем как список
                    return_code = executor.execute(command, args)
                else:
                    # Команда без аргументов
                    return_code = executor.execute(command, [])
                
                result = {
                    "success": return_code == 0,
                    "return_code": return_code,
                    "command": command,
                    "args": args or []
                }
                
                # Добавляем вывод команды
                if output_lines:
                    result["stdout"] = "\n".join(output_lines)
                if error_lines:
                    result["stderr"] = "\n".join(error_lines)
                    # Если есть stderr, добавляем его в message для удобства
                    if not result["success"]:
                        result["message"] = "\n".join(error_lines)
                
                return result
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error executing command: {str(e)}",
                    "command": command
                }
        finally:
            RobotAPI._execution_end(key)

    @staticmethod
    def _get_robot_type() -> str:
        try:
            settings_path = PROJECT_ROOT / "data" / "settings.json"
            if not settings_path.exists():
                return ""
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            return str(settings.get("RobotType", "")).strip().upper()
        except Exception:
            return ""

    @staticmethod
    def _filter_commands_by_robot_type(commands: List[Dict[str, Any]], robot_type: str) -> List[Dict[str, Any]]:
        if not robot_type:
            return commands

        filtered: List[Dict[str, Any]] = []
        for cmd in commands:
            allowed_types = cmd.get("robotTypes")
            if not allowed_types:
                filtered.append(cmd)
                continue
            normalized = {str(item).strip().upper() for item in allowed_types}
            if robot_type in normalized:
                filtered.append(cmd)
        return filtered

    @staticmethod
    def get_g1_arm_actions() -> Dict[str, Any]:
        try:
            from services.unitree_motor_control.g1_arm_action_service import get_g1_actions
            actions = get_g1_actions()
            return {
                "success": True,
                "actions": [{"name": name, "id": action_id} for name, action_id in actions.items()],
                "count": len(actions),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error loading G1 arm actions: {e}",
                "actions": [],
            }

    @staticmethod
    def execute_g1_arm_action(action_name: str) -> Dict[str, Any]:
        robot_type = RobotAPI._get_robot_type()
        if robot_type != "G1":
            return {
                "success": False,
                "message": f"G1 arm actions are available only for RobotType=G1 (current: {robot_type or 'UNKNOWN'})",
            }

        try:
            from services.unitree_motor_control.g1_arm_action_service import get_g1_arm_action_service
            network_interface = "lo"
            domain_id = 0
            try:
                import services_manager
                manager = services_manager.get_services_manager()
                params = manager.get_service_parameters("unitree_motor_control")
                network_interface = params.get("network", "lo")
                domain_id = int(params.get("id", 0))
            except Exception:
                pass

            service = get_g1_arm_action_service()
            return service.execute(
                action_name=action_name,
                network_interface=network_interface,
                domain_id=domain_id,
            )
        except Exception as e:
            return {
                "success": False,
                "message": f"Error executing G1 arm action: {e}",
            }
    
    @staticmethod
    def ensure_default_commands() -> None:
        """
        Создает дефолтный commands.json если файл не существует.
        Проверяет наличие обязательных команд и добавляет их если отсутствуют.
        """
        commands_path = PROJECT_ROOT / "data" / "commands.json"
        data_dir = commands_path.parent
        data_dir.mkdir(parents=True, exist_ok=True)

        _default_commands = [
            {
                "id": "update_system",
                "name": "Обновление системы",
                "description": "Ищет более новую версию и загружает только измененные файлы",
                "command": "python3",
                "args": ["upgrade.py"],
                "showButton": True,
                "buttonConfig": {"position": 1, "color": "primary", "icon": "update"},
            },
            {
                "id": "force_update_system",
                "name": "Принудительное обновление",
                "description": "Принудительно обновляет файлы с удалённого робота, игнорируя версию",
                "command": "python3",
                "args": ["upgrade.py", "--force"],
                "showButton": True,
                "buttonConfig": {"position": 2, "color": "danger", "icon": "update"},
            },
        ]

        if commands_path.exists():
            try:
                with open(commands_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                commands = data.get("commands", [])
                existing_ids = {cmd.get("id") for cmd in commands}
                changed = False
                for default_cmd in _default_commands:
                    if default_cmd["id"] not in existing_ids:
                        commands.append(default_cmd)
                        changed = True
                if changed:
                    data["commands"] = commands
                    with open(commands_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception:
                # Файл поврежден — пересоздаём с дефолтными командами
                default_data = {
                    "version": "1.0.0",
                    "lastUpdated": None,
                    "commands": _default_commands,
                }
                try:
                    with open(commands_path, 'w', encoding='utf-8') as f:
                        json.dump(default_data, f, indent=4, ensure_ascii=False)
                except Exception:
                    pass
        else:
            default_data = {
                "version": "1.0.0",
                "lastUpdated": None,
                "commands": _default_commands,
            }
            try:
                with open(commands_path, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
    
    @staticmethod
    def get_commands() -> Dict[str, Any]:
        """
        Получает список быстрых команд из commands.json.
        
        Returns:
            Список команд
        """
        try:
            RobotAPI.ensure_default_commands()
            commands_path = PROJECT_ROOT / "data" / "commands.json"
            if commands_path.exists():
                with open(commands_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {
                        "success": True,
                        "commands": RobotAPI._filter_commands_by_robot_type(
                            data.get("commands", []),
                            RobotAPI._get_robot_type(),
                        ),
                        "version": data.get("version", "1.0.0"),
                        "lastUpdated": data.get("lastUpdated")
                    }
            else:
                # Возвращаем пустой список если файл не существует
                return {
                    "success": True,
                    "commands": [],
                    "version": "1.0.0",
                    "lastUpdated": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error reading commands: {str(e)}",
                "commands": []
            }
    
    @staticmethod
    def update_commands(new_commands: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обновляет список быстрых команд в commands.json.
        
        Args:
            new_commands: Новые команды (словарь с ключом "commands" - список команд)
            
        Returns:
            Результат операции
        """
        try:
            import datetime
            
            # Создаем папку data если её нет
            data_dir = PROJECT_ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            commands_path = data_dir / "commands.json"
            current_data = {
                "commands": [],
                "version": "1.0.0",
                "lastUpdated": None
            }
            
            # Читаем текущие команды если файл существует
            if commands_path.exists():
                try:
                    with open(commands_path, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                except Exception:
                    pass  # Если не удалось прочитать, используем значения по умолчанию
            
            # Обновляем команды
            if "commands" in new_commands:
                current_data["commands"] = new_commands["commands"]
            
            if "version" in new_commands:
                current_data["version"] = new_commands["version"]
            
            # Обновляем время последнего изменения
            current_data["lastUpdated"] = datetime.datetime.now().isoformat()
            
            # Сохраняем в файл
            with open(commands_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, indent=4, ensure_ascii=False)
            
            return {
                "success": True,
                "message": "Commands updated successfully",
                "commands": current_data["commands"],
                "version": current_data["version"],
                "lastUpdated": current_data["lastUpdated"]
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error updating commands: {str(e)}"
            }

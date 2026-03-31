"""
API модуль для работы с данным роботом.
"""
import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
import status

# Определяем корень проекта
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Повторные HTTP-запросы с тем же command+args, пока выполнение не завершено — отклоняются.
_execution_inflight: Set[str] = set()
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

                if command == "g1_loco":
                    mode = ""
                    if args and len(args) > 0:
                        mode = str(args[0]).strip()
                    if not mode:
                        return {"success": False, "message": "g1_loco requires mode name in args[0]"}
                    # optional numeric args
                    rest = args[1:] if isinstance(args, list) else []
                    return RobotAPI.execute_g1_loco_mode(mode, rest)

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
        """
        Возвращает список доступных G1 жестов.

        Важно: `services.unitree_motor_control.g1_arm_action_service` при импорте
        выполняет native-инициализацию (CycloneDDS/SDK). Чтобы не убивать основной
        процесс `rgw2`, загружаем и получаем действия в отдельном subprocess.
        """
        import subprocess
        import json as _json

        script = (
            "import sys, json\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from services.unitree_motor_control.g1_arm_action_service import get_g1_actions\n"
            "actions = get_g1_actions()\n"
            "print(json.dumps({'actions': actions}, ensure_ascii=False))\n"
        )

        try:
            proc = subprocess.run(
                [sys.executable, "-c", script, str(PROJECT_ROOT)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            stdout = proc.stdout.strip()
            if stdout:
                data = _json.loads(stdout)
                actions = data.get("actions") or {}
                actions_list = [{"name": name, "id": action_id} for name, action_id in actions.items()]
                return {
                    "success": True,
                    "actions": actions_list,
                    "count": len(actions_list),
                }

            stderr = proc.stderr.strip()
            return {
                "success": False,
                "message": f"G1 arm actions subprocess failed (rc={proc.returncode}): {stderr[-300:] if stderr else 'no output'}",
                "actions": [],
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "G1 arm actions subprocess timed out",
                "actions": [],
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error loading G1 arm actions: {e}",
                "actions": [],
            }

    @staticmethod
    def execute_g1_arm_action(action_name: str) -> Dict[str, Any]:
        import subprocess
        import json as _json

        robot_type = RobotAPI._get_robot_type()
        if robot_type != "G1":
            return {
                "success": False,
                "message": f"G1 arm actions are available only for RobotType=G1 (current: {robot_type or 'UNKNOWN'})",
            }

        network_interface = "eth0"
        domain_id = 0
        try:
            import services_manager
            manager = services_manager.get_services_manager()
            params = manager.get_service_parameters("unitree_motor_control")
            network_interface = params.get("network", "eth0")
            domain_id = int(params.get("id", 0))
        except Exception:
            pass

        # Запускаем SDK в отдельном процессе чтобы нативный краш не убивал основной сервис.
        script = (
            "import sys, json\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from services.unitree_motor_control.g1_arm_action_service import get_g1_arm_action_service\n"
            "svc = get_g1_arm_action_service()\n"
            "result = svc.execute(action_name=sys.argv[2], network_interface=sys.argv[3], domain_id=int(sys.argv[4]))\n"
            "print(json.dumps(result))\n"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script, str(PROJECT_ROOT), action_name, network_interface, str(domain_id)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            stdout = proc.stdout.strip()
            if stdout:
                # Берём последнюю строку (может быть вывод SDK перед JSON)
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        return _json.loads(line)
            stderr = proc.stderr.strip()
            return {
                "success": False,
                "message": f"G1 arm action subprocess failed (rc={proc.returncode}): {stderr[-300:] if stderr else 'no output'}",
                "action": action_name,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": f"G1 arm action timed out (30s): {action_name}",
                "action": action_name,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error executing G1 arm action: {e}",
            }

    @staticmethod
    def get_g1_loco_modes() -> Dict[str, Any]:
        """Available G1 loco modes (FSM helpers)."""
        return {
            "success": True,
            "modes": [
                {"id": "start", "name": "Start (FSM 200)"},
                {"id": "damp", "name": "Damp (FSM 1)"},
                {"id": "zero_torque", "name": "ZeroTorque (FSM 0)"},
                {"id": "sit", "name": "Sit (FSM 3)"},
                {"id": "lie_to_stand", "name": "Lie2StandUp (FSM 702)"},
                {"id": "squat_to_stand", "name": "Squat2StandUp (FSM 706)"},
                {"id": "high_stand", "name": "HighStand"},
                {"id": "low_stand", "name": "LowStand"},
                {"id": "stop_move", "name": "StopMove"},
                {"id": "wave_hand", "name": "WaveHand (task)"},
                {"id": "shake_hand", "name": "ShakeHand (task)"},
            ],
        }

    @staticmethod
    def execute_g1_loco_mode(mode: str, extra_args: Optional[list] = None) -> Dict[str, Any]:
        """
        Execute Unitree G1 loco mode via SDK in a subprocess.
        This avoids native DDS crashes in the main service process.
        """
        import subprocess
        import json as _json

        robot_type = RobotAPI._get_robot_type()
        if robot_type != "G1":
            return {"success": False, "message": f"G1 loco modes are available only for RobotType=G1 (current: {robot_type or 'UNKNOWN'})"}

        network_interface = "eth0"
        domain_id = 0
        try:
            import services_manager
            manager = services_manager.get_services_manager()
            params = manager.get_service_parameters("unitree_motor_control")
            network_interface = params.get("network", "eth0")
            domain_id = int(params.get("id", 0))
        except Exception:
            pass

        mode = str(mode).strip().lower()
        rest = list(extra_args or [])

        try:
            script_path = PROJECT_ROOT / "api" / "g1_loco_cli.py"
            payload = {"mode": mode, "args": rest}
            proc = subprocess.run(
                [sys.executable, str(script_path), str(PROJECT_ROOT), network_interface, str(domain_id), "mode", _json.dumps(payload)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = proc.stdout.strip()
            if stdout:
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        return _json.loads(line)
            stderr = proc.stderr.strip()
            return {"success": False, "message": f"G1 loco subprocess failed (rc={proc.returncode}): {stderr[-300:] if stderr else 'no output'}", "mode": mode}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"G1 loco timed out (20s): {mode}", "mode": mode}
        except Exception as e:
            return {"success": False, "message": f"Error executing G1 loco mode: {e}", "mode": mode}

    @staticmethod
    def execute_g1_loco_op(op: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Generic loco op executor via api/g1_loco_cli.py (subprocess)."""
        import subprocess
        import json as _json

        robot_type = RobotAPI._get_robot_type()
        if robot_type != "G1":
            return {"success": False, "message": f"G1 loco is available only for RobotType=G1 (current: {robot_type or 'UNKNOWN'})"}

        network_interface = "eth0"
        domain_id = 0
        try:
            import services_manager
            manager = services_manager.get_services_manager()
            params = manager.get_service_parameters("unitree_motor_control")
            network_interface = params.get("network", "eth0")
            domain_id = int(params.get("id", 0))
        except Exception:
            pass

        op = str(op or "").strip().lower()
        script_path = PROJECT_ROOT / "api" / "g1_loco_cli.py"

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path), str(PROJECT_ROOT), network_interface, str(domain_id), op, _json.dumps(payload or {})],
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = proc.stdout.strip()
            if stdout:
                for line in reversed(stdout.splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        return _json.loads(line)
            stderr = proc.stderr.strip()
            return {"success": False, "message": f"G1 loco subprocess failed (rc={proc.returncode}): {stderr[-300:] if stderr else 'no output'}", "op": op}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"G1 loco timed out (20s): {op}", "op": op}
        except Exception as e:
            return {"success": False, "message": f"Error executing G1 loco op: {e}", "op": op}
    
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
            # G1 loco (FSM/modes) helpers (used in default control layouts)
            {
                "id": "g1_loco_start",
                "name": "G1: START (FSM 200)",
                "description": "G1 high-level mode: Start",
                "command": "g1_loco",
                "args": ["start"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_damp",
                "name": "G1: DAMP (FSM 1)",
                "description": "G1 high-level mode: Damp",
                "command": "g1_loco",
                "args": ["damp"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_zero_torque",
                "name": "G1: ZERO TORQUE (FSM 0)",
                "description": "G1 high-level mode: ZeroTorque",
                "command": "g1_loco",
                "args": ["zero_torque"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_sit",
                "name": "G1: SIT (FSM 3)",
                "description": "G1 high-level mode: Sit",
                "command": "g1_loco",
                "args": ["sit"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_lie_to_stand",
                "name": "G1: LIE→STAND (FSM 702)",
                "description": "G1 high-level mode: Lie2StandUp",
                "command": "g1_loco",
                "args": ["lie_to_stand"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_squat_to_stand",
                "name": "G1: SQUAT→STAND (FSM 706)",
                "description": "G1 high-level mode: Squat2StandUp",
                "command": "g1_loco",
                "args": ["squat_to_stand"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_high_stand",
                "name": "G1: HIGH STAND",
                "description": "G1 high-level mode: HighStand",
                "command": "g1_loco",
                "args": ["high_stand"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_low_stand",
                "name": "G1: LOW STAND",
                "description": "G1 high-level mode: LowStand",
                "command": "g1_loco",
                "args": ["low_stand"],
                "showButton": False,
                "robotTypes": ["G1"],
            },
            {
                "id": "g1_loco_stop_move",
                "name": "G1: STOP MOVE",
                "description": "G1 high-level mode: StopMove",
                "command": "g1_loco",
                "args": ["stop_move"],
                "showButton": False,
                "robotTypes": ["G1"],
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
    def ensure_default_control_layouts() -> None:
        """Create data/control_layouts.json with 2 base layouts if missing."""
        try:
            layouts_path = PROJECT_ROOT / "data" / "control_layouts.json"
            layouts_path.parent.mkdir(parents=True, exist_ok=True)
            if layouts_path.exists():
                return

            def mk_btn(btn_id: str, command_id: str, label: str, icon: str, x: float, y: float, shape: str = "circle", color: str = "#2196f3"):
                step_id = f"step-{btn_id}"
                return {
                    "id": btn_id,
                    "commandId": command_id,
                    "label": label,
                    "icon": icon,
                    "shape": shape,
                    "color": color,
                    "x": round(float(x), 5),
                    "y": round(float(y), 5),
                    "size": 64,
                    "targetIps": ["LOCAL"],
                    "program": [
                        {
                            "type": "command",
                            "id": step_id,
                            "commandId": command_id,
                            "delayBeforeMs": 0,
                            "delayAfterMs": 0,
                            "actionDurationMs": 0,
                            "targetIps": ["LOCAL"],
                            "waitContinue": False,
                            "useGo": False,
                        }
                    ],
                }

            # Place buttons around the edge of the "phone" area (0..1 coords).
            # Movements (arm gestures)
            move_cmds = [
                ("g1_hug", "HUG", "mv_hug_1"),
                ("g1_high_wave", "WAVE", "mv_wave_1"),
                ("g1_face_wave", "FACE", "mv_wave_2"),
                ("g1_shake_hand", "SHAKE", "mv_wave_3"),
                ("g1_high_five", "FIVE", "mv_wave_4"),
                ("g1_clap", "CLAP", "mv_dance_1"),
                ("g1_heart", "HEART", "mv_hug_2"),
                ("g1_right_heart", "R-HEART", "mv_hug_3"),
                ("g1_hands_up", "HANDS UP", "mv_jump_1"),
                ("g1_reject", "REJECT", "mv_stop_1"),
                ("g1_left_kiss", "L-KISS", "mv_hug_4"),
                ("g1_right_kiss", "R-KISS", "mv_hug_5"),
            ]

            # Modes (loco)
            mode_cmds = [
                ("g1_loco_start", "START", "mv_run_1"),
                ("g1_loco_damp", "DAMP", "mv_stop_1"),
                ("g1_loco_zero_torque", "0 TORQ", "mv_stop_2"),
                ("g1_loco_sit", "SIT", "mv_sit_1"),
                ("g1_loco_lie_to_stand", "LIE→STAND", "mv_stand_1"),
                ("g1_loco_squat_to_stand", "SQUAT→STAND", "mv_stand_2"),
                ("g1_loco_high_stand", "HIGH", "mv_stand_3"),
                ("g1_loco_low_stand", "LOW", "mv_squat_1"),
                ("g1_loco_stop_move", "STOP", "mv_stop_3"),
            ]

            def edge_positions(n: int):
                # clockwise positions along border (top->right->bottom->left)
                pts = []
                if n <= 0:
                    return pts
                # allocate proportionally
                top = max(1, n // 4)
                right = max(1, n // 4)
                bottom = max(1, n // 4)
                left = max(1, n - top - right - bottom)

                def lin(a, b, k, m):
                    if m <= 1:
                        return (a + b) / 2
                    return a + (b - a) * (k / (m - 1))

                for i in range(top):
                    pts.append((lin(0.15, 0.85, i, top), 0.12))
                for i in range(right):
                    pts.append((0.88, lin(0.18, 0.82, i, right)))
                for i in range(bottom):
                    pts.append((lin(0.85, 0.15, i, bottom), 0.88))
                for i in range(left):
                    pts.append((0.12, lin(0.82, 0.18, i, left)))
                return pts[:n]

            move_pts = edge_positions(len(move_cmds))
            mode_pts = edge_positions(len(mode_cmds))

            movements_buttons = []
            for i, (cmd, lbl, ico) in enumerate(move_cmds):
                x, y = move_pts[i]
                movements_buttons.append(mk_btn(f"base-move-{cmd}", cmd, lbl, ico, x, y, shape="circle", color="#2196f3"))

            modes_buttons = []
            for i, (cmd, lbl, ico) in enumerate(mode_cmds):
                x, y = mode_pts[i]
                modes_buttons.append(mk_btn(f"base-mode-{cmd}", cmd, lbl, ico, x, y, shape="square", color="#9c27b0"))

            base = {
                "version": "1.0.0",
                "layouts": [
                    {"id": "layout-movements", "name": "Движения", "buttons": movements_buttons},
                    {"id": "layout-modes", "name": "Режимы", "buttons": modes_buttons},
                ],
            }

            with open(layouts_path, "w", encoding="utf-8") as f:
                json.dump(base, f, indent=2, ensure_ascii=False)
        except Exception as e:
            try:
                print(f"[RobotAPI] ensure_default_control_layouts failed: {e}", flush=True)
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
            RobotAPI.ensure_default_control_layouts()
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

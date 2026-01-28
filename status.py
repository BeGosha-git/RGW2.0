"""
Модуль для получения статуса и параметров робота.
"""
import os
import json
import platform
import socket
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Определяем корень проекта (папка с main.py)
PROJECT_ROOT = Path(__file__).parent.absolute()


def get_robot_status() -> Dict[str, Any]:
    """
    Возвращает все параметры робота.
    
    Returns:
        Словарь с параметрами робота
    """
    status_data = {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "robot": {},
        "system": {},
        "version": {},
        "settings": {},
        "network": {}
    }
    
    # Параметры робота из settings.json
    try:
        settings_path = PROJECT_ROOT / "data" / "settings.json"
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                status_data["robot"] = {
                    "robot_type": settings.get("RobotType", "UNKNOWN"),
                    "robot_id": settings.get("RobotID", "UNKNOWN"),
                    "robot_group": settings.get("RobotGroup", "UNKNOWN"),
                    "version_priority": settings.get("VersionPriority", "UNKNOWN")
                }
                status_data["settings"] = settings
        else:
            # Файл не найден - добавляем отладочную информацию
            status_data["robot"]["error"] = f"Settings file not found"
            status_data["robot"]["debug"] = {
                "project_root": str(PROJECT_ROOT),
                "settings_path": str(settings_path),
                "cwd": str(Path.cwd())
            }
    except Exception as e:
        status_data["robot"]["error"] = str(e)
        status_data["robot"]["debug"] = {
            "project_root": str(PROJECT_ROOT),
            "settings_path": str(PROJECT_ROOT / "data" / "settings.json")
        }
    
    # Системная информация
    try:
        status_data["system"] = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "hostname": socket.gethostname(),
            "python_version": platform.python_version()
        }
    except Exception as e:
        status_data["system"]["error"] = str(e)
    
    # Информация о версии
    try:
        version_path = PROJECT_ROOT / "data" / "version.json"
        if version_path.exists():
            with open(version_path, 'r', encoding='utf-8') as f:
                version_data = json.load(f)
                status_data["version"] = {
                    "version": version_data.get("version", "UNKNOWN"),
                    "files_count": len(version_data.get("files", []))
                }
    except Exception as e:
        status_data["version"]["error"] = str(e)
    
    # Сетевая информация
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        status_data["network"] = {
            "hostname": hostname,
            "local_ip": local_ip
        }
        
        # Пытаемся получить внешний IP (может не работать без интернета)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            status_data["network"]["interface_ip"] = s.getsockname()[0]
            s.close()
        except Exception:
            pass
            
    except Exception as e:
        status_data["network"]["error"] = str(e)
    
    return status_data


def get_robot_info() -> Dict[str, Any]:
    """
    Возвращает краткую информацию о роботе.
    
    Returns:
        Краткая информация о роботе
    """
    status_data = get_robot_status()
    
    return {
        "robot_id": status_data.get("robot", {}).get("robot_id", "UNKNOWN"),
        "robot_type": status_data.get("robot", {}).get("robot_type", "UNKNOWN"),
        "robot_group": status_data.get("robot", {}).get("robot_group", "UNKNOWN"),
        "version": status_data.get("version", {}).get("version", "UNKNOWN"),
        "hostname": status_data.get("system", {}).get("hostname", "UNKNOWN"),
        "local_ip": status_data.get("network", {}).get("local_ip", "UNKNOWN")
    }


if __name__ == '__main__':
    import json
    status = get_robot_status()
    print(json.dumps(status, indent=4, ensure_ascii=False))

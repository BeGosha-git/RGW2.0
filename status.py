"""
Модуль для получения статуса и параметров робота.
Поддерживает динамическую регистрацию данных от сервисов.
"""
import os
import json
import platform
import socket
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Определяем корень проекта (папка с main.py)
PROJECT_ROOT = Path(__file__).parent.absolute()

# Глобальный реестр данных от сервисов
_service_data_registry: Dict[str, Dict[str, Any]] = {}


def register_service_data(service_name: str, data: Dict[str, Any]) -> None:
    """
    Регистрирует данные от сервиса.
    
    Args:
        service_name: Имя сервиса
        data: Данные для регистрации (словарь)
    """
    global _service_data_registry
    _service_data_registry[service_name] = {
        **data,
        "last_update": datetime.now().isoformat()
    }


def unregister_service_data(service_name: str) -> None:
    """
    Удаляет данные сервиса из реестра.
    
    Args:
        service_name: Имя сервиса
    """
    global _service_data_registry
    if service_name in _service_data_registry:
        del _service_data_registry[service_name]


def get_service_data(service_name: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные конкретного сервиса.
    
    Args:
        service_name: Имя сервиса
    
    Returns:
        Данные сервиса или None если не найдены
    """
    global _service_data_registry
    return _service_data_registry.get(service_name)


def get_all_service_data() -> Dict[str, Dict[str, Any]]:
    """
    Получает все зарегистрированные данные от сервисов.
    
    Returns:
        Словарь с данными всех сервисов
    """
    global _service_data_registry
    return _service_data_registry.copy()


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
        "network": {},
        "services": get_all_service_data()
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
                    "version_type": version_data.get("version_type", "STABLE"),
                    "files_count": len(version_data.get("files", []))
                }
    except Exception as e:
        status_data["version"]["error"] = str(e)
    
    # Сетевая информация
    try:
        hostname = socket.gethostname()
        
        # Получаем реальный локальный IP через подключение к внешнему адресу
        local_ip = None
        interface_ip = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            interface_ip = s.getsockname()[0]
            s.close()
            local_ip = interface_ip
        except Exception:
            pass
        
        # Если не удалось получить через внешнее подключение, пробуем через hostname
        if not local_ip:
            try:
                local_ip = socket.gethostbyname(hostname)
                # Проверяем, что это не localhost
                if local_ip in ["127.0.0.1", "127.0.1.1", "::1"]:
                    local_ip = None
            except Exception:
                pass
        
        # Если все еще нет IP, пробуем через сетевые интерфейсы (опционально)
        if not local_ip:
            try:
                import netifaces
                for interface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get('addr')
                            if ip and not ip.startswith('127.'):
                                local_ip = ip
                                break
                    if local_ip:
                        break
            except ImportError:
                # netifaces не установлен - это нормально
                pass
            except Exception:
                pass
        
        status_data["network"] = {
            "hostname": hostname,
            "local_ip": local_ip or "UNKNOWN",
            "interface_ip": interface_ip or local_ip or "UNKNOWN"
        }
            
    except Exception as e:
        status_data["network"]["error"] = str(e)
        status_data["network"] = {
            "hostname": socket.gethostname() if 'socket' in dir() else "UNKNOWN",
            "local_ip": "UNKNOWN",
            "interface_ip": "UNKNOWN"
        }
    
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

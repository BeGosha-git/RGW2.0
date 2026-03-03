"""
Модуль для управления сервисами через services.json.
Управляет статусами сервисов (ON/OFF/SLEEP) и их параметрами.
"""
import os
import json
import platform
import ast
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime


SERVICES_FILE = Path("data") / "services.json"


class ServicesManager:
    """Класс для управления сервисами."""
    
    def __init__(self):
        """Инициализация менеджера сервисов."""
        self.services_file = SERVICES_FILE
        self.ensure_data_dir()
        self.load_services()
    
    def ensure_data_dir(self):
        """Создает директорию data если её нет."""
        self.services_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_services(self) -> Dict[str, Any]:
        """
        Загружает services.json и обновляет старые записи до нового формата.
        
        Returns:
            Словарь с данными о сервисах
        """
        if not self.services_file.exists():
            return {
                "last_update": datetime.now().isoformat(),
                "services": {}
            }
        
        try:
            with open(self.services_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            services = data.get("services", {})
            updated = False
            
            for service_name, service_data in services.items():
                defaults = self.get_service_defaults(service_name)
                
                if "defaults" not in service_data:
                    service_data["defaults"] = defaults.copy()
                    updated = True
                else:
                    for key, value in defaults.items():
                        if key not in service_data["defaults"]:
                            service_data["defaults"][key] = value
                            updated = True
                
                if "parameters" not in service_data:
                    service_data["parameters"] = {}
                    updated = True
                
                if "enabled" not in service_data["parameters"]:
                    service_data["parameters"]["enabled"] = defaults.get("enabled", True)
                    updated = True
                
                if "enabled" not in service_data["defaults"]:
                    service_data["defaults"]["enabled"] = defaults.get("enabled", True)
                    updated = True
                
                enabled = service_data["parameters"].get("enabled", defaults.get("enabled", True))
                
                if "status" not in service_data:
                    expected_status = "ON" if enabled else "OFF"
                    service_data["status"] = expected_status
                    updated = True
                
                if "created_at" not in service_data:
                    service_data["created_at"] = datetime.now().isoformat()
                    updated = True
                
                for key, value in defaults.items():
                    if key not in ["status", "enabled"] and key not in service_data["parameters"]:
                        service_data["parameters"][key] = value
                        updated = True
            
            if updated:
                data["services"] = services
                self.save_services(data)
                print(f"[ServicesManager] Updated services.json to new format", flush=True)
            
            # Убеждаемся, что data не None и имеет правильную структуру
            if data is None or not isinstance(data, dict):
                data = {
                    "last_update": datetime.now().isoformat(),
                    "services": {}
                }
            
            # Убеждаемся, что есть ключ "services"
            if "services" not in data:
                data["services"] = {}
            
            return data
        except Exception as e:
            print(f"[ServicesManager] Error loading services.json: {e}", flush=True)
            return {
                "last_update": datetime.now().isoformat(),
                "services": {}
            }
    
    def save_services(self, data: Dict[str, Any]):
        """
        Сохраняет services.json.
        
        Args:
            data: Данные для сохранения
        """
        try:
            data["last_update"] = datetime.now().isoformat()
            with open(self.services_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ServicesManager] Error saving services.json: {str(e)}", flush=True)
    
    def get_service_defaults(self, service_name: str) -> Dict[str, Any]:
        """
        Возвращает дефолтные настройки для сервиса.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Дефолтные настройки
        """
        import platform
        
        defaults = {
            "scanner_service": {
                "status": "ON",
                "enabled": True,
                "scan_interval": 20,
                "network_range": "0-255",
                "port": 8080,
                "dependencies": []
            },
            "web": {
                "status": "ON",
                "enabled": True,
                "port": 8080,
                "api_port": 5000,
                "build_path": "services/web/build",
                "dependencies": ["api"]
            },
            "docker_service": {
                "status": "SLEEP",
                "enabled": platform.system() == "Windows",
                "check_windows": True,
                "prevent_restart": True,
                "dependencies": []
            },
            "remote_desktop": {
                "status": "ON",
                "enabled": True,
                "server_host": "localhost",
                "server_port": 9009,
                "pc_name": "",
                "wake_password": "1055",
                "dependencies": []
            },
            "unitree_motor_control": {
                "status": "OFF",
                "enabled": False,
                "id": 1,
                "network": "lo",
                "dependencies": []
            },
            "api": {
                "status": "ON",
                "enabled": True,
                "port": 5000,
                "dependencies": []
            }
        }
        
        defaults_result = defaults.get(service_name, {
            "status": "ON",
            "enabled": True,
            "dependencies": []
        })
        
        return defaults_result
    
    def get_service(self, service_name: str) -> Dict[str, Any]:
        """
        Получает информацию о сервисе.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Информация о сервисе
        """
        data = self.load_services()
        if data is None or not isinstance(data, dict):
            data = {
                "last_update": datetime.now().isoformat(),
                "services": {}
            }
        services = data.get("services", {})
        if not isinstance(services, dict):
            services = {}
        
        if service_name not in services:
            # Создаем дефолтные настройки
            defaults = self.get_service_defaults(service_name)
            enabled = defaults.get("enabled", True)
            status = "ON" if enabled else "OFF"
            
            parameters = defaults.get("parameters", defaults)
            if "enabled" not in parameters:
                parameters["enabled"] = enabled
            
            services[service_name] = {
                "status": status,
                "parameters": parameters,
                "defaults": defaults,
                "created_at": datetime.now().isoformat()
            }
            data["services"] = services
            self.save_services(data)
        
        return services.get(service_name, {})
    
    def update_service_status(self, service_name: str, status: str) -> bool:
        """
        Обновляет программный статус сервиса (ON/OFF/SLEEP).
        Используется программно для управления состоянием работы сервиса.
        
        Args:
            service_name: Имя сервиса
            status: Новый статус (ON/OFF/SLEEP)
            
        Returns:
            True если успешно
        """
        if status not in ["ON", "OFF", "SLEEP"]:
            return False
        
        data = self.load_services()
        services = data.get("services", {})
        
        if service_name not in services:
            self.get_service(service_name)  # Создаем если нет
            data = self.load_services()
            services = data.get("services", {})
        
        services[service_name]["status"] = status
        services[service_name]["last_status_change"] = datetime.now().isoformat()
        
        data["services"] = services
        self.save_services(data)
        return True
    
    def update_service_enabled(self, service_name: str, enabled: bool) -> bool:
        """
        Обновляет ручной статус запуска сервиса (enabled).
        Используется для ручного управления запуском сервиса через веб-интерфейс.
        
        Args:
            service_name: Имя сервиса
            enabled: Включен ли сервис для запуска (True/False)
            
        Returns:
            True если успешно
        """
        data = self.load_services()
        services = data.get("services", {})
        
        if service_name not in services:
            self.get_service(service_name)  # Создаем если нет
            data = self.load_services()
            services = data.get("services", {})
        
        if "parameters" not in services[service_name]:
            services[service_name]["parameters"] = {}
        
        services[service_name]["parameters"]["enabled"] = bool(enabled)
        services[service_name]["last_enabled_change"] = datetime.now().isoformat()
        
        expected_status = "ON" if enabled else "OFF"
        if services[service_name].get("status") != expected_status:
            services[service_name]["status"] = expected_status
        
        data["services"] = services
        self.save_services(data)
        return True
    
    def update_service_parameter(self, service_name: str, parameter: str, value: Any) -> bool:
        """
        Обновляет параметр сервиса.
        
        Args:
            service_name: Имя сервиса
            parameter: Имя параметра
            value: Значение параметра
            
        Returns:
            True если успешно
        """
        data = self.load_services()
        services = data.get("services", {})
        
        if service_name not in services:
            self.get_service(service_name)  # Создаем если нет
            data = self.load_services()
            services = data.get("services", {})
        
        if "parameters" not in services[service_name]:
            services[service_name]["parameters"] = {}
        
        services[service_name]["parameters"][parameter] = value
        services[service_name]["last_parameter_change"] = datetime.now().isoformat()
        
        data["services"] = services
        self.save_services(data)
        return True
    
    def reset_service_parameter(self, service_name: str, parameter: str) -> bool:
        """
        Сбрасывает параметр сервиса к дефолтному значению.
        
        Args:
            service_name: Имя сервиса
            parameter: Имя параметра
            
        Returns:
            True если успешно
        """
        data = self.load_services()
        services = data.get("services", {})
        
        if service_name not in services:
            return False
        
        defaults = services[service_name].get("defaults", {})
        default_value = defaults.get(parameter)
        
        if default_value is None:
            # Если нет в defaults, удаляем параметр
            if "parameters" in services[service_name]:
                services[service_name]["parameters"].pop(parameter, None)
        else:
            # Устанавливаем дефолтное значение
            if "parameters" not in services[service_name]:
                services[service_name]["parameters"] = {}
            services[service_name]["parameters"][parameter] = default_value
        
        services[service_name]["last_parameter_change"] = datetime.now().isoformat()
        
        data["services"] = services
        self.save_services(data)
        return True
    
    def get_all_services(self) -> Dict[str, Any]:
        """
        Получает все сервисы.
        
        Returns:
            Словарь со всеми сервисами
        """
        data = self.load_services()
        return data.get("services", {})
    
    def _file_imports_services_manager(self, filepath: Path) -> bool:
        """
        Проверяет, импортирует ли файл services_manager.
        
        Args:
            filepath: Путь к файлу для проверки
        
        Returns:
            True если файл импортирует services_manager
        """
        try:
            if not filepath.exists():
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим AST для анализа импортов
            tree = ast.parse(content, filename=str(filepath))
            
            # Проверяем импорты
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # import services_manager или import services_manager as ...
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]  # Берем только первый уровень
                        if module_name == 'services_manager':
                            return True
                elif isinstance(node, ast.ImportFrom):
                    # from services_manager import ... или from services import manager
                    if node.module:
                        module_name = node.module.split('.')[0]  # Берем только первый уровень
                        if module_name == 'services_manager':
                            return True
                        # Проверяем импорты вида "from services import manager"
                        if module_name == 'services' and node.names:
                            for alias in node.names:
                                if 'manager' in alias.name.lower():
                                    return True
            
            return False
        except Exception:
            # Если не удалось проанализировать, считаем что не импортирует
            return False
    
    def discover_services(self) -> List[str]:
        """
        Обнаруживает доступные сервисы.
        Сервисом считается только файл, который импортирует services_manager.
        
        Returns:
            Список имен сервисов
        """
        services = []
        services_dir = Path("services")
        
        if services_dir.exists():
            for item in services_dir.iterdir():
                if item.is_file() and item.suffix == '.py' and item.stem != '__init__':
                    # Пропускаем служебные файлы, которые не являются сервисами
                    if item.stem == 'init_settings':
                        continue
                    # Проверяем, импортирует ли файл services_manager
                    if self._file_imports_services_manager(item):
                        services.append(item.stem)
                elif item.is_dir():
                    # Пропускаем служебные папки
                    if item.name == "windows_docker":
                        # windows_docker - служебная папка, проверяем только docker_service.py
                        docker_service_file = item / "docker_service.py"
                        if docker_service_file.exists():
                            # docker_service всегда считается сервисом (специальный случай)
                            services.append("docker_service")
                        continue
                    
                    # Проверяем есть ли main.py или файл с именем папки в директории
                    main_file = item / "main.py"
                    service_file = item / f"{item.name}.py"
                    
                    # Проверяем main.py
                    if main_file.exists():
                        # Для main.py проверяем, импортирует ли он services_manager напрямую
                        if self._file_imports_services_manager(main_file):
                            services.append(item.name)
                        else:
                            # Если main.py не импортирует напрямую, проверяем импортируемый модуль
                            # Например, main.py может импортировать unitree_motor_control, который импортирует services_manager
                            try:
                                with open(main_file, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                # Ищем импорты из текущей директории
                                tree = ast.parse(content, filename=str(main_file))
                                for node in ast.walk(tree):
                                    if isinstance(node, ast.ImportFrom):
                                        if node.module:
                                            module_parts = node.module.split('.')
                                            # Проверяем импорты вида: services.unitree_motor_control.unitree_motor_control
                                            if (len(module_parts) >= 2 and 
                                                module_parts[0] == 'services' and 
                                                module_parts[1] == item.name):
                                                # Берем последнюю часть как имя модуля
                                                imported_module = module_parts[-1]
                                                module_file = item / f"{imported_module}.py"
                                                if module_file.exists() and self._file_imports_services_manager(module_file):
                                                    services.append(item.name)
                                                    break
                            except Exception:
                                pass
                    # Проверяем файл с именем папки (например, web/web.py)
                    elif service_file.exists():
                        # Проверяем, импортирует ли файл services_manager
                        if self._file_imports_services_manager(service_file):
                            services.append(item.name)
        
        # Добавляем системные сервисы
        services.append("api")
        
        return services
    
    def refresh_services(self):
        """
        Обновляет список сервисов, добавляя новые если их нет и удаляя несуществующие.
        """
        data = self.load_services()
        services = data.get("services", {})
        
        discovered = self.discover_services()
        discovered_set = set(discovered)
        new_services_count = 0
        removed_services_count = 0
        
        # Добавляем новые сервисы
        for service_name in discovered:
            if service_name not in services:
                defaults = self.get_service_defaults(service_name)
                enabled = defaults.get("enabled", True)
                status = "ON" if enabled else "OFF"
                
                services[service_name] = {
                    "status": status,
                    "parameters": defaults.get("parameters", defaults),
                    "defaults": defaults,
                    "created_at": datetime.now().isoformat()
                }
                
                if "parameters" not in services[service_name]:
                    services[service_name]["parameters"] = {}
                services[service_name]["parameters"]["enabled"] = enabled
                
                new_services_count += 1
                print(f"[ServicesManager] Added new service: {service_name} (enabled={enabled}, status={status})", flush=True)
        
        # Удаляем несуществующие сервисы (кроме системных)
        services_to_remove = []
        for service_name in list(services.keys()):
            if service_name not in discovered_set and service_name != "api":
                services_to_remove.append(service_name)
        
        for service_name in services_to_remove:
            del services[service_name]
            removed_services_count += 1
            print(f"[ServicesManager] Removed non-existent service: {service_name}", flush=True)
        
        # Всегда обновляем last_update, даже если новых сервисов нет
        # Это показывает, что проверка была выполнена
        data["services"] = services
        self.save_services(data)
        
        if new_services_count > 0:
            print(f"[ServicesManager] Found {new_services_count} new service(s). services.json updated.", flush=True)
        else:
            print(f"[ServicesManager] Service check completed. No new services found. Total: {len(services)}", flush=True)
    
    def is_service_enabled(self, service_name: str) -> bool:
        """
        Проверяет, должен ли сервис быть запущен (ручное управление через enabled).
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            True если сервис включен для запуска (enabled=True)
        """
        service = self.get_service(service_name)
        defaults = service.get("defaults", {})
        parameters = service.get("parameters", {})
        
        enabled = parameters.get("enabled", defaults.get("enabled", True))
        return bool(enabled)
    
    def get_service_parameters(self, service_name: str) -> Dict[str, Any]:
        """
        Получает параметры сервиса (с учетом defaults).
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Словарь параметров
        """
        service = self.get_service(service_name)
        defaults = service.get("defaults", {})
        parameters = service.get("parameters", {})
        
        # Объединяем defaults и parameters (parameters имеют приоритет)
        result = {**defaults, **parameters}
        return result
    
    def get_service_dependencies(self, service_name: str) -> List[str]:
        """
        Получает список зависимостей сервиса.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Список имен сервисов, от которых зависит данный сервис
        """
        service = self.get_service(service_name)
        defaults = service.get("defaults", {})
        parameters = service.get("parameters", {})
        
        # Зависимости могут быть в defaults или parameters
        dependencies = parameters.get("dependencies", defaults.get("dependencies", []))
        
        # Фильтруем service_manager из зависимостей
        return [dep for dep in dependencies if dep != "services_manager"]
    
    def get_services_depending_on(self, service_name: str) -> List[str]:
        """
        Получает список сервисов, которые зависят от данного сервиса.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Список имен сервисов, зависящих от данного
        """
        depending_services = []
        all_services = self.get_all_services()
        
        for other_service_name, other_service_data in all_services.items():
            if other_service_name == service_name:
                continue
            
            other_defaults = other_service_data.get("defaults", {})
            other_parameters = other_service_data.get("parameters", {})
            other_dependencies = other_parameters.get("dependencies", other_defaults.get("dependencies", []))
            
            if service_name in other_dependencies:
                depending_services.append(other_service_name)
        
        return depending_services
    
    def can_disable_service(self, service_name: str) -> Tuple[bool, List[str]]:
        """
        Проверяет, можно ли выключить сервис.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Кортеж (можно_ли_выключить, список_зависимых_сервисов)
        """
        depending_services = self.get_services_depending_on(service_name)
        active_depending = [dep for dep in depending_services if self.get_service(dep).get("status") == "ON"]
        return (len(active_depending) == 0, active_depending)
    
    def disable_service_with_dependencies(self, service_name: str, visited: set = None) -> List[str]:
        """
        Выключает сервис и все зависящие от него сервисы каскадно.
        
        Args:
            service_name: Имя сервиса для выключения
            visited: Множество уже обработанных сервисов (для предотвращения циклов)
            
        Returns:
            Список выключенных сервисов в порядке выключения
        """
        if visited is None:
            visited = set()
        
        if service_name in visited:
            return []
        
        visited.add(service_name)
        disabled_services = []
        depending_services = self.get_services_depending_on(service_name)
        
        for dep_service in depending_services:
            dep_status = self.get_service(dep_service).get("status", "OFF")
            if dep_status == "ON":
                disabled_services.extend(self.disable_service_with_dependencies(dep_service, visited))
        
        if self.get_service(service_name).get("status", "OFF") == "ON":
            self.update_service_status(service_name, "OFF")
            disabled_services.append(service_name)
        
        return disabled_services
    
    def analyze_service_dependencies(self, filepath: str) -> List[str]:
        """
        Анализирует импорты в файле сервиса и определяет зависимости от других сервисов.
        
        Args:
            filepath: Путь к файлу сервиса
            
        Returns:
            Список имен сервисов, от которых зависит данный сервис
        """
        dependencies = []
        
        try:
            filepath_obj = Path(filepath)
            if not filepath_obj.exists():
                return dependencies
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсим AST для анализа импортов
            tree = ast.parse(content, filename=filepath)
            
            # Получаем список всех доступных сервисов
            all_services = self.discover_services()
            
            # Создаем маппинг: имя модуля -> имя сервиса
            # Для сервисов в папке services/ имя файла = имя сервиса
            service_mapping = {}
            services_dir = Path("services")
            if services_dir.exists():
                for item in services_dir.iterdir():
                    if item.is_file() and item.suffix == '.py' and item.stem != '__init__':
                        service_mapping[item.stem] = item.stem
                    elif item.is_dir():
                        # Пропускаем служебные папки
                        if item.name == "windows_docker":
                            # windows_docker - служебная папка, проверяем только docker_service.py
                            docker_service_file = item / "docker_service.py"
                            if docker_service_file.exists():
                                service_mapping["docker_service"] = "docker_service"
                            continue
                        
                        # Проверяем есть ли main.py или файл с именем папки в директории
                        main_file = item / "main.py"
                        service_file = item / f"{item.name}.py"
                        
                        if main_file.exists():
                            service_mapping[item.name] = item.name
                        elif service_file.exists():
                            service_mapping[item.name] = item.name
            
            # Добавляем системные сервисы
            service_mapping["api"] = "api"
            
            # Анализируем импорты
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # import module
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]  # Берем только первый уровень
                        # Проверяем, является ли это сервисом
                        if module_name in service_mapping:
                            service_name = service_mapping[module_name]
                            if service_name in all_services:
                                dependencies.append(service_name)
                elif isinstance(node, ast.ImportFrom):
                    # from module import ...
                    if node.module:
                        module_name = node.module.split('.')[0]  # Берем только первый уровень
                        # Проверяем, является ли это сервисом
                        if module_name in service_mapping:
                            service_name = service_mapping[module_name]
                            if service_name in all_services:
                                dependencies.append(service_name)
                        # Также проверяем импорты вида "import services.scanner" или "from services import scanner"
                        if module_name == "services" and node.names:
                            for alias in node.names:
                                service_name = alias.name.split('.')[0]
                                if service_name in all_services:
                                    dependencies.append(service_name)
            
            # Убираем дубликаты и сортируем
            dependencies = sorted(list(set(dependencies)))
            
            # Определяем имя текущего сервиса из пути
            # Для файлов в подпапках (например, services/web/web.py) берем имя папки
            if filepath_obj.parent.name == "services" or (filepath_obj.parent.parent.name == "services" if filepath_obj.parent.parent.exists() else False):
                # Специальный случай: docker_service.py в windows_docker
                if filepath_obj.name == "docker_service.py" and filepath_obj.parent.name == "windows_docker":
                    current_service_name = "docker_service"
                elif filepath_obj.parent.name != "services":
                    current_service_name = filepath_obj.parent.name  # services/web/web.py -> web
                else:
                    current_service_name = filepath_obj.stem  # services/scanner.py -> scanner
            else:
                current_service_name = filepath_obj.stem
            
            # Фильтруем services_manager и сам сервис
            dependencies = [dep for dep in dependencies if dep != "services_manager" and dep != current_service_name]
            
        except Exception as e:
            print(f"[ServicesManager] Error analyzing dependencies for {filepath}: {str(e)}", flush=True)
        
        return dependencies
    
    def update_service_dependencies_from_file(self, service_name: str, filepath: str) -> bool:
        """
        Обновляет зависимости сервиса на основе анализа его файла.
        
        Args:
            service_name: Имя сервиса
            filepath: Путь к файлу сервиса
            
        Returns:
            True если зависимости были обновлены
        """
        try:
            # Анализируем зависимости из файла
            detected_dependencies = self.analyze_service_dependencies(filepath)
            
            # Получаем текущие зависимости
            current_dependencies = self.get_service_dependencies(service_name)
            
            # Если зависимости изменились, обновляем
            if set(detected_dependencies) != set(current_dependencies):
                data = self.load_services()
                services = data.get("services", {})
                
                if service_name not in services:
                    self.get_service(service_name)  # Создаем если нет
                    data = self.load_services()
                    services = data.get("services", {})
                
                # Обновляем зависимости в parameters
                if "parameters" not in services[service_name]:
                    services[service_name]["parameters"] = {}
                
                services[service_name]["parameters"]["dependencies"] = detected_dependencies
                
                data["services"] = services
                self.save_services(data)
                
                print(f"[ServicesManager] Updated dependencies for {service_name}: {detected_dependencies}", flush=True)
                return True
            
            return False
        except Exception as e:
            print(f"[ServicesManager] Error updating dependencies for {service_name}: {str(e)}", flush=True)
            return False


# Глобальный экземпляр менеджера
_services_manager = None


def get_services_manager() -> ServicesManager:
    """
    Получает глобальный экземпляр менеджера сервисов.
    
    Returns:
        Экземпляр ServicesManager
    """
    global _services_manager
    if _services_manager is None:
        _services_manager = ServicesManager()
    return _services_manager


def get_api_port() -> int:
    """
    Получает порт API сервиса из конфигурации.
    
    Returns:
        Порт API (по умолчанию 5000)
    """
    try:
        manager = get_services_manager()
        params = manager.get_service_parameters("api")
        return params.get("port", 5000)
    except Exception:
        return 5000


def get_web_port() -> int:
    """
    Получает порт веб-сервиса из конфигурации.
    
    Returns:
        Порт веб-сервера (по умолчанию 8080)
    """
    try:
        manager = get_services_manager()
        params = manager.get_service_parameters("web")
        return params.get("port", 8080)
    except Exception:
        return 8080


def get_scanner_port() -> int:
    """
    Получает порт для сканирования сети из конфигурации.
    
    Returns:
        Порт для сканирования (по умолчанию 8080)
    """
    try:
        manager = get_services_manager()
        params = manager.get_service_parameters("scanner_service")
        return params.get("port", 8080)
    except Exception:
        return 8080

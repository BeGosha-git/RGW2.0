"""
Модуль для управления сервисами через services.json.
Управляет статусами сервисов (ON/OFF/SLEEP) и их параметрами.
"""
import os
import json
import platform
import ast
from pathlib import Path
from typing import Dict, Any, Optional, List
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
        Загружает services.json.
        
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
                return data
        except Exception as e:
            print(f"Error loading services.json: {str(e)}")
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
        defaults = {
            "scanner": {
                "status": "ON",
                "scan_interval": 20,
                "network_range": "0-255",
                "port": 80,
                "dependencies": []
            },
            "web": {
                "status": "ON",
                "port": 80,
                "api_port": 5000,
                "build_path": "services/web/build",
                "dependencies": []
            },
            "docker_service": {
                "status": "SLEEP",
                "check_windows": True,
                "prevent_restart": True,
                "dependencies": []
            }
        }
        
        return defaults.get(service_name, {
            "status": "ON",
            "enabled": True,
            "dependencies": []
        })
    
    def get_service(self, service_name: str) -> Dict[str, Any]:
        """
        Получает информацию о сервисе.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Информация о сервисе
        """
        data = self.load_services()
        services = data.get("services", {})
        
        if service_name not in services:
            # Создаем дефолтные настройки
            defaults = self.get_service_defaults(service_name)
            services[service_name] = {
                "status": defaults.get("status", "ON"),
                "parameters": defaults.get("parameters", defaults),
                "defaults": defaults,
                "created_at": datetime.now().isoformat()
            }
            data["services"] = services
            self.save_services(data)
        
        return services.get(service_name, {})
    
    def update_service_status(self, service_name: str, status: str) -> bool:
        """
        Обновляет статус сервиса.
        
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
    
    def discover_services(self) -> List[str]:
        """
        Обнаруживает доступные сервисы.
        
        Returns:
            Список имен сервисов
        """
        services = []
        services_dir = Path("services")
        
        if services_dir.exists():
            for item in services_dir.iterdir():
                if item.is_file() and item.suffix == '.py' and item.stem != '__init__':
                    services.append(item.stem)
                elif item.is_dir():
                    # Проверяем есть ли main файл в директории
                    main_file = item / "main.py"
                    if main_file.exists():
                        services.append(item.name)
                    # Проверяем есть ли docker_service.py в windows_docker
                    elif item.name == "windows_docker":
                        docker_service_file = item / "docker_service.py"
                        if docker_service_file.exists():
                            services.append("docker_service")
        
        # Добавляем системные сервисы
        services.append("api")
        
        return services
    
    def refresh_services(self):
        """
        Обновляет список сервисов, добавляя новые если их нет.
        """
        data = self.load_services()
        services = data.get("services", {})
        
        discovered = self.discover_services()
        new_services_count = 0
        
        for service_name in discovered:
            if service_name not in services:
                defaults = self.get_service_defaults(service_name)
                services[service_name] = {
                    "status": defaults.get("status", "ON"),
                    "parameters": defaults.get("parameters", defaults),
                    "defaults": defaults,
                    "created_at": datetime.now().isoformat()
                }
                new_services_count += 1
                print(f"[ServicesManager] Added new service: {service_name}", flush=True)
        
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
        Проверяет, включен ли сервис.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            True если сервис включен
        """
        service = self.get_service(service_name)
        status = service.get("status", "ON")
        return status == "ON"
    
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
    
    def can_disable_service(self, service_name: str) -> tuple[bool, List[str]]:
        """
        Проверяет, можно ли выключить сервис.
        
        Args:
            service_name: Имя сервиса
            
        Returns:
            Кортеж (можно_ли_выключить, список_зависимых_сервисов)
        """
        depending_services = self.get_services_depending_on(service_name)
        return (len(depending_services) == 0, depending_services)
    
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
                        # Проверяем есть ли main файл в директории
                        main_file = item / "main.py"
                        if main_file.exists():
                            service_mapping[item.name] = item.name
                        # Проверяем есть ли docker_service.py в windows_docker
                        elif item.name == "windows_docker":
                            docker_service_file = item / "docker_service.py"
                            if docker_service_file.exists():
                                service_mapping["docker_service"] = "docker_service"
            
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

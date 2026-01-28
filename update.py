"""
Модуль для обновления системы.
Использует API для получения актуальной версии и обновления файлов.
"""
import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import network
import api.network_api as network_api_module


def calculate_file_size(filepath: str) -> int:
    """
    Вычисляет размер файла или директории.
    
    Args:
        filepath: Путь к файлу или директории
        
    Returns:
        Размер в байтах
    """
    if not os.path.exists(filepath):
        return 0
    
    if os.path.isfile(filepath):
        return os.path.getsize(filepath)
    else:
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(filepath):
            for filename in filenames:
                filepath_full = os.path.join(dirpath, filename)
                if os.path.exists(filepath_full):
                    total_size += os.path.getsize(filepath_full)
        return total_size


def scan_project_files():
    """
    Сканирует файлы проекта и возвращает список файлов с их размерами.
    
    Returns:
        Список файлов с информацией о пути и размере
    """
    files_list = []
    
    # Сканируем все файлы в корне проекта (кроме служебных)
    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist', 'data'}
    exclude_files = {'data/version.json', 'data/settings.json', 'data/commands.json', 'data/services.json', 'data/ips.json', '.gitignore'}
    
    services_path = "services"
    
    for root, dirs, files in os.walk('.'):
        # Пропускаем папку services при обычном сканировании
        if root == '.' and services_path in dirs:
            dirs.remove(services_path)
        
        # Исключаем служебные директории (включая __pycache__ в любой папке)
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d != '__pycache__']
        
        # Пропускаем файлы в __pycache__ папках
        if '__pycache__' in root:
            continue
        
        # Пропускаем файлы внутри services/ при обычном сканировании
        if services_path in root and root != f'./{services_path}':
            continue
        
        for file in files:
            if file in exclude_files:
                continue
            
            filepath = os.path.join(root, file)
            # Пропускаем скрытые файлы
            if filepath.startswith('./.'):
                continue
            
            # Пропускаем файлы внутри services/ (обработаем отдельно)
            if services_path in filepath and root != f'./{services_path}':
                continue
            
            # Нормализуем путь
            normalized_path = filepath.replace('\\', '/').lstrip('./')
            
            file_size = calculate_file_size(filepath)
            files_list.append({
                "path": normalized_path,
                "size": file_size
            })
    
    # Для папки services обрабатываем только первый уровень:
    # - .py файлы в корне services/
    # - папки первого уровня (например, services/web/)
    if os.path.exists(services_path):
        # Обрабатываем .py файлы в корне services/
        if os.path.isdir(services_path):
            for item in os.listdir(services_path):
                # Пропускаем __pycache__
                if item == '__pycache__':
                    continue
                
                item_path = os.path.join(services_path, item)
                normalized_item_path = item_path.replace('\\', '/')
                
                # Если это .py файл - добавляем его
                if os.path.isfile(item_path) and item.endswith('.py'):
                    file_size = calculate_file_size(item_path)
                    files_list.append({
                        "path": normalized_item_path,
                        "size": file_size
                    })
                # Если это папка первого уровня - добавляем её с общим размером
                elif os.path.isdir(item_path):
                    dir_size = calculate_file_size(item_path)
                    files_list.append({
                        "path": normalized_item_path,
                        "size": dir_size,
                        "is_directory": True
                    })
    
    return files_list


def check_and_update_version():
    """
    Проверяет файлы проекта и обновляет версию в data/version.json если файлы изменились.
    
    Returns:
        True если версия была обновлена или не требовала обновления
    """
    try:
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        version_file = "data/version.json"
        
        # Читаем текущую версию если есть
        current_version = "1.00.01"
        current_files = []
        existing_version_type = "STABLE"
        
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    current_version = existing_data.get("version", "1.00.01")
                    current_files = existing_data.get("files", [])
                    existing_version_type = existing_data.get("version_type", "STABLE")
            except Exception as e:
                print(f"Warning: Could not read existing version file: {str(e)}", flush=True)
        
        # Сканируем текущие файлы
        files_list = scan_project_files()
        
        # Сортируем списки для сравнения
        current_files_sorted = sorted(current_files, key=lambda x: x.get("path", ""))
        files_list_sorted = sorted(files_list, key=lambda x: x.get("path", ""))
        
        # Сравниваем файлы
        files_changed = False
        
        # Проверяем количество файлов
        if len(current_files_sorted) != len(files_list_sorted):
            files_changed = True
        else:
            # Проверяем каждый файл
            for current_file, new_file in zip(current_files_sorted, files_list_sorted):
                if (current_file.get("path") != new_file.get("path") or 
                    current_file.get("size") != new_file.get("size")):
                    files_changed = True
                    break
        
        # Если файлы изменились, повышаем версию
        if files_changed:
            # Повышаем версию (увеличиваем последнюю цифру)
            version_parts = current_version.split('.')
            if len(version_parts) >= 3:
                try:
                    last_part = int(version_parts[2])
                    last_part += 1
                    version_parts[2] = str(last_part).zfill(2)
                    new_version = '.'.join(version_parts)
                except ValueError:
                    new_version = current_version
            else:
                new_version = current_version
            
            version_data = {
                "version": new_version,
                "version_type": existing_version_type,
                "files": files_list
            }
            
            # Сохраняем обновленный version.json
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, indent=4, ensure_ascii=False)
            
            print(f"Version updated: {current_version} -> {new_version} ({len(files_list)} files)", flush=True)
            return True
        else:
            print(f"Version check: No changes detected (version {current_version}, {len(files_list)} files)", flush=True)
            return True
            
    except Exception as e:
        print(f"Error checking/updating version: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def update_version_file():
    """
    Обновляет version.json с актуальным списком файлов и их размерами.
    Всегда обновляет список файлов, но не меняет версию.
    """
    try:
        version_data = {
            "version": "1.00.01",
            "version_type": "STABLE",
            "files": []
        }
        
        # Создаем папку data если её нет
        os.makedirs("data", exist_ok=True)
        
        # Читаем текущую версию если есть
        version_file = "data/version.json"
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                version_data["version"] = existing_data.get("version", "1.00.01")
                version_data["version_type"] = existing_data.get("version_type", "STABLE")
        
        files_list = scan_project_files()
        version_data["files"] = files_list
        
        # Сохраняем обновленный version.json
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=4, ensure_ascii=False)
        
        print(f"Version file updated: {len(files_list)} files/directories", flush=True)
        return True
        
    except Exception as e:
        print(f"Error updating version file: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def download_file_from_robot(source_ip: str, filepath: str, local_path: str) -> bool:
    """
    Скачивает файл с другого робота.
    
    Args:
        source_ip: IP адрес робота-источника
        filepath: Путь к файлу на роботе
        local_path: Локальный путь для сохранения
        
    Returns:
        True если успешно
    """
    try:
        client = network.NetworkClient()
        url = f"http://{source_ip}/api/files/download?path={filepath}"
        
        # Создаем директорию если нужно
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        return client.download_file(url, local_path)
    except Exception as e:
        print(f"Error downloading file {filepath} from {source_ip}: {str(e)}")
        return False


def update_files_from_robot(source_ip: str, files_to_update: list) -> bool:
    """
    Обновляет файлы с другого робота.
    
    Args:
        source_ip: IP адрес робота-источника
        files_to_update: Список файлов для обновления
        
    Returns:
        True если все файлы обновлены успешно
    """
    success = True
    
    for file_info in files_to_update:
        filepath = file_info.get("path")
        if not filepath:
            continue
        
        local_path = filepath
        
        print(f"Updating {filepath}...")
        
        if download_file_from_robot(source_ip, filepath, local_path):
            print(f"  ✓ {filepath} updated")
        else:
            print(f"  ✗ Failed to update {filepath}")
            success = False
    
    return success


def get_version_priority_from_settings() -> str:
    """
    Получает приоритет версии из settings.json.
    
    Returns:
        Приоритет версии: STABLE, BETA или ALPHA (по умолчанию STABLE)
    """
    try:
        settings_file = Path("data/settings.json")
        if settings_file.exists():
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return settings.get("VersionPriority", "STABLE")
    except Exception as e:
        print(f"Warning: Could not read VersionPriority from settings.json: {str(e)}", flush=True)
    return "STABLE"


def version_matches_priority(version_type: str, priority: str) -> bool:
    """
    Проверяет, соответствует ли тип версии приоритету.
    
    Args:
        version_type: Тип версии (STABLE, BETA, ALPHA)
        priority: Приоритет из settings (STABLE, BETA, ALPHA)
    
    Returns:
        True если версия соответствует приоритету
    """
    if priority == "STABLE":
        return version_type == "STABLE"
    elif priority == "BETA":
        return version_type in ["STABLE", "BETA"]
    elif priority == "ALPHA":
        return True  # ALPHA принимает все версии
    return False


def get_ips_from_file() -> List[str]:
    """
    Загружает IP адреса из ips.json.
    
    Returns:
        Список IP адресов
    """
    try:
        ips_file = Path("data/ips.json")
        if ips_file.exists():
            with open(ips_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("ips", [])
    except Exception as e:
        print(f"Warning: Could not read ips.json: {str(e)}", flush=True)
    return []


def find_best_version_by_priority(robot_ips: List[str], priority: str) -> Optional[Dict[str, Any]]:
    """
    Находит наивысшую версию среди роботов, соответствующую приоритету.
    
    Args:
        robot_ips: Список IP адресов роботов
        priority: Приоритет версии (STABLE, BETA, ALPHA)
    
    Returns:
        Словарь с информацией о версии и IP источника, или None
    """
    network_api = network_api_module.NetworkAPI()
    best_version = None
    best_version_info = None
    best_source_ip = None
    
    for ip in robot_ips:
        try:
            base_url = f"http://{ip}"
            robot_info = network_api.client.get_robot_info(base_url)
            
            if robot_info and robot_info.get("success"):
                version_data = robot_info.get("version", {})
                version_str = version_data.get("version", "0.00.00")
                version_type = version_data.get("version_type", "STABLE")
                
                # Проверяем соответствие приоритету
                if not version_matches_priority(version_type, priority):
                    print(f"Robot {ip} has version {version_str} ({version_type}), but priority is {priority}. Skipping.", flush=True)
                    continue
                
                # Сравниваем версии
                if best_version is None or network_api._compare_versions(version_str, best_version) > 0:
                    best_version = version_str
                    best_version_info = version_data
                    best_source_ip = ip
                    print(f"Found better version: {version_str} ({version_type}) from {ip}", flush=True)
        except Exception as e:
            print(f"Error checking robot {ip}: {str(e)}", flush=True)
            continue
    
    if best_version_info and best_source_ip:
        return {
            "success": True,
            "version": best_version_info,
            "source_ip": best_source_ip,
            "source_url": f"http://{best_source_ip}"
        }
    else:
        return None


def get_changed_services(files_to_update: List[Dict[str, Any]]) -> List[str]:
    """
    Определяет какие сервисы изменились на основе списка файлов.
    
    Args:
        files_to_update: Список файлов для обновления
    
    Returns:
        Список имен измененных сервисов
    """
    changed_services = set()
    
    for file_info in files_to_update:
        filepath = file_info.get("path", "")
        if not filepath:
            continue
        
        # Проверяем, относится ли файл к сервисам
        if filepath.startswith("services/"):
            # Извлекаем имя сервиса (первый уровень после services/)
            parts = filepath.split("/")
            if len(parts) >= 2:
                service_name = parts[1]
                # Если это директория (например, services/web/)
                if file_info.get("is_directory"):
                    changed_services.add(service_name)
                # Если это файл внутри директории сервиса (например, services/web/web.py)
                elif len(parts) > 2:
                    changed_services.add(service_name)
                # Если это .py файл в корне services/ (например, services/scanner.py)
                elif service_name.endswith(".py"):
                    changed_services.add(service_name[:-3])  # Убираем .py
    
    return list(changed_services)


def restart_service(service_name: str) -> bool:
    """
    Перезапускает сервис, создавая файл-флаг для перезапуска.
    
    Args:
        service_name: Имя сервиса для перезапуска
    
    Returns:
        True если успешно
    """
    try:
        # Создаем файл-флаг для перезапуска сервиса
        restart_flag_file = Path("data") / f".restart_{service_name}"
        restart_flag_file.parent.mkdir(parents=True, exist_ok=True)
        restart_flag_file.touch()
        
        print(f"Service {service_name} restart flag created. Service will be restarted by run.py", flush=True)
        return True
    except Exception as e:
        print(f"Error creating restart flag for service {service_name}: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def restart_project() -> None:
    """
    Перезапускает весь проект.
    В Docker контейнере это приведет к перезапуску контейнера.
    """
    print("Restarting project...", flush=True)
    import sys
    sys.exit(1)  # Выход с кодом ошибки для перезапуска контейнера


def update_system():
    """
    Основная функция обновления системы.
    Использует ips.json для поиска роботов, находит наивысшую версию,
    соответствующую приоритету, и обновляет файлы.
    Если изменены сервисы - перезапускает только их, иначе перезапускает проект.
    """
    print("Starting system update...", flush=True)
    
    # Обновляем локальный version.json
    print("Updating local version file...", flush=True)
    update_version_file()
    
    # Получаем приоритет версии из settings.json
    priority = get_version_priority_from_settings()
    print(f"Version priority: {priority}", flush=True)
    
    # Загружаем IP адреса из ips.json
    robot_ips = get_ips_from_file()
    if not robot_ips:
        print("No robot IPs found in ips.json. Skipping update.", flush=True)
        return True
    
    print(f"Found {len(robot_ips)} robot IP(s) in ips.json", flush=True)
    
    # Находим наивысшую версию, соответствующую приоритету
    print("Checking for updates from other robots...", flush=True)
    version_info = find_best_version_by_priority(robot_ips, priority)
    
    if not version_info or not version_info.get("success"):
        print("No updates available or no matching versions found.", flush=True)
        return True
    
    source_ip = version_info.get("source_ip")
    version_data = version_info.get("version", {})
    remote_version = version_data.get("version", "0.00.00")
    remote_version_type = version_data.get("version_type", "STABLE")
    
    # Читаем текущую версию
    current_version = "0.00.00"
    version_file = "data/version.json"
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            current_data = json.load(f)
            current_version = current_data.get("version", "0.00.00")
    
    print(f"Current version: {current_version}", flush=True)
    print(f"Latest matching version: {remote_version} ({remote_version_type}) from {source_ip}", flush=True)
    
    # Сравниваем версии
    network_api = network_api_module.NetworkAPI()
    if network_api._compare_versions(remote_version, current_version) <= 0:
        print("System is up to date.", flush=True)
        return True
    
    # Получаем список файлов для обновления
    files_to_update = version_data.get("files", [])
    
    if not files_to_update:
        print("No files to update.", flush=True)
        return True
    
    print(f"Updating {len(files_to_update)} files from {source_ip}...", flush=True)
    
    # Определяем какие сервисы изменились
    changed_services = get_changed_services(files_to_update)
    has_service_changes = len(changed_services) > 0
    
    # Определяем есть ли изменения вне services/
    has_non_service_changes = any(
        not file_info.get("path", "").startswith("services/")
        for file_info in files_to_update
    )
    
    print(f"Changed services: {changed_services if changed_services else 'none'}", flush=True)
    print(f"Has non-service changes: {has_non_service_changes}", flush=True)
    
    # Обновляем файлы
    success = update_files_from_robot(source_ip, files_to_update)
    
    if success:
        # Обновляем версию после успешного обновления
        version_file = "data/version.json"
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data_local = json.load(f)
                version_data_local["version"] = remote_version
                version_data_local["version_type"] = remote_version_type
                
                with open(version_file, 'w', encoding='utf-8') as f:
                    json.dump(version_data_local, f, indent=4, ensure_ascii=False)
        
        print("System update completed successfully!", flush=True)
        
        # Перезапускаем сервисы или проект
        if has_non_service_changes:
            # Если изменены файлы вне services - перезапускаем весь проект
            print("Non-service files changed. Restarting project...", flush=True)
            restart_project()
        elif has_service_changes:
            # Если изменены только сервисы - создаем флаги для перезапуска
            print(f"Changed services detected: {', '.join(changed_services)}", flush=True)
            print("Note: Services will be automatically reloaded by run.py when files change.", flush=True)
            # Создаем флаги для перезапуска (run.py может проверять их)
            for service_name in changed_services:
                restart_service(service_name)
        else:
            print("No restart needed.", flush=True)
    else:
        print("System update completed with errors.", flush=True)
    
    return success


if __name__ == '__main__':
    update_system()

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
    
    exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist', 'data'}
    exclude_files = {'data/version.json', 'data/settings.json', 'data/commands.json', 'data/services.json', 'data/ips.json', '.gitignore'}
    
    services_path = "services"
    
    for root, dirs, files in os.walk('.'):
        if root == '.' and services_path in dirs:
            dirs.remove(services_path)
        
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d != '__pycache__']
        
        if '__pycache__' in root:
            continue
        
        if services_path in root and root != f'./{services_path}':
            continue
        
        for file in files:
            if file in exclude_files:
                continue
            
            filepath = os.path.join(root, file)
            if filepath.startswith('./.'):
                continue
            
            if services_path in filepath and root != f'./{services_path}':
                continue
            
            normalized_path = filepath.replace('\\', '/').lstrip('./')
            
            file_size = calculate_file_size(filepath)
            files_list.append({
                "path": normalized_path,
                "size": file_size
            })
    
    if os.path.exists(services_path):
        if os.path.isdir(services_path):
            for item in os.listdir(services_path):
                if item == '__pycache__':
                    continue
                
                item_path = os.path.join(services_path, item)
                normalized_item_path = item_path.replace('\\', '/')
                
                if os.path.isfile(item_path) and item.endswith('.py'):
                    file_size = calculate_file_size(item_path)
                    files_list.append({
                        "path": normalized_item_path,
                        "size": file_size
                    })
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
        os.makedirs("data", exist_ok=True)
        
        version_file = "data/version.json"
        
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
            except Exception:
                pass
        
        files_list = scan_project_files()
        
        current_files_sorted = sorted(current_files, key=lambda x: x.get("path", ""))
        files_list_sorted = sorted(files_list, key=lambda x: x.get("path", ""))
        
        files_changed = False
        
        if len(current_files_sorted) != len(files_list_sorted):
            files_changed = True
        else:
            for current_file, new_file in zip(current_files_sorted, files_list_sorted):
                if (current_file.get("path") != new_file.get("path") or 
                    current_file.get("size") != new_file.get("size")):
                    files_changed = True
                    break
        
        if files_changed:
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
            
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, indent=4, ensure_ascii=False)
            
            return True
        else:
            return True
            
    except Exception:
        return False


def create_venv_archive() -> bool:
    """
    Создает архив venv для распространения на другие роботы.
    
    Returns:
        True если успешно
    """
    try:
        import tarfile
        
        venv_path = Path("venv")
        venv_archive = "venv.tar.gz"
        
        if not venv_path.exists():
            return False
        
        venv_ready_flag = venv_path / ".ready"
        if not venv_ready_flag.exists():
            return False
        
        with tarfile.open(venv_archive, 'w:gz') as tar:
            tar.add(venv_path, arcname='venv', filter=lambda tarinfo: None if '__pycache__' in tarinfo.name else tarinfo)
        
        return True
        
    except Exception:
        return False


def update_version_file():
    """
    Обновляет version.json с актуальным списком файлов и их размерами.
    Всегда обновляет список файлов, но не меняет версию.
    Также создает архив venv если он готов.
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
        
        # Создаем архив venv если он готов
        create_venv_archive()
        
        files_list = scan_project_files()
        version_data["files"] = files_list
        
        # Сохраняем обновленный version.json
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=4, ensure_ascii=False)
        
        return True
        
    except Exception:
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
        import services_manager
        api_port = services_manager.get_api_port()
        client = network.NetworkClient()
        url = f"http://{source_ip}:{api_port}/api/files/download?path={filepath}"
        
        # Создаем директорию если нужно (только если есть поддиректории)
        dir_path = os.path.dirname(local_path)
        if dir_path:  # Проверяем, что путь не пустой (для корневых файлов dir_path будет '')
            os.makedirs(dir_path, exist_ok=True)
        
        # Для корневых файлов local_path будет просто имя файла (например, "run.py")
        # Это нормально - файл будет создан в текущей рабочей директории
        result = client.download_file(url, local_path)
        if not result:
            print(f"Failed to download {filepath} from {source_ip}:{api_port}", flush=True)
            return False
        
        # Проверяем, что файл действительно был создан
        if not os.path.exists(local_path):
            print(f"Download reported success but file {local_path} does not exist", flush=True)
            return False
        
        return True
    except Exception as e:
        print(f"Exception downloading {filepath} from {source_ip}: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return False


def download_venv_from_robot(source_ip: str) -> bool:
    """
    Скачивает venv с другого робота как архив.
    
    Args:
        source_ip: IP адрес робота-источника
        
    Returns:
        True если успешно
    """
    try:
        import tarfile
        import tempfile
        import services_manager
        
        venv_path = Path("venv")
        venv_archive = "venv.tar.gz"
        api_port = services_manager.get_api_port()
        
        client = network.NetworkClient()
        url = f"http://{source_ip}:{api_port}/api/files/download?path={venv_archive}"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tar.gz') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            if not client.download_file(url, tmp_path):
                return False
            
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                return False
            
            if venv_path.exists():
                shutil.rmtree(venv_path)
            
            with tarfile.open(tmp_path, 'r:gz') as tar:
                # Используем filter='data' для Python 3.14+ совместимости
                # 'data' фильтрует только опасные метаданные, но сохраняет файлы
                try:
                    tar.extractall(path='.', filter='data')
                except TypeError:
                    # Для старых версий Python filter не поддерживается
                    tar.extractall(path='.')
            
            venv_ready_flag = venv_path / ".ready"
            if not venv_ready_flag.exists():
                venv_ready_flag.touch()
            
            return True
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception:
        return False


def check_venv_exists_on_robot(source_ip: str) -> bool:
    """
    Проверяет наличие venv на другом роботе.
    
    Args:
        source_ip: IP адрес робота-источника
        
    Returns:
        True если venv существует
    """
    try:
        import requests
        import services_manager
        api_port = services_manager.get_api_port()
        url = f"http://{source_ip}:{api_port}/api/files/download?path=venv.tar.gz"
        response = requests.head(url, timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_remote_file_size(source_ip: str, filepath: str) -> Optional[int]:
    """
    Получает размер файла на удаленном роботе.
    
    Args:
        source_ip: IP адрес робота-источника
        filepath: Путь к файлу на роботе
    
    Returns:
        Размер файла в байтах или None если не удалось получить
    """
    try:
        import requests
        import services_manager
        api_port = services_manager.get_api_port()
        url = f"http://{source_ip}:{api_port}/api/files/info?filepath={filepath}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("is_file"):
                return data.get("size")
    except Exception:
        pass
    return None


def update_files_from_robot(source_ip: str, files_to_update: list) -> tuple:
    """
    Обновляет файлы с другого робота, загружая только файлы с отличающимся размером.
    
    Args:
        source_ip: IP адрес робота-источника
        files_to_update: Список файлов для обновления (каждый элемент должен содержать 'path' и 'size')
    
    Returns:
        (success: bool, updated_count: int, skipped_count: int, error_count: int)
        success = True если все файлы обновлены успешно или пропущены (same size)
    """
    if not files_to_update:
        return (True, 0, 0, 0)
    
    success = True
    skipped_count = 0
    updated_count = 0
    error_count = 0
    
    for file_info in files_to_update:
        filepath = file_info.get("path")
        if not filepath:
            continue
        
        # Пропускаем директории
        if file_info.get("is_directory"):
            print(f"Skipping directory: {filepath}", flush=True)
            continue
        
        local_path = filepath
        remote_size = file_info.get("size")
        
        # Проверяем размер локального файла
        local_size = None
        if os.path.exists(local_path) and os.path.isfile(local_path):
            try:
                local_size = os.path.getsize(local_path)
            except (OSError, IOError):
                pass
        
        # Если размеры совпадают и оба не None, пропускаем файл
        if local_size is not None and remote_size is not None and local_size == remote_size:
            skipped_count += 1
            print(f"Skipping {filepath}: sizes match ({local_size} bytes)", flush=True)
            continue
        
        # Загружаем файл
        print(f"Downloading {filepath} (local: {local_size}, remote: {remote_size})...", flush=True)
        try:
            if download_file_from_robot(source_ip, filepath, local_path):
                updated_count += 1
                print(f"Successfully downloaded {filepath}", flush=True)
            else:
                print(f"Failed to download {filepath}", flush=True)
                error_count += 1
                success = False
        except Exception as e:
            print(f"Error downloading {filepath}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            error_count += 1
            success = False
    
    # Выводим статистику только если были изменения
    if updated_count > 0 or skipped_count > 0 or error_count > 0:
        print(f"Update complete: {updated_count} files updated, {skipped_count} files skipped (same size), {error_count} errors", flush=True)
    
    return (success, updated_count, skipped_count, error_count)


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
    except Exception:
        pass
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
    import services_manager
    api_port = services_manager.get_api_port()
    network_api = network_api_module.NetworkAPI()
    best_version = None
    best_version_info = None
    best_source_ip = None
    
    print(f"Checking versions from {len(robot_ips)} robot(s) on port {api_port}...", flush=True)
    
    for ip in robot_ips:
        try:
            base_url = f"http://{ip}:{api_port}"
            print(f"Checking version from {ip}:{api_port}...", flush=True)
            
            # Используем /api/version для получения полного version.json со списком файлов
            version_response = network_api.client.get_from_robot(base_url, "version")
            
            if version_response and version_response.get("success"):
                version_data = version_response.get("version", {})
                version_str = version_data.get("version", "0.00.00")
                version_type = version_data.get("version_type", "STABLE")
                
                print(f"Found version {version_str} ({version_type}) from {ip} with {len(version_data.get('files', []))} files", flush=True)
                
                if not version_matches_priority(version_type, priority):
                    print(f"Version {version_str} ({version_type}) does not match priority {priority}, skipping", flush=True)
                    continue
                
                if best_version is None or network_api._compare_versions(version_str, best_version) > 0:
                    print(f"New best version: {version_str} from {ip}", flush=True)
                    best_version = version_str
                    best_version_info = version_data
                    best_source_ip = ip
            else:
                print(f"No version info from {ip}: {version_response}", flush=True)
        except Exception as e:
            print(f"Error checking version from {ip}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            continue
    
    if best_version_info and best_source_ip:
        print(f"Best version found: {best_version} from {best_source_ip}", flush=True)
        return {
            "success": True,
            "version": best_version_info,
            "source_ip": best_source_ip,
            "source_url": f"http://{best_source_ip}:{api_port}"
        }
    else:
        print(f"No suitable version found (checked {len(robot_ips)} robots)", flush=True)
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
        restart_flag_file = Path("data") / f".restart_{service_name}"
        restart_flag_file.parent.mkdir(parents=True, exist_ok=True)
        restart_flag_file.touch()
        return True
    except Exception:
        return False


def restart_project() -> None:
    """Перезапускает весь проект."""
    import sys
    print("Update completed successfully. Restarting project...", flush=True)
    sys.exit(0)  # Код 0 = успешное завершение, перезапуск обрабатывается main.py


def update_system():
    """
    Основная функция обновления системы.
    Использует ips.json для поиска роботов, находит наивысшую версию,
    соответствующую приоритету, и обновляет файлы.
    Если изменены сервисы - перезапускает только их, иначе перезапускает проект.
    """
    try:
        import scanner
        scanner.scan_network()  # Использует порт из конфигурации scanner_service
    except Exception:
        pass
    
    update_version_file()
    
    priority = get_version_priority_from_settings()
    robot_ips = get_ips_from_file()
    if not robot_ips:
        return True
    
    version_info = find_best_version_by_priority(robot_ips, priority)
    
    if not version_info or not version_info.get("success"):
        print("No version info found or update not needed", flush=True)
        return True
    
    source_ip = version_info.get("source_ip")
    version_data = version_info.get("version", {})
    remote_version = version_data.get("version", "0.00.00")
    remote_version_type = version_data.get("version_type", "STABLE")
    
    current_version = "0.00.00"
    version_file = "data/version.json"
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            current_data = json.load(f)
            current_version = current_data.get("version", "0.00.00")
    
    print(f"Current version: {current_version}, Remote version: {remote_version}", flush=True)
    
    network_api = network_api_module.NetworkAPI()
    version_comparison = network_api._compare_versions(remote_version, current_version)
    print(f"Version comparison result: {version_comparison} (1 = remote newer, 0 = same, -1 = remote older)", flush=True)
    
    if version_comparison <= 0:
        print(f"Remote version {remote_version} is not newer than current {current_version}, skipping update", flush=True)
        return True
    
    files_to_update = version_data.get("files", [])
    print(f"Files to update: {len(files_to_update)}", flush=True)
    if not files_to_update:
        print("No files to update in version data", flush=True)
        return True
    
    changed_services = get_changed_services(files_to_update)
    has_service_changes = len(changed_services) > 0
    
    has_non_service_changes = any(
        not file_info.get("path", "").startswith("services/")
        for file_info in files_to_update
    )
    
    requirements_changed = any(
        file_info.get("path", "") == "requirements.txt"
        for file_info in files_to_update
    )
    
    main_py_changed = any(
        file_info.get("path", "") == "main.py"
        for file_info in files_to_update
    )
    
    venv_updated = False
    if check_venv_exists_on_robot(source_ip):
        venv_updated = download_venv_from_robot(source_ip)
    
    success, updated_count, skipped_count, error_count = update_files_from_robot(source_ip, files_to_update)
    
    # Обновляем версию только если:
    # 1. Все файлы успешно загружены (success = True), ИЛИ
    # 2. Были только пропуски (same size) и нет ошибок (error_count = 0)
    # НЕ обновляем версию если были ошибки загрузки файлов
    should_update_version = success or (error_count == 0 and (updated_count > 0 or skipped_count > 0))
    
    version_file = "data/version.json"
    if should_update_version and os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data_local = json.load(f)
            
            # Обновляем версию только если удаленная версия новее
            current_version_str = version_data_local.get("version", "0.00.00")
            if network_api._compare_versions(remote_version, current_version_str) > 0:
                print(f"Updating version from {current_version_str} to {remote_version}", flush=True)
                version_data_local["version"] = remote_version
                version_data_local["version_type"] = remote_version_type
                
                with open(version_file, 'w', encoding='utf-8') as f:
                    json.dump(version_data_local, f, indent=4, ensure_ascii=False)
                print(f"Version updated to {remote_version}", flush=True)
            else:
                print(f"Version already up to date: {current_version_str}", flush=True)
        except Exception as e:
            print(f"Error updating version file: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
    elif not should_update_version:
        print(f"Skipping version update due to download errors ({error_count} errors)", flush=True)
    
    # Перезапускаем сервисы/проект только если обновление было успешным
    if success:
        if not venv_updated and (requirements_changed or main_py_changed):
            try:
                venv_recreate_flag = Path("data/.recreate_venv")
                venv_recreate_flag.parent.mkdir(parents=True, exist_ok=True)
                venv_recreate_flag.touch()
            except Exception:
                pass
        
        if has_non_service_changes:
            print("Restarting project due to non-service changes", flush=True)
            restart_project()
        elif has_service_changes:
            print(f"Restarting services: {changed_services}", flush=True)
            for service_name in changed_services:
                restart_service(service_name)
    else:
        print(f"Update completed with errors. Version synced to {remote_version}, but some files failed to download.", flush=True)
    
    return success


if __name__ == '__main__':
    update_system()

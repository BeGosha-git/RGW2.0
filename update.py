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
from api import _net as net_policy


def _try_get_version_from(ip: str, port: int) -> Optional[Dict[str, Any]]:
    """Best-effort: refresh + GET /api/version from ip:port. Returns version_response dict or None."""
    try:
        base_url = f"http://{ip}:{int(port)}"
        import network as net_mod
        try:
            refresh_client = net_mod.NetworkClient(timeout=net_policy.timeout_version_refresh())
            refresh_client.post(f"{base_url.rstrip('/')}/api/version/refresh", {"skip_venv_archive": True})
        except Exception:
            pass
        check_client = net_mod.NetworkClient(timeout=net_policy.timeout_version_check())
        return check_client.get_from_robot(base_url, "version")
    except Exception:
        return None


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
    # Исключаем все папки venv-* (но не архивы venv-*.tar.gz)
    exclude_dirs.update({d for d in os.listdir('.') if os.path.isdir(d) and d.startswith('venv-')})
    exclude_files = {'data/version.json', 'data/settings.json', 'data/commands.json', 'data/services.json', 'data/ips.json', '.gitignore'}
    
    services_path = "services"
    
    for root, dirs, files in os.walk('.'):
        if root == '.' and services_path in dirs:
            dirs.remove(services_path)
        
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d != '__pycache__']
        
        if '__pycache__' in root:
            continue
        
        # Пропускаем все папки venv-* (но не архивы venv-*.tar.gz в корне)
        if any(root.replace('\\', '/').startswith(f'./{d}') or root.replace('\\', '/') == f'./{d}' for d in exclude_dirs if d.startswith('venv-')):
            continue
        
        if services_path in root and root != f'./{services_path}':
            continue
        
        for file in files:
            if file in exclude_files:
                continue
            
            filepath = os.path.join(root, file)
            if filepath.startswith('./.'):
                continue
            
            # Пропускаем файлы внутри папок venv-*
            normalized_path = filepath.replace('\\', '/').lstrip('./')
            if any(normalized_path.startswith(f'{d}/') for d in exclude_dirs if d.startswith('venv-')):
                continue
            
            if services_path in filepath and root != f'./{services_path}':
                continue
            
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
    Refreshes the file list in data/version.json without changing the version number.

    The version number is intentionally NOT auto-incremented here.  It only
    changes when update_system() successfully pulls files from another robot.
    This prevents the patch counter from bumping on every restart (e.g. after
    `npm run build` creates new asset hash filenames).

    Returns:
        True on success, False on exception.
    """
    try:
        os.makedirs("data", exist_ok=True)

        version_file = "data/version.json"

        current_version = "1.00.01"
        existing_version_type = "STABLE"

        if os.path.exists(version_file):
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    current_version = existing_data.get("version", "1.00.01")
                    existing_version_type = existing_data.get("version_type", "STABLE")
            except Exception:
                pass

        files_list = scan_project_files()

        version_data = {
            "version": current_version,
            "version_type": existing_version_type,
            "files": files_list,
        }

        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=4, ensure_ascii=False)

        return True

    except Exception:
        return False


def create_venv_archive(root: Optional[Path] = None, python_version: str = None) -> bool:
    """
    Создает архив venv для распространения на другие роботы.
    root: корень проекта; если None — текущая директория.
    python_version: версия Python (например, "3.8", "3.11", "3.13"). Обязательный параметр.
    Returns:
        True если успешно
    """
    if not python_version:
        return False
    
    try:
        import tarfile

        base = Path(root) if root else Path(".")
        
        venv_name = f"venv-{python_version}"
        venv_archive_name = f"venv-{python_version}.tar.gz"
        
        venv_path = base / venv_name
        venv_archive = base / venv_archive_name

        if not venv_path.exists():
            return False

        venv_ready_flag = venv_path / ".ready"
        if not venv_ready_flag.exists():
            return False

        with tarfile.open(venv_archive, 'w:gz') as tar:
            tar.add(venv_path, arcname=venv_name, filter=lambda tarinfo: None if '__pycache__' in tarinfo.name else tarinfo)

        return True

    except Exception:
        return False


def ensure_venv_archive(project_root: Path, python_version: str = None) -> bool:
    """
    Создаёт venv-{version}.tar.gz в project_root, если файла нет или venv обновился.
    python_version: версия Python (например, "3.8", "3.11", "3.13"). Обязательный параметр.
    Returns:
        True если архив есть (был или только что создан)
    """
    if not python_version:
        return False
    
    venv_name = f"venv-{python_version}"
    archive_name = f"venv-{python_version}.tar.gz"
    
    archive = project_root / archive_name
    venv_path = project_root / venv_name
    if not venv_path.exists() or not (venv_path / ".ready").exists():
        return archive.exists()
    need_build = not archive.exists()
    if not need_build:
        try:
            ready_mtime = os.path.getmtime(venv_path / ".ready")
            if ready_mtime > os.path.getmtime(archive):
                need_build = True
        except OSError:
            need_build = True
    if need_build:
        create_venv_archive(project_root, python_version)
    return archive.exists()


def update_version_file(skip_venv_archive: bool = False):
    """
    Обновляет version.json с актуальным списком файлов и их размерами.
    Всегда обновляет список файлов, но не меняет версию.
    Если skip_venv_archive=False, также создает архив venv если он готов.
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
        existing_data = {}
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                version_data["version"] = existing_data.get("version", "1.00.01")
                version_data["version_type"] = existing_data.get("version_type", "STABLE")
        
        if not skip_venv_archive:
            # Создаем архивы для всех версий Python (3.8, 3.11, 3.13)
            for version in ["3.8", "3.11", "3.13"]:
                ensure_venv_archive(Path("."), version)
        
        files_list = scan_project_files()
        version_data["files"] = files_list
        
        # Сохраняем обновленный version.json
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=4, ensure_ascii=False)
        
        return True
        
    except Exception:
        return False


def download_file_from_robot(source_ip: str, filepath: str, local_path: str, api_port: Optional[int] = None) -> bool:
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
        if api_port is None:
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


def download_venv_from_robot(source_ip: str, python_version: str = None, api_port: Optional[int] = None) -> bool:
    """
    Скачивает venv с другого робота как архив для конкретной версии Python.
    
    Args:
        source_ip: IP адрес робота-источника
        python_version: Версия Python (например, "3.8", "3.11", "3.13"). Если None, используется версия из окружения.
        
    Returns:
        True если успешно
    """
    try:
        import tarfile
        import tempfile
        import services_manager
        
        # Определяем версию Python
        if not python_version:
            python_version = os.environ.get('PYTHON_VERSION')
            if not python_version:
                # Пробуем найти первую доступную версию
                for version in ["3.13", "3.11", "3.8"]:
                    venv_check = Path(f"venv-{version}")
                    if venv_check.exists():
                        python_version = version
                        break
                if not python_version:
                    return False
        
        venv_name = f"venv-{python_version}"
        venv_path = Path(venv_name)
        venv_archive = f"venv-{python_version}.tar.gz"
        if api_port is None:
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
            
            # Переименовываем извлеченный venv в venv-{version}
            extracted_venv = Path("venv")
            if extracted_venv.exists() and not venv_path.exists():
                extracted_venv.rename(venv_path)
            
            venv_ready_flag = venv_path / ".ready"
            if not venv_ready_flag.exists():
                venv_ready_flag.touch()
            
            return True
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
                
    except Exception:
        return False


def check_venv_exists_on_robot(source_ip: str, python_version: str = None, api_port: Optional[int] = None) -> bool:
    """
    Проверяет наличие venv на другом роботе для конкретной версии Python.
    
    Args:
        source_ip: IP адрес робота-источника
        python_version: Версия Python (например, "3.8", "3.11", "3.13"). Если None, проверяет все версии.
        
    Returns:
        True если venv существует
    """
    try:
        import requests
        import services_manager
        if api_port is None:
            api_port = services_manager.get_api_port()
        
        # Определяем версию Python
        if not python_version:
            python_version = os.environ.get('PYTHON_VERSION')
            if not python_version:
                # Проверяем все версии
                for version in ["3.13", "3.11", "3.8"]:
                    venv_archive = f"venv-{version}.tar.gz"
                    url = f"http://{source_ip}:{api_port}/api/files/download?path={venv_archive}"
                    try:
                        response = requests.head(url, timeout=net_policy.timeout_file_head())
                        if response.status_code == 200:
                            return True
                    except Exception:
                        continue
                return False
        
        venv_archive = f"venv-{python_version}.tar.gz"
        url = f"http://{source_ip}:{api_port}/api/files/download?path={venv_archive}"
        response = requests.head(url, timeout=net_policy.timeout_file_head())
        return response.status_code == 200
    except Exception:
        return False


def get_remote_file_size(source_ip: str, filepath: str, api_port: Optional[int] = None) -> Optional[int]:
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
        if api_port is None:
            api_port = services_manager.get_api_port()
        url = f"http://{source_ip}:{api_port}/api/files/info?filepath={filepath}"
        response = requests.get(url, timeout=net_policy.timeout_file_info())
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("is_file"):
                return data.get("size")
    except Exception:
        pass
    return None


def actualize_file_list_from_source_and_local(
    source_ip: str, files_list: List[Dict[str, Any]], api_port: Optional[int] = None
) -> tuple:
    """
    Проверяет файлы на источнике и локально, актуализирует размеры (вес).
    Для каждого файла запрашивает размер на source и с диска, обновляет поля size и local_size.

    Returns:
        (files_list, need_update_count, up_to_date_count)
    """
    need_update = 0
    up_to_date = 0
    for file_info in files_list:
        path = file_info.get("path")
        if not path:
            continue
        if file_info.get("is_directory"):
            # для директорий локальный размер для отчёта
            file_info["local_size"] = calculate_file_size(path) if os.path.exists(path) else None
            file_info["size"] = file_info.get("size")
            continue
        # Актуализируем размер на источнике
        remote_size = get_remote_file_size(source_ip, path, api_port=api_port)
        if remote_size is not None:
            file_info["size"] = remote_size
        else:
            remote_size = file_info.get("size")
        # Размер у себя
        if os.path.exists(path) and os.path.isfile(path):
            try:
                local_size = os.path.getsize(path)
            except (OSError, IOError):
                local_size = None
        else:
            local_size = None
        file_info["local_size"] = local_size
        # что нужно обновлять
        if local_size is not None and remote_size is not None and local_size == remote_size:
            up_to_date += 1
        else:
            need_update += 1
    return files_list, need_update, up_to_date


def update_files_from_robot(source_ip: str, files_to_update: list, api_port: Optional[int] = None) -> tuple:
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
        
        # Пропускаем файлы внутри папок venv-* (синхронизируем только архивы venv-*.tar.gz)
        if any(filepath.startswith(f'venv-{v}/') for v in ['3.8', '3.11', '3.13']):
            print(f"Skipping venv file: {filepath} (only archives are synced)", flush=True)
            skipped_count += 1
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
            if download_file_from_robot(source_ip, filepath, local_path, api_port=api_port):
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


def get_local_ips() -> set:
    """Возвращает множество IP этого ПК, чтобы не считать себя источником версии при обновлении."""
    local = {"127.0.0.1"}
    try:
        import socket
        try:
            _, _, ipaddrlist = socket.gethostbyname_ex(socket.gethostname())
            for ip in (ipaddrlist or []):
                local.add(ip)
        except Exception:
            pass
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            local.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    except Exception:
        pass
    return local


def is_this_host(ip: str, port: int) -> bool:
    """True, если ip — этот ПК (при подключении к ip:port локальный адрес сокета совпадает с ip)."""
    if ip in ("127.0.0.1", "localhost"):
        return True
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect((ip, port))
        local_addr = s.getsockname()[0]
        s.close()
        return local_addr == ip
    except Exception:
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
    best_source_port: Optional[int] = None
    
    ports_to_try = net_policy.candidate_api_ports()
    print(
        f"Checking versions from {len(robot_ips)} robot(s) on ports {ports_to_try}: {robot_ips}",
        flush=True,
    )
    
    for ip in robot_ips:
        try:
            version_response = None
            used_port: Optional[int] = None
            for p in ports_to_try:
                print(f"Checking version from {ip}:{p}...", flush=True)
                version_response = _try_get_version_from(ip, p)
                if version_response and isinstance(version_response, dict) and version_response.get("success"):
                    used_port = int(p)
                    break
            
            if version_response and version_response.get("success"):
                version_data = version_response.get("version", {})
                version_str = version_data.get("version", "0.00.00")
                version_type = version_data.get("version_type", "STABLE")
                
                print(
                    f"Found version {version_str} ({version_type}) from {ip}:{used_port} with {len(version_data.get('files', []))} files",
                    flush=True,
                )
                
                if not version_matches_priority(version_type, priority):
                    print(f"Version {version_str} ({version_type}) does not match priority {priority}, skipping", flush=True)
                    print(f"Done with {ip}", flush=True)
                    continue
                
                if best_version is None or network_api._compare_versions(version_str, best_version) > 0:
                    print(f"New best version: {version_str} from {ip}:{used_port}", flush=True)
                    best_version = version_str
                    best_version_info = version_data
                    best_source_ip = ip
                    best_source_port = used_port
            else:
                print(f"No version info from {ip}: {version_response}", flush=True)
            print(f"Done with {ip}", flush=True)
        except Exception as e:
            print(f"Error checking version from {ip}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            print(f"Done with {ip} (error), continuing to next", flush=True)
            continue
    
    if best_version_info and best_source_ip:
        print(f"Best version found: {best_version} from {best_source_ip}:{best_source_port}", flush=True)
        return {
            "success": True,
            "version": best_version_info,
            "source_ip": best_source_ip,
            "source_port": best_source_port,
            "source_url": f"http://{best_source_ip}:{best_source_port}" if best_source_port else f"http://{best_source_ip}"
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


def update_system(force: bool = False, source_ip: str = None):
    """
    Основная функция обновления системы.

    Args:
        force:     Если True — игнорирует сравнение версий и обновляет файлы
                   даже если удалённая версия старше или совпадает с локальной.
        source_ip: Если задан — использует только этот IP как источник обновления,
                   минуя поиск среди всех известных роботов.

    Использует ips.json для поиска роботов, находит наивысшую версию,
    соответствующую приоритету, и обновляет файлы.
    Если изменены сервисы - перезапускает только их, иначе перезапускает проект.
    """
    # --- Discover candidate IPs -------------------------------------------------
    if source_ip:
        # Forced update from a specific IP — skip network scan entirely
        robot_ips = [source_ip]
        print(f"Forced update: using explicit source IP {source_ip}", flush=True)
    else:
        try:
            import scanner
            scanner.scan_network()
        except Exception:
            pass

        robot_ips = get_ips_from_file()
        local_ips = get_local_ips()
        try:
            import services_manager as sm
            api_port = sm.get_api_port()
        except Exception:
            api_port = 5000
        excluded = [ip for ip in robot_ips if ip in local_ips or is_this_host(ip, api_port)]
        robot_ips = [ip for ip in robot_ips if ip not in local_ips and not is_this_host(ip, api_port)]
        if excluded:
            print(f"This host IP(s) excluded from version sources: {excluded}", flush=True)
        if not robot_ips:
            print("No other robots in network (or only this host in ips), skipping update check.", flush=True)
            return True

    print(f"Checking version from other robot(s): {robot_ips}", flush=True)

    # Актуализируем свой version.json перед сравнением (список файлов и размеры, без пересборки venv)
    print("Updating local version.json (file list and sizes)...", flush=True)
    try:
        update_version_file(skip_venv_archive=True)
    except Exception as e:
        print(f"Warning: could not update local version.json: {e}", flush=True)

    priority = get_version_priority_from_settings()
    version_info = find_best_version_by_priority(robot_ips, priority)

    if not version_info or not version_info.get("success"):
        print("No version info found or update not needed", flush=True)
        return True

    chosen_source_ip = version_info.get("source_ip")
    chosen_source_port = version_info.get("source_port")
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

    if not force and version_comparison < 0:
        print(
            f"Remote version {remote_version} (from {chosen_source_ip}) is older than current "
            f"{current_version}, skipping update (use --force to override)",
            flush=True,
        )
        return True

    files_to_update = version_data.get("files", [])
    print("Actualizing file list from source and local...", flush=True)
    files_to_update, need_update_count, up_to_date_count = actualize_file_list_from_source_and_local(
        chosen_source_ip, files_to_update, api_port=chosen_source_port
    )
    print(f"Actualized: {need_update_count} file(s) need update, {up_to_date_count} file(s) up to date (same size)", flush=True)

    if not force and version_comparison == 0 and need_update_count == 0:
        print(f"Same version {remote_version}, all files match (sizes equal). No update needed.", flush=True)
        return True

    if force:
        print(f"Forced update: proceeding regardless of version/file comparison.", flush=True)

    # Только при реальном обновлении обновляем version.json и venv-архив (иначе create_venv_archive тормозит на минуты)
    update_version_file()
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
    if check_venv_exists_on_robot(chosen_source_ip, api_port=chosen_source_port):
        venv_updated = download_venv_from_robot(chosen_source_ip, api_port=chosen_source_port)

    success, updated_count, skipped_count, error_count = update_files_from_robot(chosen_source_ip, files_to_update, api_port=chosen_source_port)

    # Обновляем версию только если:
    # 1. Все файлы успешно загружены (success = True), ИЛИ
    # 2. Были только пропуски (same size) и нет ошибок (error_count = 0)
    should_update_version = success or (error_count == 0 and (updated_count > 0 or skipped_count > 0))

    version_file = "data/version.json"
    if should_update_version and os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data_local = json.load(f)

            current_version_str = version_data_local.get("version", "0.00.00")
            if force or network_api._compare_versions(remote_version, current_version_str) > 0:
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
    import argparse as _argparse
    _parser = _argparse.ArgumentParser(description="RGW2 system updater")
    _parser.add_argument('--force', action='store_true',
                         help='Ignore version comparison and force update')
    _parser.add_argument('--ip', default=None, metavar='IP',
                         help='Force update from this specific IP (implies --force)')
    _args = _parser.parse_args()
    _force = _args.force or bool(_args.ip)
    update_system(force=_force, source_ip=_args.ip)

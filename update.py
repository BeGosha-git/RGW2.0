"""
Модуль для обновления системы.
Использует API для получения актуальной версии и обновления файлов.
"""
import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
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


def update_version_file():
    """
    Обновляет version.json с актуальным списком файлов и их размерами.
    """
    try:
        version_data = {
            "version": "1.00.01",
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
        
        files_list = []
        
        # Сканируем все файлы в корне проекта (кроме служебных)
        exclude_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'build', 'dist'}
        exclude_files = {'data/version.json', 'data/settings.json', 'data/commands.json', 'data/services.json', 'data/ips.json', '.gitignore'}
        
        services_path = "services"
        services_processed = False
        
        for root, dirs, files in os.walk('.'):
            # Пропускаем папку services при обычном сканировании
            if root == '.' and services_path in dirs:
                dirs.remove(services_path)
                services_processed = True
            
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
        
        version_data["files"] = files_list
        
        # Сохраняем обновленный version.json
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=4, ensure_ascii=False)
        
        print(f"Version file updated: {len(files_list)} files/directories")
        return True
        
    except Exception as e:
        print(f"Error updating version file: {str(e)}")
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


def update_system():
    """
    Основная функция обновления системы.
    Получает актуальную версию и обновляет файлы.
    """
    print("Starting system update...")
    
    # Обновляем локальный version.json
    print("Updating local version file...")
    update_version_file()
    
    # Получаем актуальную версию от других роботов
    print("Checking for updates from other robots...")
    network_api = network_api_module.NetworkAPI()
    version_info = network_api.get_actual_version()
    
    if not version_info.get("success"):
        print("No updates available or no other robots found.")
        return True
    
    source_ip = version_info.get("source_ip")
    version_data = version_info.get("version", {})
    remote_version = version_data.get("version", "0.00.00")
    
    # Читаем текущую версию
    current_version = "0.00.00"
    version_file = "data/version.json"
    if os.path.exists(version_file):
        with open(version_file, 'r', encoding='utf-8') as f:
            current_data = json.load(f)
            current_version = current_data.get("version", "0.00.00")
    
    print(f"Current version: {current_version}")
    print(f"Latest version available: {remote_version} from {source_ip}")
    
    # Сравниваем версии
    if network_api._compare_versions(remote_version, current_version) <= 0:
        print("System is up to date.")
        return True
    
    # Получаем список файлов для обновления
    files_to_update = version_data.get("files", [])
    
    if not files_to_update:
        print("No files to update.")
        return True
    
    print(f"Updating {len(files_to_update)} files from {source_ip}...")
    
    # Обновляем файлы
    success = update_files_from_robot(source_ip, files_to_update)
    
    if success:
        # Обновляем версию после успешного обновления
        version_file = "data/version.json"
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data_local = json.load(f)
                version_data_local["version"] = remote_version
                
                with open(version_file, 'w', encoding='utf-8') as f:
                    json.dump(version_data_local, f, indent=4, ensure_ascii=False)
        
        print("System update completed successfully!")
    else:
        print("System update completed with errors.")
    
    return success


if __name__ == '__main__':
    update_system()

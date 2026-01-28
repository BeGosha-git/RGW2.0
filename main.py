"""
Главный файл приложения.
Единственный запускаемый файл для полного процесса.
"""
import os
import sys
import platform
import subprocess
import venv
import json
from pathlib import Path
import services_manager


def is_windows():
    """
    Проверяет, является ли система Windows.
    
    Returns:
        True если Windows, False иначе
    """
    return platform.system() == 'Windows'


def setup_virtual_environment():
    """
    Проверяет наличие виртуального окружения, создает если нет,
    и устанавливает зависимости из requirements.txt.
    
    Returns:
        True если окружение готово, False при ошибке
    """
    venv_name = "venv"
    venv_path = Path(venv_name)
    requirements_file = Path("requirements.txt")
    
    # Проверяем наличие виртуального окружения
    if not venv_path.exists():
        print(f"Virtual environment '{venv_name}' not found. Creating...")
        try:
            # Создаем виртуальное окружение
            venv.create(venv_path, with_pip=True)
            print(f"Virtual environment '{venv_name}' created successfully")
        except Exception as e:
            print(f"Error creating virtual environment: {str(e)}")
            return False
    else:
        print(f"Virtual environment '{venv_name}' found")
    
    # Определяем путь к pip в виртуальном окружении
    if is_windows():
        pip_path = venv_path / "Scripts" / "pip.exe"
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        pip_path = venv_path / "bin" / "pip"
        python_path = venv_path / "bin" / "python"
    
    # Проверяем наличие requirements.txt
    if not requirements_file.exists():
        print(f"Warning: {requirements_file} not found. Skipping dependency installation.")
        return True
    
    # Устанавливаем зависимости
    print(f"Installing dependencies from {requirements_file}...")
    try:
        result = subprocess.run(
            [str(pip_path), "install", "-r", str(requirements_file)],
            check=False,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("Dependencies installed successfully")
            return True
        else:
            print(f"Warning: Some dependencies may not have been installed:")
            print(result.stderr)
            # Продолжаем работу даже если были ошибки
            return True
            
    except Exception as e:
        print(f"Error installing dependencies: {str(e)}")
        print("Continuing anyway...")
        return True


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


def check_and_update_version():
    """
    Проверяет файлы проекта и обновляет версию в data/version.json если файлы изменились.
    Использует логику из update.py.
    
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
        
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    current_version = existing_data.get("version", "1.00.01")
                    current_files = existing_data.get("files", [])
            except Exception as e:
                print(f"Warning: Could not read existing version file: {str(e)}")
        
        # Сканируем текущие файлы
        files_list = []
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
        
        # Для папки services обрабатываем только первый уровень
        if os.path.exists(services_path):
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
                "files": files_list
            }
            
            # Сохраняем обновленный version.json
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, indent=4, ensure_ascii=False)
            
            print(f"Version updated: {current_version} -> {new_version} ({len(files_list)} files)")
            return True
        else:
            print(f"Version check: No changes detected (version {current_version}, {len(files_list)} files)")
            return True
            
    except Exception as e:
        print(f"Error checking/updating version: {str(e)}")
        return False


def run_update():
    """
    Запускает update.py для обновления системы.
    
    Returns:
        True если успешно обновлено
    """
    try:
        print("Running update...")
        import update
        return update.update_system()
    except Exception as e:
        print(f"Error running update: {str(e)}")
        return False


def run_services():
    """
    Запускает run.py для запуска всех сервисов.
    
    Returns:
        True если успешно запущено
    """
    try:
        print("Starting services...")
        import run
        run.run_services()
        return True
    except KeyboardInterrupt:
        print("\nStopped by user")
        return True
    except Exception as e:
        print(f"Error running services: {str(e)}")
        return False


def main():
    """Главная функция приложения."""
    print("=" * 50)
    print("RGW 2.0 - Robot Control System")
    print("=" * 50)
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    print("=" * 50)
    
    # Проверяем и обновляем версию ДО запуска докера
    print("\nChecking and updating version...")
    check_and_update_version()
    print("=" * 50)
    
    # Инициализируем менеджер сервисов
    manager = services_manager.get_services_manager()
    manager.refresh_services()  # Обновляем список сервисов
    
    # Проверяем, запущены ли мы в Docker
    in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    
    # Настройка виртуального окружения только если не в Docker
    if not in_docker:
        print("\nSetting up virtual environment...")
        if not setup_virtual_environment():
            print("Warning: Virtual environment setup had issues, but continuing...")
        print("=" * 50)
    else:
        print("\nDocker environment detected. Skipping virtual environment setup.")
        print("=" * 50)
    
    if is_windows():
        print("Windows detected. Docker-compose will be managed by docker_service.")
    else:
        print("Non-Windows system detected. Running services...")
        
        # В Docker пропускаем update, так как файлы уже скопированы
        # Запускаем update.py только если не в Docker
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
        if not in_docker:
            print("Running update...")
            update_success = run_update()
            if not update_success:
                print("Warning: Update completed with errors, but continuing...")
            print("\n" + "=" * 50)
        else:
            print("Docker environment detected. Skipping update.")
        
        # Запускаем сервисы
        print("Starting services...")
        run_services()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nApplication stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        sys.exit(1)

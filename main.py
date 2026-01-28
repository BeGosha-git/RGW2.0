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


def check_and_update_version():
    """
    Проверяет файлы проекта и обновляет версию в data/version.json если файлы изменились.
    Использует логику из update.py.
    
    Returns:
        True если версия была обновлена или не требовала обновления
    """
    try:
        import update
        return update.check_and_update_version()
    except Exception as e:
        print(f"Error checking/updating version: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
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
    try:
        print("=" * 50, flush=True)
        print("RGW 2.0 - Robot Control System", flush=True)
        print("=" * 50, flush=True)
        print(f"Platform: {platform.system()} {platform.release()}", flush=True)
        print(f"Python: {platform.python_version()}", flush=True)
        print("=" * 50, flush=True)
        
        # Проверяем и обновляем версию ДО запуска докера
        print("\nChecking and updating version...", flush=True)
        try:
            check_and_update_version()
            print("Version check completed", flush=True)
        except Exception as e:
            print(f"Warning: Version check failed: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
        print("=" * 50, flush=True)
        
        # Инициализируем менеджер сервисов
        print("Initializing services manager...", flush=True)
        try:
            manager = services_manager.get_services_manager()
            manager.refresh_services()  # Обновляем список сервисов
            print("Services manager initialized", flush=True)
        except Exception as e:
            print(f"Warning: Services manager initialization failed: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            # Продолжаем работу даже если менеджер не инициализирован
        
        # Проверяем, запущены ли мы в Docker
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
        print(f"In Docker: {in_docker}", flush=True)
    
        # Настройка виртуального окружения только если не в Docker
        if not in_docker:
            print("\nSetting up virtual environment...", flush=True)
            if not setup_virtual_environment():
                print("Warning: Virtual environment setup had issues, but continuing...", flush=True)
            print("=" * 50, flush=True)
        else:
            print("\nDocker environment detected. Skipping virtual environment setup.", flush=True)
            print("=" * 50, flush=True)
        
        is_win = is_windows()
        print(f"is_windows() = {is_win}", flush=True)
        
        if is_win:
            print("Windows detected. Starting docker-compose...", flush=True)
            # Импортируем и запускаем docker-compose напрямую
            try:
                # Импортируем функцию run_docker_compose из docker_service
                from services.windows_docker.docker_service import run_docker_compose
                
                # Запускаем docker-compose и ждем завершения
                success = run_docker_compose()
                
                if success:
                    print("Docker-compose started successfully. main.py exiting.", flush=True)
                    sys.exit(0)
                else:
                    print("Failed to start docker-compose. main.py exiting.", flush=True)
                    sys.exit(1)
                    
            except ImportError as e:
                print(f"Error importing docker_service: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                print("main.py exiting.", flush=True)
                sys.exit(1)
            except Exception as e:
                print(f"Error running docker-compose: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                print("main.py exiting.", flush=True)
                sys.exit(1)
        else:
            print("Non-Windows system detected. Running services...", flush=True)
            
            # В Docker пропускаем update, так как файлы уже скопированы
            # Запускаем update.py только если не в Docker
            in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
            if not in_docker:
                print("Running update...", flush=True)
                update_success = run_update()
                if not update_success:
                    print("Warning: Update completed with errors, but continuing...", flush=True)
                print("\n" + "=" * 50, flush=True)
            else:
                print("Docker environment detected. Skipping update.", flush=True)
            
            # Запускаем сервисы
            print("Starting services...", flush=True)
            run_services()
    except Exception as e:
        print(f"Fatal error in main(): {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise


if __name__ == '__main__':
    try:
        print("main.py starting...", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        main()
        print("main.py completed (this should not happen - services should run forever)", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        # Если main() завершился без ошибок, ждем бесконечно чтобы контейнер не падал
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\nApplication stopped by user", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal error: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)

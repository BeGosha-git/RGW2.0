"""
Сервис для Docker, который запускается только на Windows.
Если система не Windows, сервис завершает себя и устанавливает статус SLEEP.
"""
import os
import sys
import platform
import time
import subprocess
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import services_manager


def is_windows():
    """
    Проверяет, является ли система Windows.
    
    Returns:
        True если Windows, False иначе
    """
    return platform.system() == 'Windows'


def check_docker_available():
    """
    Проверяет доступность Docker.
    
    Returns:
        True если Docker доступен, False иначе
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    except Exception:
        return False


def run_docker_compose():
    """
    Запускает docker-compose на Windows.
    
    Returns:
        True если успешно запущен
    """
    try:
        # Определяем путь к docker-compose.yaml относительно корня проекта
        project_root = Path(__file__).parent.parent.parent
        docker_compose_file = project_root / "services" / "windows_docker" / "docker-compose.yaml"
        
        if not docker_compose_file.exists():
            print(f"Error: {docker_compose_file} not found", flush=True)
            return False
        
        # Проверяем доступность Docker
        print("Checking Docker availability...", flush=True)
        if not check_docker_available():
            print("Error: Docker is not running or not available.", flush=True)
            print("Please start Docker Desktop and try again.", flush=True)
            return False
        print("Docker is available", flush=True)
        
        print("Starting docker-compose...", flush=True)
        # Используем абсолютный путь к docker-compose.yaml
        abs_compose_file = str(docker_compose_file.absolute())
        compose_dir = str(docker_compose_file.parent.absolute())
        
        result = subprocess.run(
            ["docker-compose", "-f", abs_compose_file, "up", "-d", "--build"],
            check=False,
            capture_output=True,
            text=True,
            cwd=compose_dir
        )
        
        if result.returncode == 0:
            print("Docker-compose started successfully", flush=True)
            return True
        else:
            error_output = result.stderr if result.stderr else result.stdout
            print(f"Error starting docker-compose:", flush=True)
            print(error_output, flush=True)
            
            # Проверяем конфликт имен контейнеров
            if "container name" in error_output.lower() and "already in use" in error_output.lower():
                print("\nContainer name conflict detected. Removing old containers and recreating...", flush=True)
                
                # Останавливаем и удаляем контейнеры
                print("Stopping and removing old containers...", flush=True)
                down_result = subprocess.run(
                    ["docker-compose", "-f", abs_compose_file, "down"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=compose_dir
                )
                
                # Пытаемся запустить заново
                print("Starting docker-compose with fresh containers...", flush=True)
                result = subprocess.run(
                    ["docker-compose", "-f", abs_compose_file, "up", "-d", "--build", "--force-recreate"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=compose_dir
                )
                
                if result.returncode == 0:
                    print("Docker-compose started successfully after recreating containers", flush=True)
                    return True
                else:
                    print(f"Error after recreating containers: {result.stderr if result.stderr else result.stdout}", flush=True)
                    return False
            
            # Проверяем специфичные ошибки
            if "dockerDesktopLinuxEngine" in error_output or "pipe" in error_output.lower():
                print("\nHint: Make sure Docker Desktop is running and try again.", flush=True)
            elif "image" in error_output.lower() and "not found" in error_output.lower():
                print("\nHint: Trying to build images...", flush=True)
                # Пытаемся собрать образы
                build_result = subprocess.run(
                    ["docker-compose", "-f", abs_compose_file, "build"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=compose_dir
                )
                if build_result.returncode == 0:
                    print("Images built successfully. Retrying docker-compose up...", flush=True)
                    result = subprocess.run(
                        ["docker-compose", "-f", abs_compose_file, "up", "-d"],
                        check=False,
                        capture_output=True,
                        text=True,
                        cwd=compose_dir
                    )
                    if result.returncode == 0:
                        print("Docker-compose started successfully after build", flush=True)
                        return True
            
            return False
            
    except FileNotFoundError:
        print("Error: docker-compose not found. Please install Docker Compose.", flush=True)
        print("You can install it as part of Docker Desktop: https://www.docker.com/products/docker-desktop", flush=True)
        return False
    except Exception as e:
        print(f"Error running docker-compose: {str(e)}", flush=True)
        return False


def run():
    """
    Основная функция сервиса.
    Проверяет систему и завершает работу если не Windows.
    """
    manager = services_manager.get_services_manager()
    
    # Получаем параметры сервиса
    params = manager.get_service_parameters("docker_service")
    check_windows = params.get("check_windows", True)
    prevent_restart = params.get("prevent_restart", True)
    
    print(f"[docker_service] Starting...", flush=True)
    print(f"[docker_service] Platform: {platform.system()}", flush=True)
    
    # Проверяем текущий статус сервиса
    current_status = manager.get_service("docker_service").get("status")
    
    # Если статус SLEEP, не запускаем сервис (даже если система Windows)
    # SLEEP означает, что сервис сам себя остановил и не должен перезапускаться
    if current_status == "SLEEP":
        print(f"[docker_service] Status is SLEEP. Service will not start.", flush=True)
        print(f"[docker_service] Change status to ON manually if you want to start it.", flush=True)
        sys.exit(0)
    
    # Проверяем, нужно ли проверять Windows
    if check_windows:
        if not is_windows():
            print(f"[docker_service] Not Windows system. Exiting...", flush=True)
            # Устанавливаем статус SLEEP чтобы предотвратить перезапуск
            if prevent_restart:
                manager.update_service_status("docker_service", "SLEEP")
                print(f"[docker_service] Status set to SLEEP to prevent restart", flush=True)
            sys.exit(0)
        else:
            print(f"[docker_service] Windows detected. Running...", flush=True)
    
    # Запускаем docker-compose
    print(f"[docker_service] Starting docker-compose...", flush=True)
    success = run_docker_compose()
    
    if not success:
        print(f"[docker_service] Failed to start docker-compose. Exiting...", flush=True)
        # Устанавливаем статус SLEEP чтобы предотвратить перезапуск
        if prevent_restart:
            manager.update_service_status("docker_service", "SLEEP")
            print(f"[docker_service] Status set to SLEEP to prevent restart", flush=True)
        sys.exit(1)
    
    print(f"[docker_service] Docker-compose started successfully", flush=True)
    
    # Основной цикл работы сервиса
    try:
        while True:
            # Проверяем статус сервиса
            if not manager.is_service_enabled("docker_service"):
                print(f"[docker_service] Service disabled. Exiting...", flush=True)
                break
            
            # Здесь может быть логика работы сервиса
            # Пока просто ждем
            time.sleep(10)
            
    except KeyboardInterrupt:
        print(f"[docker_service] Stopped by user", flush=True)
    except Exception as e:
        print(f"[docker_service] Error: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        print(f"[docker_service] Exiting...", flush=True)


if __name__ == '__main__':
    run()

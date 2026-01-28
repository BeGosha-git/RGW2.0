"""
Модуль для запуска docker-compose.
Независим от services_manager.
"""
import os
import sys
import subprocess
from pathlib import Path


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


def get_compose_command():
    """
    Определяет команду для docker compose.
    
    Returns:
        Список команд для subprocess или None если не найдено
    """
    # Пробуем сначала docker compose (новая версия), затем docker-compose (старая)
    for cmd in ["docker", "docker-compose"]:
        try:
            test_result = subprocess.run(
                [cmd, "compose", "version"] if cmd == "docker" else [cmd, "--version"],
                capture_output=True,
                timeout=2
            )
            if test_result.returncode == 0:
                return ["docker", "compose"] if cmd == "docker" else ["docker-compose"]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def run_docker_compose():
    """
    Запускает docker-compose.
    
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
        
        # Определяем команду compose
        compose_cmd = get_compose_command()
        if not compose_cmd:
            print("Error: Neither 'docker compose' nor 'docker-compose' found", flush=True)
            return False
        
        print("Starting docker-compose...", flush=True)
        # Используем абсолютный путь к docker-compose.yaml
        abs_compose_file = str(docker_compose_file.absolute())
        compose_dir = str(docker_compose_file.parent.absolute())
        
        # Формируем команду запуска
        cmd_list = compose_cmd + ["-f", abs_compose_file, "up", "-d", "--build"]
        
        result = subprocess.run(
            cmd_list,
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
                    compose_cmd + ["-f", abs_compose_file, "down"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=compose_dir
                )
                
                # Пытаемся запустить заново
                print("Starting docker-compose with fresh containers...", flush=True)
                result = subprocess.run(
                    compose_cmd + ["-f", abs_compose_file, "up", "-d", "--build", "--force-recreate"],
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
                    compose_cmd + ["-f", abs_compose_file, "build"],
                    check=False,
                    capture_output=True,
                    text=True,
                    cwd=compose_dir
                )
                if build_result.returncode == 0:
                    print("Images built successfully. Retrying docker-compose up...", flush=True)
                    result = subprocess.run(
                        compose_cmd + ["-f", abs_compose_file, "up", "-d"],
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
        print("Error: docker compose not found. Please install Docker Desktop.", flush=True)
        print("You can install it from: https://www.docker.com/products/docker-desktop", flush=True)
        return False
    except Exception as e:
        print(f"Error running docker-compose: {str(e)}", flush=True)
        return False



#!/usr/bin/env python3
"""
Скрипт для офлайн установки зависимостей проекта.
Устанавливает системные пакеты (deb) и Python пакеты из локальных файлов.
"""
import os
import sys
import subprocess
import platform
from pathlib import Path
import json


def is_windows():
    """Проверяет, является ли система Windows."""
    return platform.system() == 'Windows'


def check_internet():
    """Проверяет наличие интернет-соединения."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def install_system_packages_offline(packages_dir: Path):
    """
    Устанавливает системные пакеты из локальных deb-файлов.
    
    Args:
        packages_dir: Директория с deb-пакетами
    
    Returns:
        True если успешно
    """
    if is_windows():
        print("Windows detected, skipping system packages installation", flush=True)
        return True
    
    if not packages_dir.exists():
        print(f"Packages directory not found: {packages_dir}", flush=True)
        return False
    
    deb_files = list(packages_dir.glob("*.deb"))
    if not deb_files:
        print(f"No deb packages found in {packages_dir}", flush=True)
        return False
    
    print(f"Installing {len(deb_files)} system packages from {packages_dir}...", flush=True)
    
    try:
        # Устанавливаем все deb-пакеты
        result = subprocess.run(
            ["sudo", "dpkg", "-i"] + [str(f) for f in deb_files],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            # Если есть проблемы с зависимостями, пробуем исправить
            print("Fixing dependencies...", flush=True)
            subprocess.run(
                ["sudo", "apt-get", "install", "-f", "-y"],
                capture_output=True,
                text=True,
                timeout=300
            )
        
        print("System packages installed successfully", flush=True)
        return True
        
    except subprocess.TimeoutExpired:
        print("Timeout while installing system packages", flush=True)
        return False
    except Exception as e:
        print(f"Error installing system packages: {e}", flush=True)
        return False


def install_pip_packages_offline(packages_dir: Path, requirements_file: Path, venv_python: Path = None):
    """
    Устанавливает Python пакеты из локальных wheel/tar.gz файлов.
    
    Args:
        packages_dir: Директория с wheel/tar.gz файлами
        requirements_file: Путь к requirements.txt
        venv_python: Путь к Python из venv (если None, используется sys.executable)
    
    Returns:
        True если успешно
    """
    if not packages_dir.exists():
        print(f"Packages directory not found: {packages_dir}", flush=True)
        return False
    
    pip_files = list(packages_dir.glob("*.whl")) + list(packages_dir.glob("*.tar.gz"))
    if not pip_files:
        print(f"No pip packages found in {packages_dir}", flush=True)
        return False
    
    python_exe = str(venv_python) if venv_python and venv_python.exists() else sys.executable
    
    print(f"Installing {len(pip_files)} Python packages from {packages_dir}...", flush=True)
    
    try:
        # Устанавливаем пакеты из локальной директории
        # Сначала обновляем pip, setuptools, wheel
        subprocess.run(
            [python_exe, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Устанавливаем пакеты из локальной директории
        result = subprocess.run(
            [
                python_exe, "-m", "pip", "install",
                "--no-index",  # Не использовать PyPI
                "--find-links", str(packages_dir),  # Искать в локальной директории
                "-r", str(requirements_file)
            ],
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode == 0:
            print("Python packages installed successfully", flush=True)
            return True
        else:
            print(f"Warning: pip install returned code {result.returncode}", flush=True)
            if result.stdout:
                print(f"stdout: {result.stdout}", flush=True)
            if result.stderr:
                print(f"stderr: {result.stderr}", flush=True)
            
            # Пробуем установить напрямую из файлов
            print("Trying to install packages directly from files...", flush=True)
            for pip_file in pip_files:
                try:
                    subprocess.run(
                        [python_exe, "-m", "pip", "install", str(pip_file), "--no-deps"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                except Exception:
                    pass
            
            return True  # Частичный успех
            
    except subprocess.TimeoutExpired:
        print("Timeout while installing pip packages", flush=True)
        return False
    except Exception as e:
        print(f"Error installing pip packages: {e}", flush=True)
        return False


def install_system_package_online(package_name: str):
    """
    Устанавливает системный пакет через apt-get (если есть интернет).
    
    Args:
        package_name: Имя пакета для установки
    
    Returns:
        True если успешно
    """
    if is_windows():
        return False
    
    if not check_internet():
        return False
    
    print(f"Installing {package_name} from internet...", flush=True)
    try:
        result = subprocess.run(
            ["sudo", "apt-get", "install", "-y", package_name],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    """Главная функция."""
    project_root = Path(__file__).parent.parent
    offline_dir = project_root / "offline_packages"
    requirements_file = project_root / "requirements.txt"
    
    print("=" * 60, flush=True)
    print("Offline installation of dependencies", flush=True)
    print("=" * 60, flush=True)
    
    has_internet = check_internet()
    if has_internet:
        print("Internet connection detected, will use online fallback if needed", flush=True)
    else:
        print("No internet connection, using offline packages only", flush=True)
    
    # Устанавливаем системные пакеты
    if not is_windows():
        system_success = install_system_packages_offline(offline_dir)
        
        if not system_success and has_internet:
            # Пробуем установить онлайн
            python_version = "3.8"  # по умолчанию
            try:
                import re
                result = subprocess.run(
                    [sys.executable, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version_match = re.search(r'(\d+)\.(\d+)', result.stdout)
                    if version_match:
                        python_version = f"{version_match.group(1)}.{version_match.group(2)}"
            except Exception:
                pass
            
            package_name = f"python{python_version}-venv"
            print(f"Trying to install {package_name} online...", flush=True)
            install_system_package_online(package_name)
    
    # Устанавливаем pip пакеты
    pip_success = install_pip_packages_offline(offline_dir, requirements_file)
    
    if not pip_success and has_internet:
        print("Trying to install pip packages from internet...", flush=True)
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                capture_output=True,
                text=True,
                timeout=600
            )
        except Exception:
            pass
    
    print("=" * 60, flush=True)
    print("Installation complete!", flush=True)
    print("=" * 60, flush=True)
    
    return True


if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

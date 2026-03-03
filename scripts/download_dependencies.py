#!/usr/bin/env python3
"""
Скрипт для скачивания всех зависимостей проекта для офлайн установки.
Скачивает системные пакеты (deb) и Python пакеты (wheel файлы).
"""
import os
import sys
import subprocess
import platform
import re
from pathlib import Path
import json


def is_windows():
    """Проверяет, является ли система Windows."""
    return platform.system() == 'Windows'


def get_python_version():
    """Определяет версию Python для установки правильных пакетов."""
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_match = re.search(r'(\d+)\.(\d+)', result.stdout)
            if version_match:
                return f"{version_match.group(1)}.{version_match.group(2)}"
    except Exception:
        pass
    return "3.8"  # по умолчанию


def download_system_packages(output_dir: Path):
    """
    Скачивает системные пакеты (deb) для Ubuntu/Debian.
    
    Args:
        output_dir: Директория для сохранения deb-пакетов
    """
    if is_windows():
        print("Windows detected, skipping system packages download", flush=True)
        return True
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    python_version = get_python_version()
    major_minor = python_version.split('.')
    python_package = f"python{major_minor[0]}.{major_minor[1]}-venv"
    
    # Список системных пакетов для установки
    system_packages = [
        python_package,
        "python3-pip",
        "build-essential",
        "python3-dev",
        "libssl-dev",
        "libffi-dev",
    ]
    
    print(f"Downloading system packages to {output_dir}...", flush=True)
    print(f"Python version: {python_version}, package: {python_package}", flush=True)
    
    # Скачиваем пакеты и их зависимости
    for package in system_packages:
        print(f"Downloading {package} and dependencies...", flush=True)
        try:
            result = subprocess.run(
                ["apt-get", "download", package],
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"Warning: Failed to download {package}: {result.stderr}", flush=True)
                # Пробуем скачать зависимости
                try:
                    subprocess.run(
                        ["apt-get", "download", "--download-only", package],
                        cwd=str(output_dir),
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"Error downloading {package}: {e}", flush=True)
    
    # Скачиваем зависимости для всех пакетов
    print("Downloading dependencies for all packages...", flush=True)
    try:
        subprocess.run(
            ["apt-get", "download", "--download-only", "--reinstall"] + system_packages,
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
    except Exception as e:
        print(f"Warning: Could not download all dependencies: {e}", flush=True)
    
    print(f"System packages downloaded to {output_dir}", flush=True)
    return True


def download_pip_packages(output_dir: Path, requirements_file: Path):
    """
    Скачивает Python пакеты (wheel файлы) из requirements.txt.
    
    Args:
        output_dir: Директория для сохранения wheel файлов
        requirements_file: Путь к requirements.txt
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not requirements_file.exists():
        print(f"Requirements file not found: {requirements_file}", flush=True)
        return False
    
    print(f"Downloading Python packages from {requirements_file} to {output_dir}...", flush=True)
    
    try:
        # Скачиваем пакеты и их зависимости в wheel формате
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "download",
                "-r", str(requirements_file),
                "-d", str(output_dir),
                "--platform", "linux_x86_64",
                "--only-binary", ":all:",
                "--no-deps"  # Сначала без зависимостей
            ],
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode != 0:
            print(f"Warning: pip download failed, trying without --only-binary...", flush=True)
            # Пробуем скачать с зависимостями и без ограничения на бинарные пакеты
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip", "download",
                    "-r", str(requirements_file),
                    "-d", str(output_dir),
                    "--prefer-binary"
                ],
                capture_output=True,
                text=True,
                timeout=600
            )
        
        if result.returncode == 0:
            print(f"Python packages downloaded to {output_dir}", flush=True)
            return True
        else:
            print(f"Error downloading packages: {result.stderr}", flush=True)
            return False
            
    except subprocess.TimeoutExpired:
        print("Timeout while downloading packages", flush=True)
        return False
    except Exception as e:
        print(f"Error downloading pip packages: {e}", flush=True)
        return False


def create_metadata(output_dir: Path, python_version: str):
    """
    Создает метаданные о скачанных пакетах.
    
    Args:
        output_dir: Директория с пакетами
        python_version: Версия Python
    """
    metadata = {
        "python_version": python_version,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "system_packages": [],
        "pip_packages": []
    }
    
    # Список системных пакетов
    deb_files = list(output_dir.glob("*.deb"))
    metadata["system_packages"] = [f.name for f in deb_files]
    
    # Список pip пакетов
    pip_files = list(output_dir.glob("*.whl")) + list(output_dir.glob("*.tar.gz"))
    metadata["pip_packages"] = [f.name for f in pip_files]
    
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"Metadata saved to {metadata_file}", flush=True)


def main():
    """Главная функция."""
    project_root = Path(__file__).parent.parent
    offline_dir = project_root / "offline_packages"
    requirements_file = project_root / "requirements.txt"
    
    print("=" * 60, flush=True)
    print("Downloading dependencies for offline installation", flush=True)
    print("=" * 60, flush=True)
    
    python_version = get_python_version()
    print(f"Python version: {python_version}", flush=True)
    print(f"Output directory: {offline_dir}", flush=True)
    
    # Скачиваем системные пакеты
    if not is_windows():
        if not download_system_packages(offline_dir):
            print("Warning: Some system packages failed to download", flush=True)
    
    # Скачиваем pip пакеты
    if not download_pip_packages(offline_dir, requirements_file):
        print("Warning: Some pip packages failed to download", flush=True)
    
    # Создаем метаданные
    create_metadata(offline_dir, python_version)
    
    print("=" * 60, flush=True)
    print("Download complete!", flush=True)
    print(f"All packages saved to: {offline_dir}", flush=True)
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

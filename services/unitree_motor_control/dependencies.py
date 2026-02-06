"""
Модуль для установки зависимостей в venv.
"""
import os
import sys
import subprocess
from pathlib import Path


def setup_cyclonedds_environment():
    """Настраивает переменные окружения для cyclonedds из исходников."""
    # Ищем cyclonedds в стандартных местах
    possible_paths = [
        # Переменная окружения
        os.environ.get('CYCLONEDDS_HOME'),
        # Домашняя директория пользователя
        Path.home() / "cyclonedds",
        # Стандартные системные пути
        Path("/usr/local/cyclonedds"),
        Path("/opt/cyclonedds"),
    ]
    
    for path_str in possible_paths:
        if not path_str:
            continue
        cyclonedds_source = Path(path_str)
        if cyclonedds_source.exists():
            install_lib = cyclonedds_source / "install" / "lib"
            if install_lib.exists():
                ld_library_path = os.environ.get('LD_LIBRARY_PATH', '')
                if str(install_lib) not in ld_library_path:
                    os.environ['LD_LIBRARY_PATH'] = f"{install_lib}:{ld_library_path}" if ld_library_path else str(install_lib)
                if 'CMAKE_PREFIX_PATH' not in os.environ:
                    os.environ['CMAKE_PREFIX_PATH'] = str(cyclonedds_source / "install")
                break


def setup_dependencies():
    """
    Устанавливает зависимости (numpy, cyclonedds) в venv.
    Возвращает (numpy_ok, cyclonedds_ok).
    """
    # Устанавливаем numpy
    numpy_ok = False
    try:
        import numpy
        numpy_ok = True
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--quiet', 'numpy>=1.20.0'],
                check=True,
                timeout=300,
                capture_output=True
            )
            import numpy
            numpy_ok = True
        except Exception:
            pass
    
    # Устанавливаем cyclonedds в venv (пробуем nightly, затем стабильную версию)
    cyclonedds_ok = False
    try:
        import cyclonedds
        cyclonedds_ok = True
    except ImportError:
        # Пробуем сначала nightly версию
        for package_name in ['cyclonedds-nightly', 'cyclonedds==0.10.2']:
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--quiet', package_name],
                    check=True,
                    timeout=600,
                    capture_output=True
                )
                import cyclonedds
                cyclonedds_ok = True
                break
            except Exception:
                continue
    
    return numpy_ok, cyclonedds_ok

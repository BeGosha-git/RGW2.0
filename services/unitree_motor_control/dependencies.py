"""
Модуль для установки зависимостей в venv.
"""
import os
import sys
import subprocess
from pathlib import Path


def setup_cyclonedds_environment():
    """Настраивает переменные окружения для cyclonedds."""
    ld_library_path = os.environ.get('LD_LIBRARY_PATH', '')
    paths_to_add = []
    
    venv_path = None
    if 'VIRTUAL_ENV' in os.environ:
        venv_path = Path(os.environ['VIRTUAL_ENV'])
    elif sys.executable and '/bin/' in sys.executable:
        venv_path = Path(sys.executable).parent.parent
        if not (venv_path / 'lib').exists():
            venv_path = None
    
    if venv_path:
        venv_lib = venv_path / 'lib'
        venv_lib64 = venv_path / 'lib64'
        if venv_lib.exists() and str(venv_lib) not in ld_library_path:
            paths_to_add.append(str(venv_lib))
        if venv_lib64.exists() and str(venv_lib64) not in ld_library_path:
            paths_to_add.append(str(venv_lib64))
    
    system_paths = [
        "/usr/lib/x86_64-linux-gnu",
        "/usr/local/lib",
        "/lib/x86_64-linux-gnu"
    ]
    
    for path_str in system_paths:
        path = Path(path_str)
        if path.exists() and str(path) not in ld_library_path:
            paths_to_add.append(str(path))
    
    possible_paths = [
        os.environ.get('CYCLONEDDS_HOME'),
        Path.home() / "cyclonedds",
        Path("/usr/local/cyclonedds"),
        Path("/opt/cyclonedds"),
    ]
    
    for path_str in possible_paths:
        if not path_str:
            continue
        cyclonedds_source = Path(path_str)
        if cyclonedds_source.exists():
            install_lib = cyclonedds_source / "install" / "lib"
            if install_lib.exists() and str(install_lib) not in ld_library_path:
                paths_to_add.append(str(install_lib))
            if 'CMAKE_PREFIX_PATH' not in os.environ:
                os.environ['CMAKE_PREFIX_PATH'] = str(cyclonedds_source / "install")
            break
    
    if paths_to_add:
        new_ld_path = ':'.join(paths_to_add)
        os.environ['LD_LIBRARY_PATH'] = f"{new_ld_path}:{ld_library_path}" if ld_library_path else new_ld_path
    
    libddsc_so0 = Path("/usr/lib/x86_64-linux-gnu/libddsc.so.0")
    libddsc_so0debian = Path("/usr/lib/x86_64-linux-gnu/libddsc.so.0debian")
    
    if libddsc_so0debian.exists() and not libddsc_so0.exists():
        try:
            import subprocess
            result = subprocess.run(
                ["ln", "-sf", str(libddsc_so0debian), str(libddsc_so0)],
                check=False,
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"[Dependencies] Created libddsc.so.0 symlink", flush=True)
        except Exception:
            pass


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

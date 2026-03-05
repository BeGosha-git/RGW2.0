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
        print("[Dependencies] numpy already installed", flush=True)
    except (ImportError, ModuleNotFoundError) as e:
        # Проверяем, может быть numpy установлен, но сломан (например, отсутствует _multiarray_umath)
        error_str = str(e).lower()
        if '_multiarray_umath' in error_str or 'numpy.core' in error_str:
            print("[Dependencies] numpy is broken, reinstalling...", flush=True)
            # Пробуем переустановить numpy
            try:
                subprocess.run(
                    [sys.executable, '-m', 'pip', 'uninstall', '-y', 'numpy'],
                    check=False,
                    timeout=60,
                    capture_output=True,
                    text=True
                )
            except Exception:
                pass
        
        print("[Dependencies] Installing numpy...", flush=True)
        try:
            install_result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--quiet', '--force-reinstall', 'numpy>=1.20.0'],
                check=True,
                timeout=300,
                capture_output=True,
                text=True
            )
            import numpy
            numpy_ok = True
            print("[Dependencies] numpy installed successfully", flush=True)
        except subprocess.TimeoutExpired:
            print("[Dependencies] Timeout installing numpy", flush=True)
        except subprocess.CalledProcessError as e:
            if e.stderr:
                error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
            else:
                error_msg = str(e)
            print(f"[Dependencies] Failed to install numpy: {error_msg[:200]}", flush=True)
        except Exception as e:
            print(f"[Dependencies] Error installing numpy: {e}", flush=True)
    
    if not numpy_ok:
        print("[Dependencies] WARNING: numpy installation failed. Some features may not work.", flush=True)
    
    # Устанавливаем cyclonedds в venv
    # Сначала проверяем, есть ли он уже установлен
    cyclonedds_ok = False
    try:
        import cyclonedds
        cyclonedds_ok = True
        print("[Dependencies] cyclonedds already installed", flush=True)
    except ImportError:
        # Пробуем установить из офлайн-пакетов
        project_root = Path(__file__).parent.parent.parent
        offline_dir = project_root / "offline_packages"
        
        if offline_dir.exists():
            # Ищем cyclonedds в офлайн-пакетах
            cyclonedds_files = list(offline_dir.glob("*cyclonedds*.whl")) + list(offline_dir.glob("*cyclonedds*.tar.gz"))
            
            if cyclonedds_files:
                print(f"[Dependencies] Found cyclonedds in offline packages: {cyclonedds_files[0].name}", flush=True)
                try:
                    # Устанавливаем из локального файла
                    # Используем абсолютные пути для надежности
                    offline_dir_abs = str(offline_dir.resolve())
                    cyclonedds_file_abs = str(cyclonedds_files[0].resolve())
                    install_result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', '--quiet', '--no-index', '--find-links', offline_dir_abs, cyclonedds_file_abs],
                        check=True,
                        timeout=600,
                        capture_output=True,
                        text=True
                    )
                    import cyclonedds
                    cyclonedds_ok = True
                    print("[Dependencies] cyclonedds installed from offline packages", flush=True)
                except subprocess.TimeoutExpired:
                    print("[Dependencies] Timeout installing cyclonedds from offline packages", flush=True)
                except subprocess.CalledProcessError as e:
                    if e.stderr:
                        error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
                    else:
                        error_msg = str(e)
                    print(f"[Dependencies] Failed to install cyclonedds from offline packages: {error_msg[:200]}", flush=True)
                except Exception as e:
                    print(f"[Dependencies] Error installing cyclonedds from offline packages: {e}", flush=True)
        
        # Если офлайн не сработал, пробуем через интернет
        if not cyclonedds_ok:
            print("[Dependencies] Attempting to install cyclonedds from internet...", flush=True)
            # Пробуем сначала nightly версию, затем стабильную
            for package_name in ['cyclonedds-nightly', 'cyclonedds==0.10.2']:
                try:
                    install_result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', '--quiet', package_name],
                        check=True,
                        timeout=600,
                        capture_output=True,
                        text=True
                    )
                    import cyclonedds
                    cyclonedds_ok = True
                    print(f"[Dependencies] cyclonedds installed from internet: {package_name}", flush=True)
                    break
                except subprocess.TimeoutExpired:
                    print(f"[Dependencies] Timeout installing {package_name}", flush=True)
                    continue
                except subprocess.CalledProcessError as e:
                    if e.stderr:
                        error_msg = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
                    else:
                        error_msg = str(e)
                    print(f"[Dependencies] Failed to install {package_name}: {error_msg[:200]}", flush=True)
                    continue
                except Exception as e:
                    print(f"[Dependencies] Error installing {package_name}: {e}", flush=True)
                    continue
    
    if not cyclonedds_ok:
        print("[Dependencies] WARNING: cyclonedds installation failed. Some features may not work.", flush=True)
    
    return numpy_ok, cyclonedds_ok

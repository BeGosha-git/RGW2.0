"""
Главный файл приложения.
Единственный запускаемый файл для полного процесса.
"""
import os
import sys
import platform
import subprocess
import json
import re
import struct
from pathlib import Path
import faulthandler
import services_manager

# If a selected venv python segfaults on startup, we must not `execv` into it.
# We detect this by running a short smoke-test in a subprocess.
def _python_smoke_test(python_exe: Path) -> bool:
    import subprocess as _subprocess
    env = os.environ.copy()
    # Prevent our own environment tweaks from affecting dynamic linking.
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        proc = _subprocess.run(
            [str(python_exe), "-c", "import sys; print('ok', sys.version)"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _pick_usable_venv_python(preferred_version=None):
    """
    Returns a python executable path from venv-<version>/bin that successfully
    starts a minimal python command.
    """
    order = ["3.13", "3.11", "3.8"]
    versions = ([preferred_version] if preferred_version else []) + [v for v in order if v != preferred_version]

    for v in versions:
        venv_path = Path(f"venv-{v}")
        venv_ready_flag = venv_path / ".ready"

        # Try to ensure it exists (works offline if tar archives are present).
        if not venv_path.exists() or not venv_ready_flag.exists():
            try:
                setup_virtual_environment_for_version(v)
            except Exception:
                pass

        candidates = [
            venv_path / "bin" / f"python{v}",
            venv_path / "bin" / "python3",
            venv_path / "bin" / "python",
        ]
        for c in candidates:
            if c.exists() and _python_smoke_test(c):
                return c
    return None

# If Python segfaults (native extension crash), dump a traceback into logs.
# This makes `systemctl status rgw2` / `journalctl -u rgw2` show where it died.
try:
    faulthandler.enable(all_threads=True)
except Exception:
    pass


def is_windows():
    """
    Проверяет, является ли система Windows.
    
    Returns:
        True если Windows, False иначе
    """
    return platform.system() == 'Windows'


def _host_architecture() -> str:
    arch = platform.machine().lower()
    if arch in {"arm64", "aarch64"}:
        return "aarch64"
    if arch in {"x86_64", "amd64"}:
        return "x86_64"
    return arch


def _elf_architecture(elf_path: Path) -> str:
    try:
        with open(elf_path, "rb") as f:
            hdr = f.read(20)
        if len(hdr) < 20 or hdr[:4] != b"\x7fELF":
            return "unknown"
        e_machine = struct.unpack("<H", hdr[18:20])[0]
        if e_machine == 183:
            return "aarch64"
        if e_machine == 62:
            return "x86_64"
        return f"elf-{e_machine}"
    except Exception:
        return "unknown"


def _venv_cyclonedds_arch(venv_path: Path, python_version: str) -> str:
    site_packages = venv_path / "lib" / f"python{python_version}" / "site-packages"
    candidates = sorted((site_packages / "cyclonedds").glob("_clayer*.so"))
    if not candidates:
        return "missing"
    return _elf_architecture(candidates[0])


def _is_venv_compatible(venv_path: Path, python_version: str) -> bool:
    host_arch = _host_architecture()
    dds_arch = _venv_cyclonedds_arch(venv_path, python_version)
    if dds_arch in {"missing", "unknown"}:
        return True
    return dds_arch == host_arch


def _kill_process_tree(pid: int, timeout: float = 3.0) -> bool:
    """Send SIGTERM to pid, wait timeout seconds, then SIGKILL if still alive."""
    import signal as _signal
    import time
    try:
        os.kill(pid, _signal.SIGTERM)
    except ProcessLookupError:
        return True  # already gone
    except PermissionError:
        print(f"No permission to kill PID {pid}", flush=True)
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)  # check still alive
        except ProcessLookupError:
            return True
        time.sleep(0.1)

    # Force kill
    try:
        os.kill(pid, _signal.SIGKILL)
    except ProcessLookupError:
        pass
    return True


def _single_instance_guard(force: bool = False) -> None:
    """
    Prevent multiple RGW2 instances on the same host.
    If force=True, kills the existing instance (reads PID from lock file)
    and then acquires the lock for the current process.
    """
    if is_windows():
        return
    try:
        import fcntl
        lock_dir = Path("data")
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "rgw2.lock"
        lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not force:
                print("Another RGW2 instance is already running. Exiting.\n"
                      "Use --force to kill it and start a new one.", flush=True)
                sys.exit(0)

            # --force: read old PID, kill it, then re-acquire the lock
            try:
                os.lseek(lock_fd, 0, os.SEEK_SET)
                raw = os.read(lock_fd, 32).decode(errors='ignore').strip()
                old_pid = int(raw) if raw.isdigit() else None
            except Exception:
                old_pid = None

            if old_pid:
                print(f"--force: killing existing RGW2 instance (PID {old_pid})…", flush=True)
                _kill_process_tree(old_pid)
            else:
                print("--force: no PID in lock file, removing stale lock…", flush=True)

            # Remove lock file and re-open (the old fd is dead now)
            try:
                os.close(lock_fd)
            except Exception:
                pass
            try:
                lock_path.unlink()
            except Exception:
                pass

            import time
            time.sleep(0.5)  # give the kernel a moment to release ports

            # Also kill any process still holding our ports
            _force_free_ports([8080, 5000, 8765, 8766])

            lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # must succeed now

        os.truncate(lock_fd, 0)
        os.lseek(lock_fd, 0, os.SEEK_SET)
        os.write(lock_fd, str(os.getpid()).encode())
        # Keep fd open for process lifetime (do not close!)
    except (BlockingIOError, SystemExit):
        raise
    except Exception:
        # Don't hard-fail if locking isn't available
        return


def _force_free_ports(ports: list) -> None:
    """Kill whatever process is listening on each port in the list."""
    for port in ports:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                for pid_str in result.stdout.strip().split():
                    try:
                        pid = int(pid_str)
                        if pid != os.getpid():
                            _kill_process_tree(pid)
                            print(f"--force: freed port {port} (killed PID {pid})", flush=True)
                    except Exception:
                        pass
        except Exception:
            pass


def setup_virtual_environment_for_version(python_version: str) -> bool:
    """
    Создает виртуальное окружение для конкретной версии Python.
    Проверяет наличие venv, если нет - распаковывает из архива, если архива нет - создает и упаковывает.
    
    Args:
        python_version: Версия Python (например, "3.8" или "3.11")
    
    Returns:
        True если окружение готово, False при ошибке
    """
    venv_name = f"venv-{python_version}"
    venv_path = Path(venv_name)
    venv_ready_flag = venv_path / ".ready"
    
    # Проверяем наличие Python этой версии
    python_exe = find_python_executable(python_version)
    if not python_exe:
        print(f"Python {python_version} not found", flush=True)
        return False
    
    if is_windows():
        python_path = venv_path / "Scripts" / "python.exe"
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        python_path = venv_path / "bin" / "python"
        pip_path = venv_path / "bin" / "pip"
    
    # Если venv уже готов - готово
    if venv_path.exists() and venv_ready_flag.exists() and python_path.exists():
        if not _is_venv_compatible(venv_path, python_version):
            print(
                f"[venv-{python_version}] Incompatible transferred venv architecture "
                f"(host={_host_architecture()}, dds={_venv_cyclonedds_arch(venv_path, python_version)}). Rebuilding...",
                flush=True,
            )
            try:
                import shutil
                shutil.rmtree(venv_path)
            except Exception:
                pass
        else:
            print(f"Virtual environment for Python {python_version} is ready", flush=True)
            # Обновляем пакеты если requirements.txt изменился
            packages_updated = _update_packages_if_needed(venv_path, python_path, pip_path, python_version)
            if not packages_updated:
                # Critical runtime deps are missing (e.g. `requests` in offline environment).
                # Mark venv as not ready so the code will re-extract/rebuild it from the tar archive.
                try:
                    venv_ready_flag.unlink(missing_ok=True)
                except Exception:
                    pass
                print(f"[venv-{python_version}] venv marked not-ready (critical deps missing).", flush=True)
                return False
            # Создаем/обновляем архив
            venv_archive = Path(f"venv-{python_version}.tar.gz")
            if not venv_archive.exists() or packages_updated:
                try:
                    create_venv_archive_for_version(python_version)
                except Exception:
                    pass
            return True
    
    # Проверяем наличие архива venv для этой версии
    venv_archive = Path(f"venv-{python_version}.tar.gz")
    venv_meta = Path(f"venv-{python_version}.meta.json")
    if venv_archive.exists():
        print(f"Found venv-{python_version}.tar.gz, extracting...", flush=True)
        try:
            if venv_meta.exists():
                with open(venv_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta_arch = str(meta.get("host_arch", "")).lower().strip()
                if meta_arch and meta_arch != _host_architecture():
                    raise RuntimeError(
                        f"Archive architecture mismatch: archive={meta_arch}, host={_host_architecture()}"
                    )

            import tarfile
            import shutil
            
            if venv_path.exists():
                shutil.rmtree(venv_path)
            
            with tarfile.open(venv_archive, 'r:gz') as tar:
                try:
                    tar.extractall(path='.', filter='data')
                except TypeError:
                    tar.extractall(path='.')
            
            # Переименовываем извлеченный venv в venv-{version}
            extracted_venv = Path("venv")
            if extracted_venv.exists() and not venv_path.exists():
                extracted_venv.rename(venv_path)
            
            venv_ready_flag.touch()
            if not _is_venv_compatible(venv_path, python_version):
                print(
                    f"[venv-{python_version}] Extracted archive is incompatible for this CPU "
                    f"(host={_host_architecture()}, dds={_venv_cyclonedds_arch(venv_path, python_version)}).",
                    flush=True,
                )
                try:
                    import shutil
                    shutil.rmtree(venv_path)
                except Exception:
                    pass
                raise RuntimeError("Incompatible venv archive architecture")
            print(f"Successfully extracted venv-{python_version}.tar.gz", flush=True)

            # Restore execute permissions on all bin/ scripts — tarfile extraction
            # can lose the +x bit depending on the platform umask or filter used.
            try:
                import stat as _stat
                venv_bin_dir = venv_path / "bin"
                if venv_bin_dir.exists():
                    for _f in venv_bin_dir.iterdir():
                        if _f.is_file():
                            _mode = _f.stat().st_mode
                            if not (_mode & _stat.S_IXUSR):
                                os.chmod(str(_f), _mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
            except Exception:
                pass

            # Обновляем пакеты если архив был собран с другими requirements
            _update_packages_if_needed(venv_path, python_path, pip_path, python_version)
            # Пересоздаём архив с актуальными пакетами
            try:
                create_venv_archive_for_version(python_version)
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"Warning: Failed to extract venv-{python_version}.tar.gz: {e}", flush=True)
    
    # Создаем новый venv
    print(f"Creating virtual environment for Python {python_version}...", flush=True)
    try:
        # Для Python 3.8 и 3.11 может не работать ensurepip, используем --without-pip
        venv_args = [python_exe, "-m", "venv", str(venv_path)]
        if python_version in ["3.8", "3.11"]:
            # Пробуем сначала с --without-pip для Python 3.8 и 3.11
            venv_args.append("--without-pip")
        
        result = subprocess.run(
            venv_args,
            check=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        print(f"Successfully created venv using Python {python_version}", flush=True)
    except subprocess.CalledProcessError as e:
        # Если не получилось с --without-pip, пробуем без него
        if python_version in ["3.8", "3.11"] and "--without-pip" in str(e):
            try:
                result = subprocess.run(
                    [python_exe, "-m", "venv", str(venv_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                print(f"Successfully created venv using Python {python_version} (retry without --without-pip)", flush=True)
            except subprocess.CalledProcessError as e2:
                print(f"Error creating venv for Python {python_version}: {e2}", flush=True)
                if e2.stderr:
                    print(f"Error details: {e2.stderr[:300]}", flush=True)
                return False
        else:
            print(f"Error creating venv for Python {python_version}: {e}", flush=True)
            if e.stderr:
                print(f"Error details: {e.stderr[:300]}", flush=True)
            return False
    
    # Устанавливаем пакеты через pip онлайн
    if not install_packages_to_venv(venv_path, python_path, pip_path, python_version):
        print(f"Warning: Failed to install packages for Python {python_version}", flush=True)
        return False

    venv_ready_flag.touch()

    # Сохраняем hash requirements.txt чтобы отслеживать изменения
    requirements_file = Path(f"requirements-{python_version}.txt")
    if not requirements_file.exists():
        requirements_file = Path("requirements.txt")
    _save_requirements_hash(venv_path, requirements_file)

    # Создаем архив
    try:
        create_venv_archive_for_version(python_version)
        print(f"Created archive venv-{python_version}.tar.gz", flush=True)
    except Exception as e:
        print(f"Warning: Could not create venv-{python_version}.tar.gz archive: {e}", flush=True)
    
    print(f"Virtual environment for Python {python_version} created successfully", flush=True)
    return True


def _requirements_hash(requirements_file: Path) -> str:
    """Return a short SHA-256 digest of requirements.txt (comments stripped)."""
    import hashlib
    lines = []
    try:
        with open(requirements_file, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    lines.append(stripped.lower())
    except Exception:
        return ''
    return hashlib.sha256('\n'.join(sorted(lines)).encode()).hexdigest()[:16]


def _stored_requirements_hash(venv_path: Path) -> str:
    """Return the hash that was stored when the venv was last updated."""
    hash_file = venv_path / '.requirements_hash'
    try:
        return hash_file.read_text(encoding='utf-8').strip()
    except Exception:
        return ''


def _save_requirements_hash(venv_path: Path, requirements_file: Path):
    """Persist the current requirements hash inside the venv directory."""
    try:
        h = _requirements_hash(requirements_file)
        (venv_path / '.requirements_hash').write_text(h, encoding='utf-8')
    except Exception:
        pass


def _update_packages_if_needed(venv_path: Path, python_path: Path, pip_path: Path,
                                 python_version: str) -> bool:
    """
    Re-run pip install if requirements.txt changed since the venv was last built.
    Returns True if packages are up-to-date (no action needed or update succeeded).
    """
    requirements_file = Path(f"requirements-{python_version}.txt")
    if not requirements_file.exists():
        requirements_file = Path("requirements.txt")
    if not requirements_file.exists():
        return True  # Nothing to check

    current_hash = _requirements_hash(requirements_file)
    stored_hash  = _stored_requirements_hash(venv_path)

    # If hashes match, still verify that critical imports exist.
    # Otherwise we can mark the venv as "up-to-date" while it is missing
    # required runtime dependencies (e.g. `requests` in offline environments).
    if current_hash == stored_hash:
        check = subprocess.run(
            [str(python_path), "-c", "import flask, requests, websockets, aiortc, av"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode == 0:
            return True  # Already up-to-date and critical deps exist

    print(f"[venv-{python_version}] requirements.txt changed — updating packages...", flush=True)
    # In some offline/tar-extracted venvs `pip` can be missing or non-executable.
    # Don't crash here — try to (re)install pip and then install requirements.
    if (not pip_path.exists()) or (not os.access(str(pip_path), os.X_OK)):
        print(f"[venv-{python_version}] pip missing or not executable; installing pip...", flush=True)
        return install_packages_to_venv(venv_path, python_path, pip_path, python_version)

    # Offline installs should use local wheels if present.
    has_internet = check_internet()
    cmd = [
        str(pip_path),
        "install",
        "--quiet",
        "--no-warn-script-location",
        "-r",
        str(requirements_file),
    ]
    if not has_internet:
        offline_dir = Path("offline_packages")
        if offline_dir.exists():
            cmd += ["--no-index", "--find-links", str(offline_dir.resolve())]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError:
        # pip path existed at check time but is broken/not available for execution.
        print(f"[venv-{python_version}] pip execution failed (FileNotFoundError); reinstalling pip...", flush=True)
        return install_packages_to_venv(venv_path, python_path, pip_path, python_version)
    if result.returncode == 0:
        print(f"[venv-{python_version}] Packages updated successfully", flush=True)
        _save_requirements_hash(venv_path, requirements_file)
        return True
    else:
        # Partial failure — still save hash so we don't retry on every startup
        # if it's a known-optional package that can't be built on this platform.
        print(f"[venv-{python_version}] Some packages failed to update: "
              f"{result.stderr[:300]}", flush=True)
        # Check that critical runtime deps imported fine before accepting partial success.
        check = subprocess.run(
            [str(python_path), "-c", "import flask, requests"],
            check=False, capture_output=True, text=True, timeout=10,
        )
        if check.returncode == 0:
            _save_requirements_hash(venv_path, requirements_file)
            return True
        return False


def install_packages_to_venv(venv_path: Path, python_path: Path, pip_path: Path, python_version: str) -> bool:
    """
    Устанавливает пакеты в venv через pip онлайн.
    
    Args:
        venv_path: Путь к venv
        python_path: Путь к Python в venv
        pip_path: Путь к pip в venv
        python_version: Версия Python
        
    Returns:
        True если успешно
    """
    # Используем версионный requirements файл если существует, иначе базовый
    requirements_file = Path(f"requirements-{python_version}.txt")
    if not requirements_file.exists():
        requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print(f"Warning: requirements file not found", flush=True)
        return False
    
    # Устанавливаем pip если нужно (особенно важно для Python 3.8 с --without-pip)
    if not pip_path.exists():
        print(f"Installing pip for Python {python_version}...", flush=True)
        import shutil
        import urllib.request
        import tempfile
        
        site_packages = venv_path / "lib" / f"python{python_version}" / "site-packages"
        
        # Удаляем сломанный pip из site-packages если есть (несовместимый от другой версии Python)
        broken_pip = site_packages / "pip"
        if broken_pip.exists():
            shutil.rmtree(broken_pip)
        
        pip_installed = False
        
        # Метод 1: get-pip.py из offline_packages
        offline_dir = Path("offline_packages")
        get_pip_file = offline_dir / f"get-pip-{python_version}.py"
        if not get_pip_file.exists():
            get_pip_file = offline_dir / "get-pip.py"
        
        if get_pip_file.exists():
            print(f"Trying get-pip.py from offline_packages for Python {python_version}...", flush=True)
            result = subprocess.run(
                [str(python_path), str(get_pip_file), "--no-warn-script-location"],
            check=False,
            capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and pip_path.exists():
                print(f"Successfully installed pip using offline get-pip.py for Python {python_version}", flush=True)
                pip_installed = True
        
        # Метод 2: Скачиваем get-pip.py онлайн
        if not pip_installed:
            print(f"Downloading get-pip.py for Python {python_version} from internet...", flush=True)
            get_pip_url = f"https://bootstrap.pypa.io/pip/{python_version}/get-pip.py"
            if python_version not in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]:
                get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
            
            tmp_file_path = None
            try:
                tmp_file_path = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False).name
                urllib.request.urlretrieve(get_pip_url, tmp_file_path)
                result = subprocess.run(
                    [str(python_path), tmp_file_path, "--no-warn-script-location"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0 and pip_path.exists():
                    print(f"Successfully installed pip for Python {python_version}", flush=True)
                    pip_installed = True
                else:
                    err_text = result.stderr
                    print(f"Warning: get-pip.py failed: {err_text[:300]}", flush=True)
                    # Если ошибка связана с distutils - устанавливаем пакет и пробуем снова
                    if "distutils" in err_text and not is_windows():
                        print(f"Missing distutils for Python {python_version}, trying to install...", flush=True)
                        distutils_pkg = f"python{python_version}-distutils"
                        subprocess.run(
                            ["sudo", "apt-get", "install", "-y", distutils_pkg],
                            check=False, capture_output=True, text=True, timeout=120
                        )
                        result2 = subprocess.run(
                            [str(python_path), tmp_file_path, "--no-warn-script-location"],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=120,
                        )
                        if result2.returncode == 0 and pip_path.exists():
                            print(f"Successfully installed pip for Python {python_version} after distutils fix", flush=True)
                            pip_installed = True
                        else:
                            print(f"Warning: Still failed after distutils: {result2.stderr[:200]}", flush=True)
            except Exception as e:
                print(f"Warning: get-pip.py download failed: {e}", flush=True)
            finally:
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
        
        if not pip_installed:
            print(f"Error: All methods failed to install pip for Python {python_version}", flush=True)
            return False
        
        print(f"Pip ready for Python {python_version}", flush=True)
    
    # Устанавливаем пакеты через pip онлайн
    # Для Python 3.8 используем системный pip напрямую для установки пакетов в venv
    pip_available = pip_path.exists()
    use_system_pip = False
    site_packages_for_pip = None
    
    # use_system_pip больше не используется - pip устанавливается в venv через get-pip.py
    
    if pip_available or use_system_pip:
        try:
            print(f"Installing packages from {requirements_file.name} for Python {python_version}...", flush=True)
            # Сначала обновляем pip, setuptools, wheel
            # Для Python 3.13 нужен setuptools >= 70.1 для правильной работы с wheel
            print(f"Updating pip, setuptools, wheel for Python {python_version}...", flush=True)
            # Для Python 3.8 используем системный pip для установки в venv
            if use_system_pip and site_packages_for_pip:
                upgrade_cmd = [
                    f"python{python_version}", "-m", "pip", "install", "--target", str(site_packages_for_pip),
                    "--upgrade", "--no-warn-script-location", "--no-cache-dir", "--break-system-packages",
                    "pip", "setuptools", "wheel"
                ]
                upgrade_env = os.environ.copy()
            else:
                upgrade_cmd = [
                    str(pip_path), "install", "--upgrade",
                    "pip", "setuptools>=70.1", "wheel"
                ]
                upgrade_env = os.environ.copy()
            upgrade_result = subprocess.run(
                upgrade_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
                env=upgrade_env
            )
            if upgrade_result.returncode != 0:
                print(f"Warning: Failed to upgrade pip/setuptools/wheel: {upgrade_result.stderr[:200]}", flush=True)
            
            # Для Python 3.13 дополнительно обновляем setuptools в build environment
            if python_version == "3.13":
                print(f"Ensuring setuptools>=70.1 for Python {python_version} build environment...", flush=True)
                # Устанавливаем setuptools>=70.1 перед установкой пакетов
                subprocess.run(
                    [str(pip_path), "install", "--upgrade", "--force-reinstall", "setuptools>=70.1"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            
            # Для Python 3.13 устанавливаем markupsafe отдельно с обновленным setuptools
            if python_version == "3.13":
                print(f"Installing markupsafe separately for Python {python_version}...", flush=True)
                markupsafe_result = subprocess.run(
                    [str(pip_path), "install", "--upgrade", "markupsafe"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if markupsafe_result.returncode == 0:
                    print(f"Successfully installed markupsafe for Python {python_version}", flush=True)
                else:
                    print(f"Warning: Failed to install markupsafe separately: {markupsafe_result.stderr[:200]}", flush=True)
            
            # Устанавливаем пакеты из requirements
            # Для Python 3.13 пропускаем markupsafe, так как он уже установлен
            install_cmd = [str(pip_path), "install", "-r", str(requirements_file)]
            tmp_req_path = None
            if python_version == "3.13":
                # Устанавливаем пакеты по одному, пропуская markupsafe если он уже установлен
                try:
                    # Проверяем, установлен ли markupsafe
                    check_markupsafe = subprocess.run(
                        [str(python_path), "-c", "import markupsafe; print('OK')"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if check_markupsafe.returncode == 0:
                        # Создаем временный requirements без markupsafe
                        import tempfile
                        with open(requirements_file, 'r') as f:
                            req_lines = f.readlines()
                        filtered_reqs = [line for line in req_lines if not line.strip().startswith('markupsafe')]
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp_req:
                            tmp_req.write(''.join(filtered_reqs))
                            tmp_req_path = tmp_req.name
                        if use_system_pip and site_packages_for_pip:
                            install_cmd = [f"python{python_version}", "-m", "pip", "install", "--target", str(site_packages_for_pip), "--no-warn-script-location", "--no-cache-dir", "--break-system-packages", "-r", tmp_req_path]
                        else:
                            install_cmd = [str(pip_path), "install", "-r", tmp_req_path]
                except Exception:
                    pass
            
            # Для Python 3.13 и 3.8 устанавливаем пакеты по одному, чтобы избежать конфликтов зависимостей
            env = os.environ.copy()
            if python_version in ["3.13", "3.8"]:
                if python_version == "3.13":
                    env["PIP_BUILD_ISOLATION"] = "0"
                # Устанавливаем пакеты по одному
                try:
                    import tempfile
                    with open(requirements_file, 'r') as f:
                        req_lines = f.readlines()
                    
                    # Устанавливаем пакеты по одному
                    failed_packages = []
                    optional_packages = {"evdev", "cyclonedds"}  # Пакеты, которые не критичны
                    for line in req_lines:
                        line_stripped = line.strip()
                        if line_stripped and not line_stripped.startswith('#'):
                            # Пропускаем markupsafe для Python 3.13, так как он уже установлен
                            if python_version == "3.13" and 'markupsafe' in line_stripped.lower():
                                continue
                            
                            # Извлекаем имя пакета для проверки
                            pkg_name = line_stripped.split('>=')[0].split('==')[0].split('<=')[0].split('>')[0].split('<')[0].strip().lower()
                            
                            print(f"Installing {line_stripped} for Python {python_version}...", flush=True)
                            pkg_cmd = [str(pip_path), "install", line_stripped]
                            pkg_env = env.copy()
                            
                            pkg_result = subprocess.run(
                                pkg_cmd,
                                check=False,
                                capture_output=True,
                                text=True,
                                timeout=300,
                                env=pkg_env
                            )
                            if pkg_result.returncode != 0:
                                print(f"Warning: Failed to install {line_stripped}: {pkg_result.stderr[:200]}", flush=True)
                                # Для cyclonedds пробуем установить без build isolation
                                if 'cyclonedds' in line_stripped.lower():
                                    print(f"Retrying cyclonedds without build isolation...", flush=True)
                                    cyclonedds_env = env.copy()
                                    cyclonedds_env["PIP_BUILD_ISOLATION"] = "0"
                                    cyclonedds_env["PIP_NO_BUILD_ISOLATION"] = "1"
                                    cyclonedds_cmd = [str(pip_path), "install", "--no-build-isolation", line_stripped]
                                    cyclonedds_retry = subprocess.run(
                                        cyclonedds_cmd,
                                        check=False,
                                        capture_output=True,
                                        text=True,
                                        timeout=300,
                                        env=cyclonedds_env
                                    )
                                    if cyclonedds_retry.returncode == 0:
                                        print(f"Successfully installed cyclonedds without build isolation", flush=True)
                                    else:
                                        print(f"Warning: cyclonedds installation failed, but continuing...", flush=True)
                                        if pkg_name not in optional_packages:
                                            failed_packages.append(line_stripped)
                                elif pkg_name in optional_packages:
                                    # evdev и другие опциональные пакеты - просто пропускаем
                                    print(f"Warning: Optional package {pkg_name} failed to install, continuing...", flush=True)
                                else:
                                    failed_packages.append(line_stripped)
                    
                    # Проверяем успешность установки критичных пакетов
                    check_result = subprocess.run(
                        [str(python_path), "-c", "import flask; print('Flask OK')"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if check_result.returncode == 0:
                        if failed_packages:
                            print(f"Warning: Some packages failed to install: {', '.join(failed_packages)}", flush=True)
                        return True
                    else:
                        print(f"Warning: Critical packages not installed", flush=True)
                        return False
                except Exception as e:
                    print(f"Warning: Failed to install packages separately: {e}", flush=True)
                    # Fallback к обычной установке
                    pass
            else:
                env = os.environ.copy()
            
            # Обычная установка для других версий Python или fallback для 3.13
            # Для Python 3.8 используем системный pip если он доступен
            if use_system_pip and site_packages_for_pip:
                install_env = os.environ.copy()
            else:
                install_env = env
            result = subprocess.run(
                install_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
                env=install_env
            )
            
            # Очищаем временный файл если был создан
            if tmp_req_path and os.path.exists(tmp_req_path):
                try:
                    os.unlink(tmp_req_path)
                except Exception:
                    pass
            
            if result.returncode == 0:
                print(f"Successfully installed packages from {requirements_file.name}", flush=True)
                return True
            else:
                # Выводим полный вывод ошибки для диагностики
                if result.stdout:
                    print(f"pip stdout: {result.stdout[:500]}", flush=True)
                if result.stderr:
                    print(f"pip stderr: {result.stderr[:500]}", flush=True)
                print(f"Warning: Some packages failed to install (exit code: {result.returncode})", flush=True)
                # Не возвращаем False сразу - возможно часть пакетов установилась
                # Проверяем наличие критичных пакетов
                try:
                    check_result = subprocess.run(
                        [str(python_path), "-c", "import flask; print('Flask OK')"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if check_result.returncode == 0:
                        print(f"Critical packages installed successfully, continuing...", flush=True)
                        return True
                except Exception:
                    pass
                return False
        except Exception as e:
            print(f"Warning: Failed to install packages: {e}", flush=True)
            return False
    
    return False


def create_venv_archive_for_version(python_version: str) -> bool:
    """
    Создает архив venv для конкретной версии Python.
    
    Args:
        python_version: Версия Python (например, "3.8" или "3.11")
        
    Returns:
        True если успешно
    """
    try:
        import tarfile
        
        venv_name = f"venv-{python_version}"
        venv_path = Path(venv_name)
        venv_archive = Path(f"{venv_name}.tar.gz")
        venv_meta = Path(f"{venv_name}.meta.json")
        
        if not venv_path.exists():
            return False
        
        venv_ready_flag = venv_path / ".ready"
        if not venv_ready_flag.exists():
            return False
        
        with tarfile.open(venv_archive, 'w:gz') as tar:
            tar.add(venv_path, arcname=venv_name, filter=lambda tarinfo: None if '__pycache__' in tarinfo.name else tarinfo)
        try:
            meta = {
                "python_version": python_version,
                "host_arch": _host_architecture(),
                "cyclonedds_arch": _venv_cyclonedds_arch(venv_path, python_version),
            }
            with open(venv_meta, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        
        return True
    except Exception:
        return False


def setup_virtual_environment(python_version: str = None):
    """
    Проверяет наличие виртуального окружения для указанной версии Python, создает если нет.
    Для обратной совместимости создает основной venv из выбранной версии.
    
    Args:
        python_version: Версия Python для использования (например, "3.8", "3.11", "3.13").
                      Если None, используется логика выбора версии по умолчанию.
    
    Returns:
        True если окружение готово, False при ошибке
    """
    # Определяем доступные версии Python
    available_versions = get_available_python_versions()
    
    # Если указана конкретная версия, используем её
    if python_version:
        if python_version not in available_versions:
            print(f"Python {python_version} not found", flush=True)
            return False
        
        print(f"Setting up virtual environment for Python {python_version}...", flush=True)
        if not setup_virtual_environment_for_version(python_version):
            print(f"Warning: Failed to setup venv for Python {python_version}", flush=True)
            return False
        
        # Создаем основной venv из выбранной версии только если venv готов
        venv_primary = Path(f"venv-{python_version}")
        venv_ready_flag = venv_primary / ".ready"
        venv_main = Path("venv")
        
        # Проверяем, что venv существует и готов (есть .ready файл)
        if venv_primary.exists() and venv_ready_flag.exists():
            try:
                import shutil
                if venv_main.exists():
                    shutil.rmtree(venv_main)
                shutil.copytree(venv_primary, venv_main)
                (venv_main / ".ready").touch()
                print(f"Created main venv from Python {python_version}", flush=True)
            except Exception as e:
                print(f"Warning: Could not create main venv: {e}", flush=True)
                return False
        else:
            print(f"Warning: venv-{python_version} is not ready, cannot create main venv", flush=True)
            return False

        # Настраиваем LD_LIBRARY_PATH для cyclonedds
        if not is_windows():
            lib_paths = []
            for path in ["/usr/lib/x86_64-linux-gnu", "/usr/local/lib", "/lib/x86_64-linux-gnu"]:
                if Path(path).exists():
                    lib_paths.append(path)
            
            try:
                find_cmd = ["find", "/usr", "-name", "libddsc.so*", "-type", "f", "2>/dev/null"]
                result = subprocess.run(
                    " ".join(find_cmd),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                ld_library_path = os.environ.get("LD_LIBRARY_PATH", "")
                
                if result.returncode == 0 and result.stdout.strip():
                    found_libs = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                    if found_libs:
                        lib_dir = str(Path(found_libs[0]).parent)
                        if lib_dir not in ld_library_path:
                            ld_library_path = f"{ld_library_path}:{lib_dir}" if ld_library_path else lib_dir
                
                for lib_path in lib_paths:
                    if lib_path not in ld_library_path:
                        ld_library_path = f"{ld_library_path}:{lib_path}" if ld_library_path else lib_path
                
                os.environ["LD_LIBRARY_PATH"] = ld_library_path
            except Exception:
                pass
        
        return True
    
    # Если версия не указана, создаем venv для нескольких версий (3.13, 3.11, 3.8)
    target_versions = ["3.13", "3.11", "3.8"]
    
    # Создаем venv для каждой доступной версии из target_versions
    venv_created = False
    for version in target_versions:
        if version in available_versions:
            print(f"Setting up virtual environment for Python {version}...", flush=True)
            if setup_virtual_environment_for_version(version):
                venv_created = True
                print(f"Virtual environment for Python {version} ready", flush=True)
            else:
                print(f"Warning: Failed to setup venv for Python {version}", flush=True)
    
    # Создаем основной venv для совместимости (используем первую успешно созданную версию)
    # Проверяем версии в порядке приоритета: 3.13, 3.11, 3.8
    primary_version = None
    for version in ["3.13", "3.11", "3.8"]:
        if version in available_versions:
            venv_check = Path(f"venv-{version}")
            venv_ready_check = venv_check / ".ready"
            # Используем только готовые venv (с установленными пакетами)
            if venv_check.exists() and venv_ready_check.exists():
                primary_version = version
                break
    
    if primary_version:
        venv_primary = Path(f"venv-{primary_version}")
        venv_main = Path("venv")
        if venv_primary.exists() and not venv_main.exists():
            try:
                import shutil
                shutil.copytree(venv_primary, venv_main)
                (venv_main / ".ready").touch()
                print(f"Created main venv from Python {primary_version}", flush=True)
                venv_created = True
            except Exception as e:
                print(f"Warning: Could not create main venv: {e}", flush=True)
    
    if not venv_created:
        print("Warning: Failed to setup any virtual environment", flush=True)
        return False
    
    # Настраиваем LD_LIBRARY_PATH для cyclonedds
    if not is_windows():
        lib_paths = []
        for path in ["/usr/lib/x86_64-linux-gnu", "/usr/local/lib", "/lib/x86_64-linux-gnu"]:
            if Path(path).exists():
                lib_paths.append(path)
        
        try:
            find_cmd = ["find", "/usr", "-name", "libddsc.so*", "-type", "f", "2>/dev/null"]
            result = subprocess.run(
                " ".join(find_cmd),
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            ld_library_path = os.environ.get("LD_LIBRARY_PATH", "")
            
            if result.returncode == 0 and result.stdout.strip():
                found_libs = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if found_libs:
                    lib_dir = str(Path(found_libs[0]).parent)
                    if lib_dir not in ld_library_path:
                        ld_library_path = f"{ld_library_path}:{lib_dir}" if ld_library_path else lib_dir
            
            for lib_path in lib_paths:
                if lib_path not in ld_library_path:
                    ld_library_path = f"{ld_library_path}:{lib_path}" if ld_library_path else lib_path
            
            os.environ["LD_LIBRARY_PATH"] = ld_library_path
        except Exception:
            pass
    
    return True
            

def check_sudo_permissions():
    """
    Проверяет, есть ли у пользователя права на выполнение sudo команд.
    
    Returns:
        True если есть права, False иначе
    """
    if is_windows():
        return True

    try:
        # Проверяем, можем ли выполнить sudo без пароля
        result = subprocess.run(
            ["sudo", "-n", "true"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True

        # Если без пароля не удалось, пробуем пароль из конфигурации робота
        sudo_password = get_sudo_password_for_robot()
        if sudo_password:
            result = subprocess.run(
                ["sudo", "-S", "-k", "true"],
                input=f"{sudo_password}\n",
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True

        # Пробуем с паролем (интерактивно) - но не ждем ввода
        # Просто проверяем наличие sudo
        result = subprocess.run(
            ["which", "sudo"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def get_sudo_password_for_robot() -> str:
    """
    Возвращает sudo-пароль на основе типа робота из data/settings.json.
    H1 -> Unitree0408, G1/G -> 123
    """
    try:
        data_dir = Path(__file__).parent / "data"
        settings_path = data_dir / "settings.json"
        passwords_path = data_dir / "sudo_passwords.json"
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            robot_type = str(settings.get("RobotType", "")).upper()
        else:
            robot_type = ""
    except Exception:
        robot_type = ""

    # Сначала читаем пользовательский файл маппинга паролей
    try:
        if passwords_path.exists():
            with open(passwords_path, "r", encoding="utf-8") as f:
                pwd_map = json.load(f)
            if isinstance(pwd_map, dict):
                configured = pwd_map.get(robot_type) or pwd_map.get(robot_type.upper())
                if configured:
                    return str(configured)
    except Exception:
        pass

    if robot_type == "H1":
        return "Unitree0408"
    if robot_type in {"G1", "G"}:
        return "123"
    return ""


def run_sudo_command(command: list, timeout: int = 120):
    """
    Выполняет sudo-команду без TTY, используя пароль из конфигурации при необходимости.
    """
    if not command:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Empty command")

    if command[0] != "sudo":
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)

    # Сначала пробуем без пароля
    try:
        result = subprocess.run(
            ["sudo", "-n"] + command[1:],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result
    except Exception:
        pass

    sudo_password = get_sudo_password_for_robot()
    if not sudo_password:
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="No sudo password configured")

    return subprocess.run(
        ["sudo", "-S", "-k"] + command[1:],
        input=f"{sudo_password}\n",
        capture_output=True,
        text=True,
        timeout=timeout
    )


def check_internet():
    """Проверяет наличие интернет-соединения."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


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


def find_python_executable(version: str) -> str:
    """
    Находит исполняемый файл Python для указанной версии.
    
    Args:
        version: Версия Python (например, "3.8" или "3.11")
        
    Returns:
        Путь к исполняемому файлу Python или None если не найден
    """
    if is_windows():
        paths = [
            f"C:\\Python{version.replace('.', '')}\\python.exe",
            f"C:\\Program Files\\Python{version.replace('.', '')}\\python.exe",
        ]
    else:
        # Расширенный список путей, включая miniconda и conda environments
        paths = [
            f"/usr/bin/python{version}",
            f"/usr/local/bin/python{version}",
            f"/opt/python{version}/bin/python{version}",
            f"/home/g100/miniconda3/envs/env-isaaclab/bin/python{version}",
            f"/home/g100/miniconda3/bin/python{version}",
            f"{os.path.expanduser('~')}/miniconda3/envs/env-isaaclab/bin/python{version}",
            f"{os.path.expanduser('~')}/miniconda3/bin/python{version}",
            f"{os.path.expanduser('~')}/anaconda3/envs/env-isaaclab/bin/python{version}",
            f"{os.path.expanduser('~')}/anaconda3/bin/python{version}",
        ]
        
        # Также проверяем общий python3 если версия совпадает с текущей
        try:
            current_version_result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if current_version_result.returncode == 0:
                current_version_match = re.search(r'(\d+)\.(\d+)', current_version_result.stdout)
                if current_version_match:
                    current_version = f"{current_version_match.group(1)}.{current_version_match.group(2)}"
                    if current_version == version:
                        # Если текущий Python совпадает с запрошенной версией, используем его
                        if Path(sys.executable).exists():
                            return sys.executable
        except Exception:
            pass
    
    for path in paths:
        if Path(path).exists():
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and version in result.stdout:
                    return path
            except Exception:
                continue
    
    return None


def install_python_version(version: str) -> bool:
    """
    Проверяет наличие указанной версии Python.
    
    Args:
        version: Версия Python (например, "3.8" или "3.11")
        
    Returns:
        True если Python доступен, False при ошибке
    """
    python_exe = find_python_executable(version)
    if python_exe:
        print(f"Python {version} available at {python_exe}", flush=True)
        return True
    
    print(f"Python {version} not found", flush=True)
    return False


def get_available_python_versions() -> list:
    """
    Возвращает список доступных версий Python на системе.
    
    Returns:
        Список версий Python (например, ["3.8", "3.11"])
    """
    available_versions = []
    
    # Проверяем стандартные версии
    for version in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]:
        python_exe = find_python_executable(version)
        if python_exe:
            available_versions.append(version)
    
    return available_versions


def check_offline_packages_completeness():
    """
    Проверяет полноту комплекта офлайн пакетов.
    
    Returns:
        (is_complete: bool, missing_packages: list) - полный ли комплект и список недостающих пакетов
    """
    project_root = Path(__file__).parent
    offline_dir = project_root / "offline_packages"
    requirements_file = project_root / "requirements.txt"
    
    if not offline_dir.exists():
        return (False, ["all"])
    
    missing = []
    
    # Проверяем системные пакеты
    python_version = get_python_version()
    # Пробуем разные варианты имени пакета python3-venv
    python_package_variants = [
        f"python{python_version}-venv",
        "python3-venv",
        f"python3.{python_version.split('.')[1]}-venv" if '.' in python_version else None
    ]
    python_package_variants = [p for p in python_package_variants if p]
    
    system_packages = [
        ("python-venv", python_package_variants),  # Гибкая проверка для python-venv
        ("python3-pip", ["python3-pip"]),
        ("build-essential", ["build-essential"]),
        ("python3-dev", ["python3-dev"]),
        ("libssl-dev", ["libssl-dev"]),
        ("libffi-dev", ["libffi-dev"]),
    ]
    
    deb_files = list(offline_dir.glob("*.deb"))
    for pkg_name, variants in system_packages:
        # Ищем соответствующий deb файл по любому из вариантов
        found = False
        for variant in variants:
            if any(variant.replace("-", "_") in d.name.lower() or variant in d.name.lower() for d in deb_files):
                found = True
                break
        if not found:
            missing.append(f"system:{pkg_name}")
    
    # Проверяем Python пакеты из requirements.txt (исключая cyclonedds)
    if requirements_file.exists():
        try:
            with open(requirements_file, 'r', encoding='utf-8') as f:
                requirements = f.read().strip().split('\n')
            
            pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
            pip_file_names = [f.name.lower() for f in pip_files]
            
            for req_line in requirements:
                req_line = req_line.strip()
                if not req_line or req_line.startswith('#'):
                    continue
                
                # Извлекаем имя пакета (до ==, >=, <= и т.д.)
                pkg_name = req_line.split('>=')[0].split('==')[0].split('<=')[0].split('>')[0].split('<')[0].strip()
                
                # Пропускаем cyclonedds - он уже есть офлайн
                if pkg_name.lower() == "cyclonedds":
                    continue
                
                # Проверяем наличие пакета в скачанных файлах
                found = any(pkg_name.lower() in name for name in pip_file_names)
                if not found:
                    missing.append(f"pip:{pkg_name}")
        except Exception as e:
            print(f"Warning: Could not check requirements completeness: {e}", flush=True)

    is_complete = len(missing) == 0
    return (is_complete, missing)


def download_dependencies():
    """
    Скачивает все зависимости проекта для офлайн установки.
    Скачивает системные пакеты (deb) и Python пакеты (wheel файлы).
    
    Returns:
        True если успешно
    """
    if is_windows():
        print("Windows detected, skipping system packages download", flush=True)
        return True
    
    project_root = Path(__file__).parent
    offline_dir = project_root / "offline_packages"
    requirements_file = project_root / "requirements.txt"
    
    print("=" * 60, flush=True)
    print("Downloading dependencies for offline installation", flush=True)
    print("=" * 60, flush=True)
    
    if not check_internet():
        print("No internet connection. Cannot download dependencies.", flush=True)
        return False

    python_version = get_python_version()
    print(f"Python version: {python_version}", flush=True)
    print(f"Output directory: {offline_dir}", flush=True)
    
    # Создаем директорию для пакетов с правильными правами
    offline_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(offline_dir, 0o755)  # rwxr-xr-x - права на чтение/запись для владельца, чтение для остальных
    
    # Скачиваем get-pip.py для всех версий Python (3.8, 3.11, 3.13)
    print("Downloading get-pip.py for all Python versions (3.8, 3.11, 3.13)...", flush=True)
    try:
        import urllib.request
        
        # URLs для разных версий Python
        get_pip_urls = {
            "3.8": "https://bootstrap.pypa.io/pip/3.8/get-pip.py",
            "3.11": "https://bootstrap.pypa.io/get-pip.py",  # Python 3.11 использует стандартную версию
            "3.13": "https://bootstrap.pypa.io/get-pip.py",
        }
        
        # Также скачиваем стандартную версию для совместимости
        standard_url = "https://bootstrap.pypa.io/get-pip.py"
        
        for version, url in get_pip_urls.items():
            try:
                get_pip_path = offline_dir / f"get-pip-{version}.py"
                urllib.request.urlretrieve(url, str(get_pip_path))
                os.chmod(get_pip_path, 0o644)
                print(f"Successfully downloaded get-pip.py for Python {version}", flush=True)
            except Exception as e:
                print(f"Warning: Failed to download get-pip.py for Python {version}: {e}", flush=True)
        
        # Скачиваем стандартную версию как fallback
        try:
            get_pip_path = offline_dir / "get-pip.py"
            urllib.request.urlretrieve(standard_url, str(get_pip_path))
            os.chmod(get_pip_path, 0o644)
            print(f"Successfully downloaded standard get-pip.py", flush=True)
        except Exception as e:
            print(f"Warning: Failed to download standard get-pip.py: {e}", flush=True)
    except Exception as e:
        print(f"Warning: Failed to download get-pip.py: {e}", flush=True)
    
    # Обновляем список пакетов перед скачиванием
    print("Updating package list...", flush=True)
    try:
        subprocess.run(
            ["apt-get", "update"],
            check=False,
            capture_output=True,
            text=True,
            timeout=300
        )
    except Exception as e:
        print(f"Warning: Failed to update package list: {e}", flush=True)
    
    # Скачиваем системные пакеты (.deb) для всех версий Python
    print("Downloading system packages (.deb) for all Python versions...", flush=True)
    system_packages = {
        "3.8": [
            "python3.8-dev",
            "python3.8-distutils",
            "python3.8-venv",
            "libevdev-dev",
        ],
        "3.11": [
            "python3.11-dev",
            "python3.11-distutils",
            "python3.11-venv",
        ],
        "3.13": [
            "python3.13-dev",
            "python3.13-distutils",
            "python3.13-venv",
        ],
    }
    
    # Общие системные пакеты
    common_packages = [
        "build-essential",
        "python3-pip",
    ]
    
    # Проверяем доступные версии Python
    available_versions = get_available_python_versions()
    
    # Скачиваем пакеты для доступных версий Python
    downloaded_packages = []
    for version in ["3.8", "3.11", "3.13"]:
        if version in available_versions and version in system_packages:
            packages = system_packages[version]
            print(f"Downloading system packages for Python {version}...", flush=True)
            for pkg in packages:
                try:
                    # Используем apt-get download для скачивания .deb файлов
                    result = subprocess.run(
                        ["apt-get", "download", pkg],
                        cwd=str(offline_dir),
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=120
                    )
                    if result.returncode == 0:
                        # Проверяем, что файл действительно скачался
                        deb_files = list(offline_dir.glob(f"{pkg}*.deb"))
                        if deb_files:
                            downloaded_packages.append(pkg)
                            print(f"  ✓ Downloaded {pkg}", flush=True)
                        else:
                            print(f"  ✗ Failed to download {pkg}: file not found", flush=True)
                    else:
                        print(f"  ✗ Failed to download {pkg}: {result.stderr[:100]}", flush=True)
                except Exception as e:
                    print(f"  ✗ Failed to download {pkg}: {e}", flush=True)
    
    # Скачиваем общие пакеты
    print("Downloading common system packages...", flush=True)
    for pkg in common_packages:
        try:
            result = subprocess.run(
                ["apt-get", "download", pkg],
                cwd=str(offline_dir),
                check=False,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                deb_files = list(offline_dir.glob(f"{pkg}*.deb"))
                if deb_files:
                    downloaded_packages.append(pkg)
                    print(f"  ✓ Downloaded {pkg}", flush=True)
                else:
                    print(f"  ✗ Failed to download {pkg}: file not found", flush=True)
            else:
                print(f"  ✗ Failed to download {pkg}: {result.stderr[:100]}", flush=True)
        except Exception as e:
            print(f"  ✗ Failed to download {pkg}: {e}", flush=True)
    
    if downloaded_packages:
        print(f"Successfully downloaded {len(downloaded_packages)} system packages", flush=True)
    else:
        print("Warning: No system packages were downloaded", flush=True)
    
    # НЕ скачиваем pip пакеты - они будут установлены онлайн при создании venv
    # Это упрощает процесс и уменьшает размер offline_packages
    
    # Создаем метаданные с правильными правами
    metadata = {
        "python_version": python_version,
        "platform": platform.system(),
        "architecture": platform.machine(),
    }
    metadata_file = offline_dir / "metadata.json"
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        os.chmod(metadata_file, 0o644)  # rw-r--r-- - права на чтение/запись для владельца, чтение для остальных
    except Exception as e:
        print(f"Warning: Could not create metadata: {e}", flush=True)
    
    print("=" * 60, flush=True)
    print("Download complete!", flush=True)
    print(f"All packages saved to: {offline_dir}", flush=True)
    print("=" * 60, flush=True)
    
    return True


def _offline_pip_stamp_path(project_root: Path) -> Path:
    return project_root / ".cache" / "rgw2_offline_pip.stamp"


def _offline_pip_inputs_fingerprint(
    project_root: Path, offline_dir: Path, requirements_file: Path
) -> str:
    """Стабильный отпечаток входа для офлайн pip: requirements + артефакты + интерпретатор."""
    import hashlib

    h = hashlib.sha256()
    h.update(sys.executable.encode())
    h.update(str(sys.version_info[:3]).encode())
    if requirements_file.exists():
        h.update(requirements_file.read_bytes())
    else:
        h.update(b"<no requirements.txt>")
    combined = sorted(offline_dir.glob("*.whl"), key=lambda p: p.name) + sorted(
        offline_dir.glob("*.tar.gz"), key=lambda p: p.name
    )
    for p in combined:
        try:
            st = p.stat()
            h.update(p.name.encode())
            h.update(str(st.st_size).encode())
            h.update(str(st.st_mtime_ns).encode())
        except OSError:
            h.update(p.name.encode())
    return h.hexdigest()


def install_dependencies_offline():
    """
    Устанавливает зависимости из локальных файлов (офлайн).
    Сначала устанавливает системные пакеты (.deb), затем Python пакеты.
    
    Returns:
        True если успешно
    """
    project_root = Path(__file__).parent
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
    
    # Устанавливаем системные пакеты из offline_packages
    if not is_windows():
        if not check_sudo_permissions():
            print("Warning: No sudo permissions. System packages will not be installed.", flush=True)
            print("Please run with sudo or install packages manually.", flush=True)
        elif offline_dir.exists():
            deb_files = list(offline_dir.glob("*.deb"))
            if deb_files:
                print(f"Installing {len(deb_files)} system packages from {offline_dir}...", flush=True)
                try:
                    # Устанавливаем пакеты по одному для лучшей обработки ошибок
                    installed_count = 0
                    failed_packages = []
                    
                    for deb_file in deb_files:
                        pkg_name = deb_file.stem
                        print(f"  Installing {pkg_name}...", flush=True)
                        result = run_sudo_command(
                            ["sudo", "dpkg", "-i", str(deb_file)],
                            timeout=120
                        )
                        
                        if result.returncode == 0:
                            installed_count += 1
                            print(f"    ✓ {pkg_name} installed", flush=True)
                        else:
                            failed_packages.append(pkg_name)
                            print(f"    ✗ {pkg_name} failed: {result.stderr[:100]}", flush=True)
                    
                    # Исправляем зависимости если были ошибки
                    if failed_packages:
                        print("Fixing dependencies...", flush=True)
                        fix_result = run_sudo_command(
                            ["sudo", "apt-get", "install", "-f", "-y"],
                            timeout=300
                        )
                        if fix_result.returncode == 0:
                            print("Dependencies fixed successfully", flush=True)
                    
                    # Пробуем установить неудачные пакеты онлайн если есть интернет
                    if failed_packages and has_internet:
                        print(f"Trying to install {len(failed_packages)} failed packages online...", flush=True)
                        for pkg in failed_packages:
                            # Извлекаем имя пакета без версии для apt-get
                            pkg_base = pkg.split('_')[0] if '_' in pkg else pkg.split('-')[0] if '-' in pkg else pkg
                            try:
                                online_result = run_sudo_command(
                                    ["sudo", "apt-get", "install", "-y", pkg_base],
                                    timeout=120
                                )
                                if online_result.returncode == 0:
                                    print(f"  ✓ {pkg_base} installed online", flush=True)
                                    installed_count += 1
                            except Exception:
                                pass
                    
                    if installed_count > 0:
                        print(f"Successfully installed {installed_count} system packages", flush=True)
                    else:
                        print("Warning: No system packages were installed", flush=True)
                except Exception as e:
                    print(f"Error installing system packages: {e}", flush=True)
                    if has_internet:
                        print("Trying online installation...", flush=True)
                        # Пробуем установить базовые пакеты онлайн
                        available_versions = get_available_python_versions()
                        for version in ["3.8", "3.11", "3.13"]:
                            if version in available_versions:
                                try:
                                    run_sudo_command(
                                        ["sudo", "apt-get", "install", "-y", f"python{version}-dev", f"python{version}-venv"],
                                        timeout=120
                                    )
                                except Exception:
                                    pass
    
    # Устанавливаем pip пакеты (один раз при неизменных requirements и offline-колёсах см. штамп)
    if offline_dir.exists():
        pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
        if pip_files:
            stamp_path = _offline_pip_stamp_path(project_root)
            pip_fingerprint = _offline_pip_inputs_fingerprint(
                project_root, offline_dir, requirements_file
            )
            try:
                stamp_ok = stamp_path.read_text(encoding="utf-8").strip() == pip_fingerprint
            except Exception:
                stamp_ok = False
            if stamp_ok:
                print(
                    f"Skipping offline pip install ({len(pip_files)} wheels unchanged, "
                    f"see {stamp_path})",
                    flush=True,
                )
            else:
                print(f"Installing {len(pip_files)} Python packages from {offline_dir}...", flush=True)
                try:
                    # Опционально при наличии сети: обновить pip toolchain. Без сети пропускаем
                    # (иначе долгий таймаут) и сразу ставим из offline_packages.
                    if has_internet:
                        try:
                            subprocess.run(
                                [
                                    sys.executable,
                                    "-m",
                                    "pip",
                                    "install",
                                    "--upgrade",
                                    "pip",
                                    "setuptools",
                                    "wheel",
                                ],
                                capture_output=True,
                                text=True,
                                timeout=300,
                            )
                        except subprocess.TimeoutExpired:
                            print(
                                "Warning: pip setuptools wheel upgrade timed out; "
                                "continuing with offline --no-index install",
                                flush=True,
                            )

                    # Устанавливаем из локальной директории
                    result = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pip",
                            "install",
                            "--no-index",
                            "--find-links",
                            str(offline_dir.resolve()),
                            "-r",
                            str(requirements_file),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=600,
                    )

                    if result.returncode == 0:
                        print("Python packages installed successfully", flush=True)
                        try:
                            stamp_path.parent.mkdir(parents=True, exist_ok=True)
                            stamp_path.write_text(pip_fingerprint, encoding="utf-8")
                        except Exception:
                            pass
                    elif has_internet:
                        print("Trying online installation...", flush=True)
                        r_on = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                            capture_output=True,
                            text=True,
                            timeout=600,
                        )
                        if r_on.returncode == 0:
                            try:
                                stamp_path.parent.mkdir(parents=True, exist_ok=True)
                                stamp_path.write_text(pip_fingerprint, encoding="utf-8")
                            except Exception:
                                pass
                except Exception as e:
                    print(f"Error installing pip packages: {e}", flush=True)
                    if has_internet:
                        try:
                            r_on = subprocess.run(
                                [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                                capture_output=True,
                                text=True,
                                timeout=600,
                            )
                            if r_on.returncode == 0:
                                try:
                                    stamp_path.parent.mkdir(parents=True, exist_ok=True)
                                    stamp_path.write_text(pip_fingerprint, encoding="utf-8")
                                except Exception:
                                    pass
                        except Exception:
                            pass
    
    print("=" * 60, flush=True)
    print("Installation complete!", flush=True)
    print("=" * 60, flush=True)
    
    return True


def setup_autostart():
    """
    Создает systemd сервис для автозапуска приложения.
    
    Returns:
        True если сервис создан успешно, False при ошибке
    """
    if is_windows():
        print("Autostart setup is not supported on Windows", flush=True)
        return False
    
    try:
        script_path = Path(__file__).resolve()
        script_dir = script_path.parent
        
        # Определяем Python для использования (предпочитаем venv если есть и готов)
        python_executable = "/usr/bin/python3.8" if Path("/usr/bin/python3.8").exists() else sys.executable
        venv_path = script_dir / "venv"
        venv_ready_flag = venv_path / ".ready"
        
        if venv_path.exists() and venv_ready_flag.exists():
            if is_windows():
                venv_python = venv_path / "Scripts" / "python.exe"
            else:
                venv_python = venv_path / "bin" / "python3"
                if not venv_python.exists():
                    venv_python = venv_path / "bin" / "python"
            
            if venv_python.exists():
                # Use venv python only if it actually starts on this CPU.
                # This avoids writing a broken ExecStart that leads to 203/EXEC.
                try:
                    import subprocess as _sp
                    r = _sp.run(
                        [str(venv_python), "-c", "print('ok')"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if r.returncode == 0:
                        python_executable = str(venv_python.resolve())
                        print(f"Using venv Python: {python_executable}", flush=True)
                    else:
                        print(f"Warning: venv python is not runnable, using system python: {python_executable}", flush=True)
                except Exception:
                    print(f"Warning: venv python check failed, using system python: {python_executable}", flush=True)
        
        # Определяем реального пользователя (не root если запущено через sudo)
        real_user = os.getenv('SUDO_USER') or os.getenv('USER') or 'unitree'
        
        service_name = "rgw2"
        service_file_content = f"""[Unit]
Description=RGW2.0 Main Service
After=network.target

[Service]
Type=simple
User={real_user}
WorkingDirectory={script_dir}
ExecStartPre=/bin/sleep 10
ExecStart={python_executable} {script_path}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Ограничения ресурсов
LimitNOFILE=65536
MemoryLimit=4G

[Install]
WantedBy=multi-user.target
"""
        
        # Используем домашнюю директорию пользователя для временного файла
        # чтобы избежать проблем с правами доступа при запуске через sudo
        import tempfile
        temp_dir = Path.home() / ".tmp"
        temp_dir.mkdir(exist_ok=True, mode=0o755)
        service_file_path = temp_dir / f"{service_name}.service"
        
        try:
            service_file_path.write_text(service_file_content, encoding='utf-8')
            # Устанавливаем правильные права доступа
            os.chmod(service_file_path, 0o644)
        except PermissionError as e:
            print(f"Permission error creating temp file: {e}", flush=True)
            # Пробуем использовать /tmp с правильными правами
            service_file_path = Path(f"/tmp/{service_name}.service")
            try:
                service_file_path.write_text(service_file_content, encoding='utf-8')
                os.chmod(service_file_path, 0o644)
            except Exception as e2:
                print(f"Error creating service file: {e2}", flush=True)
                return False
        
        # Копируем сервис файл в systemd
        copy_result = run_sudo_command(
            ["sudo", "cp", str(service_file_path), f"/etc/systemd/system/{service_name}.service"],
            timeout=10
        )
        
        if copy_result.returncode != 0:
            print(f"Error copying service file: {copy_result.stderr}", flush=True)
            return False
        
        # Перезагружаем systemd
        reload_result = run_sudo_command(
            ["sudo", "systemctl", "daemon-reload"],
            timeout=10
        )
        
        if reload_result.returncode != 0:
            print(f"Error reloading systemd: {reload_result.stderr}", flush=True)
            return False
        
        # Включаем автозапуск
        enable_result = run_sudo_command(
            ["sudo", "systemctl", "enable", service_name],
            timeout=10
        )
        
        if enable_result.returncode != 0:
            print(f"Error enabling service: {enable_result.stderr}", flush=True)
            return False
        
        print(f"Autostart service '{service_name}' created and enabled successfully!", flush=True)
        print(f"To start the service: sudo systemctl start {service_name}", flush=True)
        print(f"To check status: sudo systemctl status {service_name}", flush=True)
        
        return True
        
    except Exception as e:
        print(f"Error setting up autostart: {e}", flush=True)
        return False


def check_and_update_version():
    """Проверяет и обновляет версию проекта."""
    try:
        import upgrade
        return upgrade.check_and_update_version()
    except Exception:
        return False


def run_update():
    """Запускает обновление системы."""
    try:
        import upgrade
        return upgrade.update_system()
    except Exception:
        return False


def _wait_for_first_wifi_scan(start_ts: float, timeout_sec: float = 12.0) -> bool:
    """
    Ensure we have at least one completed network scan (ips.json updated)
    before running any update checks.
    """
    import time
    from pathlib import Path
    t0 = time.time()
    ips_path = Path("data") / "ips.json"
    while time.time() - t0 < float(timeout_sec):
        try:
            if ips_path.exists():
                import json as _json
                data = _json.loads(ips_path.read_text(encoding="utf-8") or "{}")
                scan_count = int(data.get("scan_count") or 0)
                last_scan = float(data.get("last_scan") or 0.0)
                try:
                    mtime = float(ips_path.stat().st_mtime)
                except Exception:
                    mtime = 0.0
                # Require at least one scan happening during THIS process start.
                if scan_count >= 1 and (last_scan >= (start_ts - 1.0) or mtime >= (start_ts - 1.0)):
                    return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def run_services():
    """Запускает все сервисы."""
    try:
        import run
        run.run_services()
        return True
    except KeyboardInterrupt:
        return True
    except SystemExit:
        raise
    except Exception as e:
        print(f"[RGW2] run_services error: {e}", flush=True)
        return False


def main(python_version: str = None, debug: bool = False):
    """
    Главная функция приложения.
    
    Args:
        python_version: Версия Python для использования (например, "3.8", "3.11", "3.13").
                       Если None, используется логика выбора версии по умолчанию.
        debug: Включить режим отладки (вывод дополнительной информации).
    """
    # Устанавливаем переменную окружения для debug режима
    if debug:
        os.environ['RGW2_DEBUG'] = '1'
    else:
        os.environ.pop('RGW2_DEBUG', None)

    import time as _time
    boot_start_ts = _time.time()
    print("[RGW2] entering main()", flush=True)
    try:
        try:
            print("[RGW2] ensure_default_commands()", flush=True)
            import api.robot as robot_api
            robot_api.RobotAPI.ensure_default_commands()
        except Exception:
            pass
        
        try:
            print("[RGW2] refresh_services()", flush=True)
            manager = services_manager.get_services_manager()
            manager.refresh_services()
        except Exception:
            pass

        # Update checks should run only after at least one Wi-Fi/network scan happened.
        try:
            ok_scan = _wait_for_first_wifi_scan(start_ts=boot_start_ts, timeout_sec=12.0)
            if not ok_scan:
                # Fallback: perform a direct scan once (fast timeout) to populate ips.json.
                try:
                    import scanner
                    scanner.scan_network()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            print("[RGW2] check_and_update_version()", flush=True)
            check_and_update_version()
        except Exception:
            pass
        
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    
        # Проверяем, запущены ли мы уже из venv (чтобы избежать повторного создания venv после os.execv)
        venv_already_active = False
        if not in_docker:
            venv_python_check = Path(sys.executable)
            # Проверяем, запущены ли мы из venv (путь содержит venv или venv-{version})
            if 'venv' in str(venv_python_check) or 'VIRTUAL_ENV' in os.environ:
                venv_already_active = True
    
        if not in_docker and not venv_already_active:
            # Устанавливаем системные зависимости из offline_packages перед созданием venv
            try:
                install_dependencies_offline()
            except Exception as e:
                print(f"Warning: Failed to install system dependencies: {e}", flush=True)
            
            # Скачиваем get-pip.py для всех версий Python если есть интернет
            if check_internet():
                try:
                    offline_dir = Path("offline_packages")
                    offline_dir.mkdir(parents=True, exist_ok=True)
                    
                    import urllib.request
                    get_pip_urls = {
                        "3.8": "https://bootstrap.pypa.io/pip/3.8/get-pip.py",
                        "3.11": "https://bootstrap.pypa.io/get-pip.py",  # Python 3.11 использует стандартную версию
                        "3.13": "https://bootstrap.pypa.io/get-pip.py",
                    }
                    standard_url = "https://bootstrap.pypa.io/get-pip.py"
                    
                    for version, url in get_pip_urls.items():
                        get_pip_path = offline_dir / f"get-pip-{version}.py"
                        if not get_pip_path.exists():
                            try:
                                urllib.request.urlretrieve(url, str(get_pip_path))
                                os.chmod(get_pip_path, 0o644)
                                print(f"Downloaded get-pip.py for Python {version}", flush=True)
                            except Exception:
                                pass
                    
                    # Скачиваем стандартную версию
                    standard_path = offline_dir / "get-pip.py"
                    if not standard_path.exists():
                        try:
                            urllib.request.urlretrieve(standard_url, str(standard_path))
                            os.chmod(standard_path, 0o644)
                            print(f"Downloaded standard get-pip.py", flush=True)
                        except Exception:
                            pass
                except Exception:
                    pass
            
            # Автоматически настраиваем venv для ВСЕХ доступных версий Python (3.8, 3.11, 3.13) если есть интернет
            available_versions = get_available_python_versions()
            if check_internet():
                target_versions = ["3.13", "3.11", "3.8"]
                for version in target_versions:
                    if version in available_versions:
                        venv_check = Path(f"venv-{version}")
                        venv_ready_check = venv_check / ".ready"
                        # Создаем venv только если его нет или он не готов
                        if not (venv_check.exists() and venv_ready_check.exists()):
                            if debug:
                                print(f"Setting up virtual environment for Python {version}...", flush=True)
                            setup_virtual_environment_for_version(version)
            
            # Определяем версию Python для использования
            selected_version = python_version
            if not selected_version:
                # Ищем первую доступную готовую версию Python
                for version in ["3.13", "3.11", "3.8"]:
                    if version in available_versions:
                        venv_check = Path(f"venv-{version}")
                        venv_ready_check = venv_check / ".ready"
                        if venv_check.exists() and venv_ready_check.exists():
                            selected_version = version
                            break
                
                # Если не нашли готовую версию, используем первую доступную
                if not selected_version and available_versions:
                    selected_version = available_versions[0]
            
            if selected_version:
                # Создаем venv для выбранной версии если нужно (на случай если не создался выше)
                if not setup_virtual_environment(selected_version):
                    if debug:
                        print(f"Warning: Failed to setup virtual environment for Python {selected_version}", flush=True)
                # Используем venv для указанной версии
                venv_path = Path(f"venv-{selected_version}").resolve()
                # Сохраняем версию в переменную окружения для использования в run.py
                os.environ['PYTHON_VERSION'] = selected_version
            else:
                # Если версия не указана и нет доступных, создаем venv для всех доступных версий
                if debug:
                    print("Setting up virtual environments for all available Python versions...", flush=True)
                if not setup_virtual_environment(None):
                    if debug:
                        print("Warning: Failed to setup some virtual environments", flush=True)
                # Используем основной venv (созданный из первой доступной версии)
                venv_path = Path("venv").resolve()
                # Очищаем переменную окружения если версия не указана
                if 'PYTHON_VERSION' in os.environ:
                    del os.environ['PYTHON_VERSION']

            if is_windows():
                venv_python = venv_path / "Scripts" / "python.exe"
            else:
                venv_python = venv_path / "bin" / "python3"
                if not venv_python.exists():
                    venv_python = venv_path / "bin" / "python"

            if venv_python.exists():
                venv_python_resolved = venv_python.resolve()
                current_python = Path(sys.executable).resolve()

                try:
                    venv_same = venv_python_resolved.samefile(current_python)
                except (OSError, ValueError):
                    venv_same = (str(venv_python_resolved) == str(current_python))

                # Ensure critical deps exist in the selected venv.
                # Some hosts extract venvs from tar archives without packages like `flask/requests`.
                deps_version = os.environ.get('PYTHON_VERSION') or (
                    str(venv_path).split('venv-')[-1] if 'venv-' in str(venv_path) else None
                )
                if deps_version and _python_smoke_test(venv_python):
                    dep_check = subprocess.run(
                        [str(venv_python), "-c", "import flask, requests"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    if dep_check.returncode != 0:
                        print(f"[RGW2] critical deps missing in {venv_path}; installing...", flush=True)
                        if is_windows():
                            pip_guess = venv_path / "Scripts" / "pip.exe"
                        else:
                            pip_guess = venv_path / "bin" / "pip"
                        try:
                            install_packages_to_venv(venv_path, venv_python, pip_guess, deps_version)
                        except Exception as _e:
                            print(f"[RGW2] Failed to install critical deps: {_e}", flush=True)

                if not venv_same:
                    preferred_version = os.environ.get('PYTHON_VERSION')
                    # Smoke-test to avoid execv into a python that immediately SIGSEGVs.
                    if not _python_smoke_test(venv_python):
                        fallback_python = _pick_usable_venv_python(preferred_version=preferred_version)
                        if fallback_python:
                            try:
                                venv_path = fallback_python.parent.parent
                                venv_python = fallback_python
                                os.environ['PYTHON_VERSION'] = venv_path.name.replace('venv-', '')
                                venv_same = False
                                print(f"[RGW2] Using fallback venv python: {venv_python}", flush=True)
                            except Exception:
                                fallback_python = None

                    # If still not usable, don't execv (prevents systemd crash loops).
                    if not _python_smoke_test(venv_python):
                        print(f"[RGW2] venv python smoke-test failed; skipping execv: {venv_python}", flush=True)
                        venv_same = True
                        pass

                    # Ensure the venv Python binary is executable (may lose +x
                    # when the venv is extracted from a tar.gz archive).
                    if not venv_same and not os.access(str(venv_python), os.X_OK):
                        try:
                            import stat as _stat
                            current_mode = os.stat(str(venv_python)).st_mode
                            os.chmod(str(venv_python), current_mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
                            print(f"Fixed execute permission on {venv_python}", flush=True)
                        except Exception as _e:
                            print(f"Warning: could not chmod venv Python: {_e}", flush=True)

                    # Fix all bin/ scripts in the venv (same issue with pip, activate, etc.)
                    if not venv_same:
                        venv_bin = venv_path / "bin"
                        if venv_bin.exists():
                            try:
                                import stat as _stat
                                for _f in venv_bin.iterdir():
                                    if _f.is_file() and not os.access(str(_f), os.X_OK):
                                        try:
                                            _mode = os.stat(str(_f)).st_mode
                                            os.chmod(str(_f), _mode | _stat.S_IXUSR | _stat.S_IXGRP | _stat.S_IXOTH)
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                    # Set VIRTUAL_ENV so the re-executed process knows it is already
                    # inside a venv and skips a second re-execution cycle.
                    if not venv_same:
                        os.environ['VIRTUAL_ENV'] = str(venv_path)
                        # Use the *unresolved* symlink path so Python can locate
                        # pyvenv.cfg and activate site-packages for this venv.
                        if os.access(str(venv_python), os.X_OK):
                            print(f"[RGW2] execv -> {venv_python}", flush=True)
                            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
                        else:
                            print(f"Warning: venv Python {venv_python} is not executable, running with current Python", flush=True) 
            else:
                selected_version = python_version or os.environ.get('PYTHON_VERSION')
                if selected_version:
                    print(f"Error: venv-{selected_version} not found or incomplete", flush=True)
                else:
                    print("Error: venv not found or incomplete", flush=True)
        
        if is_windows():
            try:
                from services.windows_docker.docker_service import run_docker_compose
                success = run_docker_compose()
                
                if success:
                    sys.exit(0)
                else:
                    sys.exit(1)
            except Exception:
                sys.exit(1)
        else:
            if not in_docker:
                run_update()
            run_services()
    except SystemExit:
        raise
    except Exception:
        raise


def cleanup_ports():
    """Освобождает порты, используемые сервисами."""
    try:
        import subprocess
        manager = services_manager.get_services_manager()
        
        ports_to_clean = set()
        
        web_service = manager.get_service("web")
        if web_service:
            web_params = manager.get_service_parameters("web")
            web_port = web_params.get("port", 8080)
            ports_to_clean.add(web_port)
        
        api_service = manager.get_service("api")
        if api_service:
            api_params = manager.get_service_parameters("api")
            api_port = api_params.get("port", 5000)
            ports_to_clean.add(api_port)
        
        scanner_service = manager.get_service("scanner_service")
        if scanner_service:
            scanner_params = manager.get_service_parameters("scanner_service")
            scanner_port = scanner_params.get("port", 8080)
            ports_to_clean.add(scanner_port)
        
        for port in ports_to_clean:
            try:
                subprocess.run(["fuser", "-k", f"{port}/tcp"], 
                             capture_output=True, timeout=2, stderr=subprocess.DEVNULL)
            except Exception:
                try:
                    result = subprocess.run(["lsof", "-ti", f":{port}"], 
                                           capture_output=True, timeout=2, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            try:
                                subprocess.run(["kill", "-9", pid], 
                                             capture_output=True, timeout=1, stderr=subprocess.DEVNULL)
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass


if __name__ == '__main__':
    import signal
    import argparse

    # Parse args BEFORE the instance guard so --force is available
    parser = argparse.ArgumentParser(description='RGW2.0 Main Service')
    parser.add_argument('--version', type=str, choices=['3.8', '3.11', '3.13'],
                        help='Python version to use (3.8, 3.11, or 3.13)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--force', action='store_true',
                        help='Kill any existing RGW2 instance and free its ports before starting')
    args = parser.parse_args()

    _single_instance_guard(force=args.force)
    
    # Проверяем автозапуск
    autostart_configured = False
    if not is_windows():
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "rgw2"],
                capture_output=True,
                text=True,
                timeout=5
            )
            autostart_configured = result.returncode == 0
        except Exception:
            pass
    
    # Проверяем установлены ли зависимости
    dependencies_installed = True
    if not is_windows():
        # Проверяем наличие критичных системных пакетов
        try:
            result = subprocess.run(
                ["dpkg", "-l", "python3.8-dev", "python3.11-dev", "python3.13-dev", "libevdev-dev", "build-essential"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Если команда не выполнилась успешно, возможно пакеты не установлены
            if result.returncode != 0:
                dependencies_installed = False
        except Exception:
            dependencies_installed = False
    
    # Если зависимости не установлены - устанавливаем их
    if not dependencies_installed:
        if args.debug:
            print("Installing system dependencies...", flush=True)
        try:
            install_dependencies_offline()
        except Exception as e:
            if args.debug:
                print(f"Warning: Failed to install dependencies: {e}", flush=True)
    
    # Если автозапуск не настроен - настраиваем его
    if not autostart_configured:
        if args.debug:
            print("Setting up autostart...", flush=True)
        try:
            setup_autostart()
        except Exception as e:
            if args.debug:
                print(f"Warning: Failed to setup autostart: {e}", flush=True)
    
    # Определяем версию Python для использования
    python_version = args.version
    if not python_version:
        # Ищем первую доступную готовую версию Python
        available_versions = get_available_python_versions()
        for version in ["3.13", "3.11", "3.8"]:
            if version in available_versions:
                venv_check = Path(f"venv-{version}")
                venv_ready_check = venv_check / ".ready"
                if venv_check.exists() and venv_ready_check.exists():
                    python_version = version
                    break
        
        # Если не нашли готовую версию, используем первую доступную
        if not python_version and available_versions:
            python_version = available_versions[0]
    
    if not python_version:
        print("Error: No Python version available", flush=True)
        sys.exit(1)
    
    if args.debug:
        print(f"Using Python version: {python_version}", flush=True)
        print(f"Autostart configured: {autostart_configured}", flush=True)
        print(f"Dependencies installed: {dependencies_installed}", flush=True)
    
    _sig_received = False
    
    def signal_handler(signum, frame):
        global _sig_received
        if _sig_received:
            return
        _sig_received = True
        try:
            cleanup_ports()
        finally:
            # Hard-exit to guarantee fast shutdown on systemctl stop/restart.
            os._exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main(python_version, debug=args.debug)
        sys.exit(0)
    except KeyboardInterrupt:
        cleanup_ports()
        sys.exit(0)
    except SystemExit:
        cleanup_ports()
        raise
    except Exception as _e:
        import traceback
        print(f"[RGW2] FATAL ERROR: {_e}", flush=True)
        traceback.print_exc()
        cleanup_ports()
        sys.exit(1)

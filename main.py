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
    и устанавливает зависимости из requirements.txt ОДИН РАЗ.
    Использует Python 3.11 для совместимости с симулятором.
    
    КРИТИЧНО: Автоматически пересоздает venv при:
    - Изменении версии Python (мажорной или минорной)
    - Наличии флага data/.recreate_venv (создается при обновлении requirements.txt или main.py)
    - Отсутствии venv
    - Несоответствии версии Python в существующем venv
    - Отсутствии флага готовности venv/.ready
    
    Returns:
        True если окружение готово, False при ошибке
    """
    venv_name = "venv"
    venv_path = Path(venv_name)
    requirements_file = Path("requirements.txt")
    venv_ready_flag = venv_path / ".ready"
    system_deps_flag = Path("data/.system_deps_installed")
    
    if is_windows():
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        python_path = venv_path / "bin" / "python"
    
    if venv_path.exists() and venv_ready_flag.exists() and python_path.exists():
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
        
        print("Virtual environment is ready, using existing setup", flush=True)
        return True
    
    python311_paths = [
        "/usr/bin/python3.11",
        "/usr/local/bin/python3.11",
        "/home/g100/miniconda3/envs/env-isaaclab/bin/python",
        "/home/g100/miniconda3/bin/python3.11",
    ]
    
    python311 = None
    for path in python311_paths:
        if Path(path).exists():
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if "3.11" in result.stdout or "3.11" in result.stderr:
                    python311 = path
                    print(f"Found Python 3.11 at: {python311}", flush=True)
                    break
            except:
                continue
    
    if not python311:
        print("Warning: Python 3.11 not found, using default Python", flush=True)
        python311 = sys.executable
    
    if is_windows():
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"
    
    venv_recreate_flag = Path("data/.recreate_venv")
    if venv_recreate_flag.exists():
        print("Venv recreation flag detected. Will recreate virtual environment...", flush=True)
        if venv_path.exists():
            print("Removing existing virtual environment...", flush=True)
            try:
                import shutil
                shutil.rmtree(venv_path)
                print("Old virtual environment removed", flush=True)
            except Exception as e:
                print(f"Warning: Error removing old venv: {e}", flush=True)
        try:
            venv_recreate_flag.unlink()
            print("Venv recreation flag removed", flush=True)
        except Exception:
            pass
    
    need_recreate = False
    
    if not venv_path.exists():
        need_recreate = True
        print("Virtual environment not found, will create new one", flush=True)
    else:
        try:
            result_target = subprocess.run(
                [python311, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            target_version = result_target.stdout.strip() if result_target.returncode == 0 else None
            
            if python_path.exists():
                result_venv = subprocess.run(
                    [str(python_path), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                venv_version = result_venv.stdout.strip() if result_venv.returncode == 0 else None
                
                print(f"Target Python version: {target_version}", flush=True)
                print(f"Venv Python version: {venv_version}", flush=True)
                
                if target_version and venv_version:
                    import re
                    target_match = re.search(r'(\d+)\.(\d+)', target_version)
                    venv_match = re.search(r'(\d+)\.(\d+)', venv_version)
                    
                    if target_match and venv_match:
                        target_major_minor = f"{target_match.group(1)}.{target_match.group(2)}"
                        venv_major_minor = f"{venv_match.group(1)}.{venv_match.group(2)}"
                        
                        if target_major_minor != venv_major_minor:
                            print(f"Python version mismatch detected: venv={venv_major_minor}, required={target_major_minor}", flush=True)
                            print("Recreating virtual environment...", flush=True)
                            need_recreate = True
                        else:
                            print(f"Python version matches: {target_major_minor}", flush=True)
                    else:
                        print("Warning: Could not parse Python versions, will check venv integrity", flush=True)
                else:
                    print("Warning: Could not determine Python versions, will check venv integrity", flush=True)
            else:
                print("Python executable not found in venv, will recreate", flush=True)
                need_recreate = True
        except Exception as e:
            print(f"Warning: Error checking Python version: {e}, will check venv integrity", flush=True)
    
    if need_recreate:
        if venv_path.exists():
            print("Removing old virtual environment...", flush=True)
            try:
                import shutil
                if venv_ready_flag.exists():
                    venv_ready_flag.unlink()
                shutil.rmtree(venv_path)
            except Exception as e:
                print(f"Warning: Error removing old venv: {e}", flush=True)
        
        print(f"Creating virtual environment with {python311}...", flush=True)
        try:
            subprocess.run(
                [python311, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True
            )
            print("Virtual environment created successfully", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"Error creating venv: {e}", flush=True)
            if e.stdout:
                print(f"stdout: {e.stdout.decode()}", flush=True)
            if e.stderr:
                print(f"stderr: {e.stderr.decode()}", flush=True)
            return False
    
    if venv_ready_flag.exists() and not need_recreate:
        print("Virtual environment is ready, skipping dependency installation", flush=True)
    elif requirements_file.exists():
        try:
            print("Installing dependencies from requirements.txt (this may take a while)...", flush=True)
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip", "setuptools", "wheel"],
                check=False,
                capture_output=True,
                timeout=300
            )
            result = subprocess.run(
                [str(pip_path), "install", "-r", str(requirements_file)],
                check=True,
                capture_output=True,
                text=True,
                timeout=600
            )
            print("Dependencies installed successfully", flush=True)
            venv_ready_flag.touch()
            print("Venv ready flag created", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"Error installing dependencies: {e}", flush=True)
            if e.stdout:
                print(f"stdout: {e.stdout[:1000]}", flush=True)
            if e.stderr:
                print(f"stderr: {e.stderr[:1000]}", flush=True)
            return False
        except subprocess.TimeoutExpired:
            print("Timeout installing dependencies (this may be normal for cyclonedds compilation)", flush=True)
            return False
    else:
        print(f"Warning: {requirements_file} not found", flush=True)
    
    if not is_windows():
        if system_deps_flag.exists():
            print("System dependencies already installed, skipping", flush=True)
        else:
            try:
                print("Installing cyclonedds system dependencies (one-time setup)...", flush=True)
                subprocess.run(
                    ["sudo", "apt-get", "update"],
                    check=False,
                    capture_output=True,
                    timeout=60
                )
                install_result = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", "libddsc0t64", "cyclonedds-dev", "build-essential", "cmake", "libssl-dev"],
                    check=False,
                    capture_output=True,
                    timeout=300
                )
                stdout_output = install_result.stdout.decode() if install_result.stdout else ''
                stderr_output = install_result.stderr.decode() if install_result.stderr else ''
                
                if install_result.returncode == 0 or "libddsc0t64" in stdout_output or "cyclonedds-dev" in stdout_output:
                    print("System dependencies installed", flush=True)
                    
                    libddsc_so0 = Path("/usr/lib/x86_64-linux-gnu/libddsc.so.0")
                    libddsc_so0debian = Path("/usr/lib/x86_64-linux-gnu/libddsc.so.0debian")
                    
                    if libddsc_so0debian.exists() and not libddsc_so0.exists():
                        try:
                            subprocess.run(
                                ["sudo", "ln", "-sf", str(libddsc_so0debian), str(libddsc_so0)],
                                check=False,
                                capture_output=True,
                                timeout=10
                            )
                            print("Created libddsc.so.0 symlink", flush=True)
                        except Exception:
                            pass
                    
                    subprocess.run(
                        ["sudo", "ldconfig"],
                        check=False,
                        capture_output=True,
                        timeout=30
                    )
                    print("Library cache updated", flush=True)
                    system_deps_flag.parent.mkdir(parents=True, exist_ok=True)
                    system_deps_flag.touch()
                    print("System dependencies flag created", flush=True)
                else:
                    print(f"Warning: Some packages may not have installed: {stderr_output[:500] if stderr_output else 'Unknown error'}", flush=True)
            except Exception as e:
                print(f"Warning: Could not install system dependencies: {e}", flush=True)
    
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import requests, numpy, flask; print('Core dependencies OK')"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("Core dependencies verified", flush=True)
        else:
            print(f"Warning: Some dependencies may be missing: {result.stderr}", flush=True)
            if "numpy" in result.stderr or "flask" in result.stderr:
                print("CRITICAL: Core dependencies missing. Installing...", flush=True)
                try:
                    install_result = subprocess.run(
                        [str(pip_path), "install", "-r", str(requirements_file)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    if install_result.returncode == 0:
                        print("Dependencies installed successfully", flush=True)
                    else:
                        print(f"Failed to install dependencies: {install_result.stderr[:500]}", flush=True)
                        return False
                except Exception as install_e:
                    print(f"Error installing dependencies: {install_e}", flush=True)
                    return False
    except Exception as e:
        print(f"Warning: Could not verify dependencies: {e}", flush=True)
        
        try:
            lib_paths = []
            for path in ["/usr/lib/x86_64-linux-gnu", "/usr/local/lib", "/lib/x86_64-linux-gnu"]:
                if Path(path).exists():
                    lib_paths.append(path)
            
            find_cmd = ["find", "/usr", "-name", "libddsc.so*", "-type", "f", "2>/dev/null"]
            result = subprocess.run(
                " ".join(find_cmd),
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            env = os.environ.copy()
            ld_library_path = env.get("LD_LIBRARY_PATH", "")
            
            if result.returncode == 0 and result.stdout.strip():
                found_libs = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                if found_libs:
                    print(f"Found cyclonedds libraries: {found_libs[0]}", flush=True)
                    lib_dir = str(Path(found_libs[0]).parent)
                    if lib_dir not in ld_library_path:
                        ld_library_path = f"{ld_library_path}:{lib_dir}" if ld_library_path else lib_dir
            
            for lib_path in lib_paths:
                if lib_path not in ld_library_path:
                    ld_library_path = f"{ld_library_path}:{lib_path}" if ld_library_path else lib_path
            
            env["LD_LIBRARY_PATH"] = ld_library_path
            
            result = subprocess.run(
                [str(python_path), "-c", "import cyclonedds; print('cyclonedds OK')"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env
            )
            if result.returncode == 0:
                print("cyclonedds verified successfully", flush=True)
                os.environ["LD_LIBRARY_PATH"] = ld_library_path
            else:
                print(f"Warning: cyclonedds import failed: {result.stderr[:500] if result.stderr else 'No error message'}", flush=True)
                print(f"LD_LIBRARY_PATH set to: {ld_library_path}", flush=True)
                os.environ["LD_LIBRARY_PATH"] = ld_library_path
        except Exception as e:
            print(f"Warning: Could not verify cyclonedds: {e}", flush=True)
    
    try:
        result = subprocess.run(
            [str(python_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            venv_info_file = venv_path / ".python_version"
            with open(venv_info_file, 'w') as f:
                f.write(result.stdout.strip())
    except Exception:
        pass
    
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
        
        try:
            check_and_update_version()
        except Exception as e:
            print(f"Warning: Failed to check/update version: {e}", flush=True)
        
        try:
            manager = services_manager.get_services_manager()
            manager.refresh_services()
        except Exception as e:
            print(f"Warning: Failed to initialize services manager: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    
        if not in_docker:
            if not setup_virtual_environment():
                print("ERROR: Virtual environment setup failed", flush=True)
                sys.exit(1)
            
            venv_path = Path("venv").resolve()
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
                
                if not venv_same:
                    print(f"Switching to venv Python: {venv_python_resolved} (current: {current_python})", flush=True)
                    os.execv(str(venv_python_resolved), [str(venv_python_resolved)] + sys.argv)
        
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
    except Exception as e:
        print(f"Fatal error in main(): {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        raise


if __name__ == '__main__':
    import signal
    
    _sig_received = False
    
    def signal_handler(signum, frame):
        global _sig_received
        print(f"\n\nApplication received signal {signum}", flush=True)
        
        try:
            manager = services_manager.get_services_manager()
            motor_service_info = manager.get_service("unitree_motor_control")
            motor_status = motor_service_info.get("status", "OFF") if motor_service_info else "OFF"
        except Exception:
            motor_status = "OFF"
        
        if motor_status == "OFF":
            print(f"Motor service is OFF. Shutting down application...", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            sys.exit(0)
        
        if not _sig_received:
            _sig_received = True
            print(f"First SIG received. Stopping all services except motors and web...", flush=True)
            try:
                import run
                runner = run.ServiceRunner()
                runner.running = False
                
                manager = services_manager.get_services_manager()
                all_services = manager.discover_services()
                
                critical_services = {"unitree_motor_control", "web"}
                
                for service_name in all_services:
                    if service_name not in critical_services:
                        try:
                            service_info = manager.get_service(service_name)
                            if service_info.get("status") == "ON":
                                print(f"Stopping service: {service_name}", flush=True)
                                depending_services = manager.get_services_depending_on(service_name)
                                if depending_services:
                                    for dep in depending_services:
                                        if dep not in critical_services:
                                            dep_info = manager.get_service(dep)
                                            if dep_info.get("status") == "ON":
                                                print(f"  Stopping depending service: {dep}", flush=True)
                                                manager.update_service_status(dep, "OFF")
                                manager.update_service_status(service_name, "OFF")
                        except Exception as e:
                            print(f"Warning: Could not stop service {service_name}: {e}", flush=True)
                
                print("All non-critical services stopped. Motor and web services continue running.", flush=True)
                print("To shutdown motor service, send 3 consecutive OFF requests via API.", flush=True)
            except Exception as e:
                print(f"Warning: Error stopping services: {e}", flush=True)
            
            sys.stdout.flush()
            sys.stderr.flush()
            return
        
        print(f"Second SIG received. Motor service is still ON. Ignoring (motor service protection).", flush=True)
        print(f"To shutdown motor service, send 3 consecutive OFF requests via API.", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        print("main.py starting...", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        main()
        print("main.py completed (this should not happen - services should run forever)", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\nApplication stopped by user (KeyboardInterrupt)", flush=True)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nFatal error: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)

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
                    break
            except:
                continue
    
    if not python311:
        python311 = sys.executable
    
    if is_windows():
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"
    
    venv_recreate_flag = Path("data/.recreate_venv")
    if venv_recreate_flag.exists():
        if venv_path.exists():
            try:
                import shutil
                shutil.rmtree(venv_path)
            except Exception:
                pass
        try:
            venv_recreate_flag.unlink()
        except Exception:
            pass
    
    need_recreate = False
    
    if not venv_path.exists():
        need_recreate = True
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
                
                if target_version and venv_version:
                    import re
                    target_match = re.search(r'(\d+)\.(\d+)', target_version)
                    venv_match = re.search(r'(\d+)\.(\d+)', venv_version)
                    
                    if target_match and venv_match:
                        target_major_minor = f"{target_match.group(1)}.{target_match.group(2)}"
                        venv_major_minor = f"{venv_match.group(1)}.{venv_match.group(2)}"
                        
                        if target_major_minor != venv_major_minor:
                            need_recreate = True
                else:
                    need_recreate = True
            else:
                need_recreate = True
        except Exception:
            pass
    
    if need_recreate:
        if venv_path.exists():
            try:
                import shutil
                if venv_ready_flag.exists():
                    venv_ready_flag.unlink()
                shutil.rmtree(venv_path)
            except Exception:
                pass
        
        try:
            subprocess.run(
                [python311, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True
            )
        except subprocess.CalledProcessError:
            return False
    
    if venv_ready_flag.exists() and not need_recreate:
        pass
    elif requirements_file.exists():
        try:
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
            venv_ready_flag.touch()
        except subprocess.CalledProcessError:
            return False
        except subprocess.TimeoutExpired:
            return False
    
    if not is_windows():
        if not system_deps_flag.exists():
            try:
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
                
                if install_result.returncode == 0 or "libddsc0t64" in stdout_output or "cyclonedds-dev" in stdout_output:
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
                        except Exception:
                            pass
                    
                    subprocess.run(
                        ["sudo", "ldconfig"],
                        check=False,
                        capture_output=True,
                        timeout=30
                    )
                    system_deps_flag.parent.mkdir(parents=True, exist_ok=True)
                    system_deps_flag.touch()
            except Exception:
                pass
    
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import requests, numpy, flask; print('Core dependencies OK')"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            if "numpy" in result.stderr or "flask" in result.stderr:
                try:
                    install_result = subprocess.run(
                        [str(pip_path), "install", "-r", str(requirements_file)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
                    if install_result.returncode != 0:
                        return False
                except Exception:
                    return False
    except Exception:
        pass
        
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
            os.environ["LD_LIBRARY_PATH"] = ld_library_path
        except Exception:
            pass
    
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
    """Проверяет и обновляет версию проекта."""
    try:
        import update
        return update.check_and_update_version()
    except Exception:
        return False


def run_update():
    """Запускает обновление системы."""
    try:
        import update
        return update.update_system()
    except Exception:
        return False


def run_services():
    """Запускает все сервисы."""
    try:
        import run
        run.run_services()
        return True
    except KeyboardInterrupt:
        return True
    except Exception:
        return False


def main():
    """Главная функция приложения."""
    try:
        
        try:
            check_and_update_version()
        except Exception:
            pass
        
        try:
            manager = services_manager.get_services_manager()
            manager.refresh_services()
        except Exception:
            pass
        
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER') == 'true'
    
        if not in_docker:
            if not setup_virtual_environment():
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
            api_port = web_params.get("api_port", 5000)
            ports_to_clean.add(web_port)
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
    
    _sig_received = False
    
    def signal_handler(signum, frame):
        global _sig_received
        
        try:
            manager = services_manager.get_services_manager()
            motor_service_info = manager.get_service("unitree_motor_control")
            motor_status = motor_service_info.get("status", "OFF") if motor_service_info else "OFF"
        except Exception:
            motor_status = "OFF"
        
        if motor_status == "OFF":
            cleanup_ports()
            sys.exit(0)
        
        if not _sig_received:
            _sig_received = True
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
                                depending_services = manager.get_services_depending_on(service_name)
                                if depending_services:
                                    for dep in depending_services:
                                        if dep not in critical_services:
                                            dep_info = manager.get_service(dep)
                                            if dep_info.get("status") == "ON":
                                                manager.update_service_status(dep, "OFF")
                                manager.update_service_status(service_name, "OFF")
                        except Exception:
                            pass
            except Exception:
                pass
            return
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main()
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        cleanup_ports()
        sys.exit(0)
    except SystemExit:
        cleanup_ports()
        raise
    except Exception:
        cleanup_ports()
        sys.exit(1)

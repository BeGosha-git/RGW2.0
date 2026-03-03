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
import re
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
    
    # Определяем фактическую версию Python, которая будет использоваться
    try:
        version_result = subprocess.run(
            [python311, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        actual_python_version = "3.8"  # по умолчанию
        if version_result.returncode == 0:
            import re
            version_match = re.search(r'(\d+)\.(\d+)', version_result.stdout)
            if version_match:
                actual_python_version = f"{version_match.group(1)}.{version_match.group(2)}"
    except Exception:
        actual_python_version = "3.8"
    
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
    
    if need_recreate or (venv_path.exists() and not pip_path.exists()):
        if venv_path.exists():
            try:
                import shutil
                if venv_ready_flag.exists():
                    venv_ready_flag.unlink()
                shutil.rmtree(venv_path)
            except Exception:
                pass
        
        # Проверяем и устанавливаем python3-venv если нужно
        if not is_windows():
            try:
                # Используем фактическую версию Python для установки правильного пакета
                python_major_minor = actual_python_version
                python_version = f"python{actual_python_version}-venv"
                
                # Проверяем наличие ensurepip (который нужен для создания venv)
                ensurepip_check = subprocess.run(
                    [python311, "-c", "import ensurepip"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                # Если ensurepip недоступен, устанавливаем python3-venv
                if ensurepip_check.returncode != 0:
                    print(f"ensurepip not available. Installing {python_version} package...", flush=True)
                    
                    # Пробуем офлайн установку сначала
                    offline_dir = Path("offline_packages")
                    installed_offline = False
                    
                    if offline_dir.exists():
                        # Ищем пакет для конкретной версии Python
                        deb_files = []
                        # Пробуем точное совпадение версии
                        version_patterns = [
                            f"*python{python_major_minor.replace('.', '_')}*venv*.deb",
                            f"*python{python_major_minor.replace('.', '.')}*venv*.deb",
                            f"*python{python_major_minor}*venv*.deb",
                        ]
                        for pattern in version_patterns:
                            deb_files = list(offline_dir.glob(pattern))
                            if deb_files:
                                break
                        
                        # Если не нашли точное совпадение, пробуем найти совместимый пакет
                        if not deb_files:
                            # Ищем пакет для той же мажорной версии
                            major_version = python_major_minor.split('.')[0]
                            deb_files = list(offline_dir.glob(f"*python{major_version}.*venv*.deb"))
                        
                        # Если все еще не нашли, пробуем любой python*-venv пакет
                        if not deb_files:
                            all_venv_debs = list(offline_dir.glob("*python*venv*.deb"))
                            # Предпочитаем пакеты с меньшей версией (более совместимые)
                            if all_venv_debs:
                                # Сортируем по имени и берем первый (обычно это более старая версия)
                                all_venv_debs.sort(key=lambda x: x.name)
                                deb_files = [all_venv_debs[0]]
                        
                        if deb_files:
                            found_pkg = deb_files[0]
                            print(f"Found offline package: {found_pkg.name}, installing...", flush=True)
                            print(f"Note: Installing {found_pkg.name} for Python {python_major_minor} (package may be for different version)", flush=True)
                            try:
                                install_result = subprocess.run(
                                    ["sudo", "dpkg", "-i", str(found_pkg)],
                                    capture_output=True,
                                    text=True,
                                    timeout=120
                                )
                                if install_result.returncode == 0:
                                    # Проверяем, что ensurepip теперь доступен
                                    check_result = subprocess.run(
                                        [python311, "-c", "import ensurepip"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    if check_result.returncode == 0:
                                        installed_offline = True
                                        print(f"Successfully installed {found_pkg.name} from offline package, ensurepip now available", flush=True)
                                    else:
                                        print(f"Warning: Package {found_pkg.name} installed but ensurepip still not available for Python {python_major_minor}", flush=True)
                                        # Пробуем исправить зависимости
                                        print("Fixing package dependencies...", flush=True)
                                        fix_result = subprocess.run(
                                            ["sudo", "apt-get", "install", "-f", "-y"],
                                            capture_output=True,
                                            text=True,
                                            timeout=120
                                        )
                                        # Проверяем снова после исправления зависимостей
                                        check_result2 = subprocess.run(
                                            [python311, "-c", "import ensurepip"],
                                            capture_output=True,
                                            text=True,
                                            timeout=5
                                        )
                                        if check_result2.returncode == 0:
                                            installed_offline = True
                                            print(f"Package dependencies fixed, ensurepip now available", flush=True)
                                        else:
                                            print(f"Warning: ensurepip still not available after fixing dependencies", flush=True)
                                else:
                                    # Пробуем исправить зависимости
                                    print("Fixing package dependencies...", flush=True)
                                    fix_result = subprocess.run(
                                        ["sudo", "apt-get", "install", "-f", "-y"],
                                        capture_output=True,
                                        text=True,
                                        timeout=120
                                    )
                                    # Проверяем, установился ли нужный пакет после исправления зависимостей
                                    check_result = subprocess.run(
                                        [python311, "-c", "import ensurepip"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    if check_result.returncode == 0:
                                        installed_offline = True
                                        print(f"Package dependencies fixed, ensurepip now available", flush=True)
                                    else:
                                        print(f"Warning: Package installed but ensurepip still not available", flush=True)
                            except Exception as e:
                                print(f"Warning: Offline installation failed: {e}", flush=True)
                    
                    # Если офлайн не сработал или ensurepip все еще недоступен, пробуем онлайн
                    if not installed_offline:
                        # Проверяем еще раз, может быть пакет уже установлен системно
                        final_check = subprocess.run(
                            [python311, "-c", "import ensurepip"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if final_check.returncode == 0:
                            installed_offline = True
                            print(f"ensurepip is now available (may have been installed by dependencies)", flush=True)
                        else:
                            print(f"Trying online installation of {python_version}...", flush=True)
                            install_result = subprocess.run(
                                ["sudo", "apt-get", "install", "-y", python_version],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                            if install_result.returncode != 0:
                                print(f"Warning: Failed to install {python_version}. Trying to create venv without pip...", flush=True)
                                if install_result.stdout:
                                    stdout_preview = install_result.stdout[:500] if len(install_result.stdout) > 500 else install_result.stdout
                                    print(f"Install stdout preview: {stdout_preview}", flush=True)
                                if install_result.stderr:
                                    stderr_preview = install_result.stderr[:500] if len(install_result.stderr) > 500 else install_result.stderr
                                    print(f"Install stderr preview: {stderr_preview}", flush=True)
                                # Пробуем создать venv без ensurepip
                                print(f"Attempting to create venv without pip (will install pip manually)...", flush=True)
                                try:
                                    result_no_pip = subprocess.run(
                                        [python311, "-m", "venv", str(venv_path), "--without-pip"],
                                        check=True,
                                        capture_output=True,
                                        text=True,
                                        timeout=60
                                    )
                                    print(f"Successfully created venv without pip", flush=True)
                                    # Устанавливаем pip вручную после создания venv
                                    pip_path_venv = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                                    if not pip_path_venv.exists():
                                        print("Installing pip manually...", flush=True)
                                        # Сначала пробуем из офлайн-пакетов
                                        offline_dir = Path("offline_packages")
                                        pip_installed = False
                                        
                                        if offline_dir.exists():
                                            # Ищем get-pip.py в офлайн-пакетах
                                            get_pip_offline = offline_dir / "get-pip.py"
                                            if get_pip_offline.exists():
                                                print(f"Found get-pip.py in offline packages: {get_pip_offline}", flush=True)
                                                try:
                                                    python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                    # Определяем версию Python в venv для правильного get-pip.py
                                                    venv_version_result = subprocess.run(
                                                        [str(python_venv), "--version"],
                                                        capture_output=True,
                                                        text=True,
                                                        timeout=5
                                                    )
                                                    venv_python_version = None
                                                    if venv_version_result.returncode == 0:
                                                        version_match = re.search(r'(\d+)\.(\d+)', venv_version_result.stdout)
                                                        if version_match:
                                                            venv_python_version = f"{version_match.group(1)}.{version_match.group(2)}"
                                                    
                                                    # Если Python 3.8, проверяем наличие правильной версии get-pip.py
                                                    if venv_python_version and venv_python_version.startswith("3.8"):
                                                        get_pip_38 = offline_dir / "get-pip-3.8.py"
                                                        if get_pip_38.exists():
                                                            get_pip_abs = get_pip_38.resolve()
                                                            print(f"Using Python 3.8 compatible get-pip.py: {get_pip_abs}", flush=True)
                                                        else:
                                                            print(f"Warning: Python 3.8 detected but get-pip-3.8.py not found. Trying standard get-pip.py...", flush=True)
                                                            get_pip_abs = get_pip_offline.resolve()
                                                    else:
                                                        get_pip_abs = get_pip_offline.resolve()
                                                    
                                                    print(f"Running: {python_venv} {get_pip_abs}", flush=True)
                                                    install_result = subprocess.run(
                                                        [str(python_venv), str(get_pip_abs)],
                                                        check=True,
                                                        capture_output=True,
                                                        text=True,
                                                        timeout=120
                                                    )
                                                    # Проверяем, что pip действительно установлен
                                                    pip_path_venv_check = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                                                    if pip_path_venv_check.exists():
                                                        print("pip installed successfully from offline package", flush=True)
                                                        pip_installed = True
                                                    else:
                                                        print("Warning: get-pip.py completed but pip not found in venv", flush=True)
                                                        if install_result.stdout:
                                                            print(f"get-pip stdout: {install_result.stdout[:500]}", flush=True)
                                                        if install_result.stderr:
                                                            print(f"get-pip stderr: {install_result.stderr[:500]}", flush=True)
                                                except subprocess.CalledProcessError as pip_err:
                                                    print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                                                    if hasattr(pip_err, 'stdout') and pip_err.stdout:
                                                        print(f"get-pip stdout: {pip_err.stdout[:500]}", flush=True)
                                                    if hasattr(pip_err, 'stderr') and pip_err.stderr:
                                                        print(f"get-pip stderr: {pip_err.stderr[:500]}", flush=True)
                                                    # Если это Python 3.8 и стандартный get-pip.py не работает, пробуем скачать правильную версию
                                                    if venv_python_version and venv_python_version.startswith("3.8") and check_internet():
                                                        try:
                                                            import urllib.request
                                                            get_pip_38_path = offline_dir / "get-pip-3.8.py"
                                                            print("Downloading Python 3.8 compatible get-pip.py...", flush=True)
                                                            urllib.request.urlretrieve("https://bootstrap.pypa.io/pip/3.8/get-pip.py", str(get_pip_38_path))
                                                            os.chmod(get_pip_38_path, 0o644)
                                                            print(f"Retrying with Python 3.8 compatible get-pip.py...", flush=True)
                                                            subprocess.run(
                                                                [str(python_venv), str(get_pip_38_path)],
                                                                check=True,
                                                                capture_output=True,
                                                                text=True,
                                                                timeout=120
                                                            )
                                                            pip_path_venv_check = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                                                            if pip_path_venv_check.exists():
                                                                print("pip installed successfully using Python 3.8 compatible get-pip.py", flush=True)
                                                                pip_installed = True
                                                        except Exception as pip38_err:
                                                            print(f"Warning: Could not install pip using Python 3.8 compatible version: {pip38_err}", flush=True)
                                                except Exception as pip_err:
                                                    print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                                            else:
                                                print(f"get-pip.py not found in offline packages: {get_pip_offline}", flush=True)
                                        else:
                                            print(f"Offline packages directory not found: {offline_dir}", flush=True)
                                        
                                        # Если не удалось из офлайн, пробуем через интернет (только если есть интернет)
                                        if not pip_installed:
                                            if check_internet():
                                                try:
                                                    import urllib.request
                                                    # Определяем версию Python в venv для правильного get-pip.py
                                                    python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                    venv_version_result = subprocess.run(
                                                        [str(python_venv), "--version"],
                                                        capture_output=True,
                                                        text=True,
                                                        timeout=5
                                                    )
                                                    venv_python_version = None
                                                    if venv_version_result.returncode == 0:
                                                        version_match = re.search(r'(\d+)\.(\d+)', venv_version_result.stdout)
                                                        if version_match:
                                                            venv_python_version = f"{version_match.group(1)}.{version_match.group(2)}"
                                                    
                                                    get_pip_script = venv_path / "get-pip.py"
                                                    # Для Python 3.8 используем специальный URL
                                                    if venv_python_version and venv_python_version.startswith("3.8"):
                                                        get_pip_url = "https://bootstrap.pypa.io/pip/3.8/get-pip.py"
                                                        print("Downloading Python 3.8 compatible get-pip.py from internet...", flush=True)
                                                    else:
                                                        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
                                                        print("Downloading get-pip.py from internet...", flush=True)
                                                    
                                                    urllib.request.urlretrieve(get_pip_url, str(get_pip_script))
                                                    subprocess.run(
                                                        [str(python_venv), str(get_pip_script)],
                                                        check=True,
                                                        capture_output=True,
                                                        text=True,
                                                        timeout=120
                                                    )
                                                    get_pip_script.unlink(missing_ok=True)
                                                    print("pip installed successfully from internet", flush=True)
                                                    pip_installed = True
                                                except Exception as pip_err:
                                                    print(f"Warning: Could not install pip manually: {pip_err}", flush=True)
                                                    print("Note: venv created without pip. You may need to install pip later or use offline packages.", flush=True)
                                            else:
                                                if offline_dir.exists() and (offline_dir / "get-pip.py").exists():
                                                    print("No internet connection and get-pip.py installation failed. Skipping pip installation.", flush=True)
                                                    print("Note: venv created without pip. You may need to install pip manually later.", flush=True)
                                                else:
                                                    print("No internet connection and get-pip.py not found in offline packages. Skipping pip installation.", flush=True)
                                                    print("Note: venv created without pip. You may need to install pip later or add get-pip.py to offline_packages/.", flush=True)
                                    # Помечаем, что venv уже создан
                                    venv_created_without_pip = True
                                except Exception as venv_err:
                                    print(f"Error: Failed to create venv even without pip: {venv_err}", flush=True)
                                    print(f"Please install manually: sudo apt-get install -y {python_version}", flush=True)
                                    print(f"Or run: python3 main.py --download-deps to download offline packages", flush=True)
                                    return False
                            
                            # Проверяем, что ensurepip теперь доступен
                            verify_check = subprocess.run(
                                [python311, "-c", "import ensurepip"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if verify_check.returncode == 0:
                                print(f"Successfully installed {python_version} from internet, ensurepip now available", flush=True)
                            else:
                                print(f"Warning: {python_version} installed but ensurepip still not available", flush=True)
                                print(f"Trying to install python3-venv (generic package)...", flush=True)
                                # Пробуем установить общий пакет python3-venv
                                generic_result = subprocess.run(
                                    ["sudo", "apt-get", "install", "-y", "python3-venv"],
                                    capture_output=True,
                                    text=True,
                                    timeout=120
                                )
                                if generic_result.returncode == 0:
                                    final_verify = subprocess.run(
                                        [python311, "-c", "import ensurepip"],
                                        capture_output=True,
                                        text=True,
                                        timeout=5
                                    )
                                    if final_verify.returncode == 0:
                                        print(f"Successfully installed python3-venv, ensurepip now available", flush=True)
                                    else:
                                        print(f"Error: ensurepip still not available after installing python3-venv", flush=True)
                                        # Пробуем создать venv без ensurepip (используя --without-pip)
                                        print(f"Attempting to create venv without pip (will install pip manually)...", flush=True)
                                        try:
                                            result_no_pip = subprocess.run(
                                                [python311, "-m", "venv", str(venv_path), "--without-pip"],
                                                check=True,
                                                capture_output=True,
                                                text=True,
                                                timeout=60
                                            )
                                            print(f"Successfully created venv without pip", flush=True)
                                            # Устанавливаем pip вручную после создания venv
                                            pip_path_venv = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                                            if not pip_path_venv.exists():
                                                print("Installing pip manually...", flush=True)
                                                # Сначала пробуем из офлайн-пакетов
                                                offline_dir_pip = Path("offline_packages")
                                                pip_installed = False
                                                
                                                if offline_dir_pip.exists():
                                                    get_pip_offline = offline_dir_pip / "get-pip.py"
                                                    if get_pip_offline.exists():
                                                        try:
                                                            python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                            subprocess.run(
                                                                [str(python_venv), str(get_pip_offline)],
                                                                check=True,
                                                                capture_output=True,
                                                                text=True,
                                                                timeout=120
                                                            )
                                                            print("pip installed successfully from offline package", flush=True)
                                                            pip_installed = True
                                                        except Exception as pip_err:
                                                            print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                                                
                                                # Если не удалось из офлайн, пробуем через интернет (только если есть интернет)
                                                if not pip_installed:
                                                    if check_internet():
                                                        try:
                                                            import urllib.request
                                                            get_pip_script = venv_path / "get-pip.py"
                                                            print("Downloading get-pip.py from internet...", flush=True)
                                                            urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", str(get_pip_script))
                                                            python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                            subprocess.run(
                                                                [str(python_venv), str(get_pip_script)],
                                                                check=True,
                                                                capture_output=True,
                                                                text=True,
                                                                timeout=120
                                                            )
                                                            get_pip_script.unlink(missing_ok=True)
                                                            print("pip installed successfully from internet", flush=True)
                                                            pip_installed = True
                                                        except Exception as pip_err:
                                                            print(f"Warning: Could not install pip manually: {pip_err}", flush=True)
                                                            print("Note: venv created without pip. You may need to install pip later or use offline packages.", flush=True)
                                                    else:
                                                        if offline_dir_pip.exists() and (offline_dir_pip / "get-pip.py").exists():
                                                            print("No internet connection and get-pip.py installation failed. Skipping pip installation.", flush=True)
                                                            print("Note: venv created without pip. You may need to install pip manually later.", flush=True)
                                                        else:
                                                            print("No internet connection and get-pip.py not found in offline packages. Skipping pip installation.", flush=True)
                                                            print("Note: venv created without pip. You may need to install pip later or add get-pip.py to offline_packages/.", flush=True)
                                            # Помечаем, что venv уже создан
                                            venv_created_without_pip = True
                                        except Exception as venv_err:
                                            print(f"Error: Failed to create venv even without pip: {venv_err}", flush=True)
                                            return False
                                else:
                                    print(f"Error: Failed to install python3-venv", flush=True)
                                    # Пробуем создать venv без ensurepip
                                    print(f"Attempting to create venv without pip (will install pip manually)...", flush=True)
                                    try:
                                        result_no_pip = subprocess.run(
                                            [python311, "-m", "venv", str(venv_path), "--without-pip"],
                                            check=True,
                                            capture_output=True,
                                            text=True,
                                            timeout=60
                                        )
                                        print(f"Successfully created venv without pip", flush=True)
                                        # Устанавливаем pip вручную после создания venv
                                        pip_path_venv = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                                        if not pip_path_venv.exists():
                                            print("Installing pip manually...", flush=True)
                                            # Сначала пробуем из офлайн-пакетов
                                            offline_dir_pip = Path("offline_packages")
                                            pip_installed = False
                                            
                                            if offline_dir_pip.exists():
                                                get_pip_offline = offline_dir_pip / "get-pip.py"
                                                if get_pip_offline.exists():
                                                    try:
                                                        python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                        subprocess.run(
                                                            [str(python_venv), str(get_pip_offline)],
                                                            check=True,
                                                            capture_output=True,
                                                            text=True,
                                                            timeout=120
                                                        )
                                                        print("pip installed successfully from offline package", flush=True)
                                                        pip_installed = True
                                                    except Exception as pip_err:
                                                        print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                                            
                                            # Если не удалось из офлайн, пробуем через интернет (только если есть интернет)
                                            if not pip_installed:
                                                if check_internet():
                                                    try:
                                                        import urllib.request
                                                        get_pip_script = venv_path / "get-pip.py"
                                                        print("Downloading get-pip.py from internet...", flush=True)
                                                        urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", str(get_pip_script))
                                                        python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                                        subprocess.run(
                                                            [str(python_venv), str(get_pip_script)],
                                                            check=True,
                                                            capture_output=True,
                                                            text=True,
                                                            timeout=120
                                                        )
                                                        get_pip_script.unlink(missing_ok=True)
                                                        print("pip installed successfully from internet", flush=True)
                                                        pip_installed = True
                                                    except Exception as pip_err:
                                                        print(f"Warning: Could not install pip manually: {pip_err}", flush=True)
                                                        print("Note: venv created without pip. You may need to install pip later or use offline packages.", flush=True)
                                                else:
                                                    print("No internet connection and get-pip.py not found in offline packages. Skipping pip installation.", flush=True)
                                                    print("Note: venv created without pip. You may need to install pip later or add get-pip.py to offline_packages/.", flush=True)
                                        # Помечаем, что venv уже создан
                                        venv_created_without_pip = True
                                    except Exception as venv_err:
                                        print(f"Error: Failed to create venv even without pip: {venv_err}", flush=True)
                                        return False
            except Exception as e:
                print(f"Warning: Could not check/install python3-venv: {e}. Trying to continue...", flush=True)
        
        # Проверяем, был ли venv уже создан в fallback-блоке
        venv_created_without_pip = False
        if venv_path.exists() and (venv_path / "bin" / "python").exists() if not is_windows() else (venv_path / "Scripts" / "python.exe").exists():
            venv_created_without_pip = True
            print("venv already created (without pip), skipping creation", flush=True)
        
        if not venv_created_without_pip:
            try:
                result = subprocess.run(
                    [python311, "-m", "venv", str(venv_path)],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                print(f"Error creating virtual environment: {e}", flush=True)
                if e.stdout:
                    print(f"Error details: {e.stdout}", flush=True)
                if e.stderr:
                    print(f"Error stderr: {e.stderr}", flush=True)
                # Пробуем создать venv без pip как последнюю попытку
                print(f"Attempting to create venv without pip as last resort...", flush=True)
                try:
                    result_no_pip = subprocess.run(
                        [python311, "-m", "venv", str(venv_path), "--without-pip"],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    print(f"Successfully created venv without pip", flush=True)
                    # Устанавливаем pip вручную после создания venv
                    pip_path_venv = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                    if not pip_path_venv.exists():
                        print("Installing pip manually...", flush=True)
                        # Сначала пробуем из офлайн-пакетов
                        offline_dir_pip = Path("offline_packages")
                        pip_installed = False
                        
                        if offline_dir_pip.exists():
                            get_pip_offline = offline_dir_pip / "get-pip.py"
                            if get_pip_offline.exists():
                                try:
                                    python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                    subprocess.run(
                                        [str(python_venv), str(get_pip_offline)],
                                        check=True,
                                        capture_output=True,
                                        text=True,
                                        timeout=120
                                    )
                                    print("pip installed successfully from offline package", flush=True)
                                    pip_installed = True
                                except Exception as pip_err:
                                    print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                        
                        # Если не удалось из офлайн, пробуем через интернет (только если есть интернет)
                        if not pip_installed:
                            if check_internet():
                                try:
                                    import urllib.request
                                    get_pip_script = venv_path / "get-pip.py"
                                    print("Downloading get-pip.py from internet...", flush=True)
                                    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", str(get_pip_script))
                                    python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                                    subprocess.run(
                                        [str(python_venv), str(get_pip_script)],
                                        check=True,
                                        capture_output=True,
                                        text=True,
                                        timeout=120
                                    )
                                    get_pip_script.unlink(missing_ok=True)
                                    print("pip installed successfully from internet", flush=True)
                                    pip_installed = True
                                except Exception as pip_err:
                                    print(f"Warning: Could not install pip manually: {pip_err}", flush=True)
                                    print("Note: venv created without pip. You may need to install pip later or use offline packages.", flush=True)
                            else:
                                print("No internet connection and get-pip.py not found in offline packages. Skipping pip installation.", flush=True)
                                print("Note: venv created without pip. You may need to install pip later or add get-pip.py to offline_packages/.", flush=True)
                except Exception as venv_err:
                    print(f"Error: Failed to create venv even without pip: {venv_err}", flush=True)
                    return False
    
    if venv_ready_flag.exists() and not need_recreate:
        # Проверяем наличие venv.tar.gz и создаем если нет
        venv_archive = Path("venv.tar.gz")
        if not venv_archive.exists():
            try:
                import update
                print("venv.tar.gz not found, creating archive...", flush=True)
                if update.ensure_venv_archive(Path(".")):
                    print("venv.tar.gz archive created successfully", flush=True)
                else:
                    print("Warning: Failed to create venv.tar.gz archive", flush=True)
            except Exception as e:
                print(f"Warning: Could not create venv.tar.gz archive: {e}", flush=True)
    elif requirements_file.exists():
        if not pip_path.exists():
            # Если venv создан без pip, но pip не установлен, пробуем установить из офлайн-пакетов
            if venv_path.exists():
                offline_dir = Path("offline_packages")
                pip_installed = False
                
                if offline_dir.exists():
                    # Определяем версию Python в venv для правильного get-pip.py
                    python_venv = venv_path / "bin" / "python" if not is_windows() else venv_path / "Scripts" / "python.exe"
                    venv_version_result = subprocess.run(
                        [str(python_venv), "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    venv_python_version = None
                    if venv_version_result.returncode == 0:
                        version_match = re.search(r'(\d+)\.(\d+)', venv_version_result.stdout)
                        if version_match:
                            venv_python_version = f"{version_match.group(1)}.{version_match.group(2)}"
                    
                    # Пробуем сначала версию для Python 3.8, если это Python 3.8
                    get_pip_offline = None
                    if venv_python_version and venv_python_version.startswith("3.8"):
                        get_pip_38 = offline_dir / "get-pip-3.8.py"
                        if get_pip_38.exists():
                            get_pip_offline = get_pip_38
                            print(f"Found Python 3.8 compatible get-pip.py: {get_pip_offline}", flush=True)
                    
                    # Если не нашли версию для 3.8, пробуем стандартную
                    if not get_pip_offline:
                        get_pip_standard = offline_dir / "get-pip.py"
                        if get_pip_standard.exists():
                            get_pip_offline = get_pip_standard
                    
                    if get_pip_offline and get_pip_offline.exists():
                        print("pip not found, trying to install from offline package...", flush=True)
                        try:
                            subprocess.run(
                                [str(python_venv), str(get_pip_offline)],
                                check=True,
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                            pip_path_venv_check = venv_path / "bin" / "pip" if not is_windows() else venv_path / "Scripts" / "pip.exe"
                            if pip_path_venv_check.exists():
                                print("pip installed successfully from offline package", flush=True)
                                pip_installed = True
                            else:
                                print("Warning: get-pip.py completed but pip not found in venv", flush=True)
                        except Exception as pip_err:
                            print(f"Warning: Could not install pip from offline package: {pip_err}", flush=True)
                
                # Если pip все еще не установлен, устанавливаем пакеты напрямую из офлайн-пакетов
                if not pip_installed and not pip_path.exists():
                    print("pip not available, installing packages directly from offline packages...", flush=True)
                    offline_dir = Path("offline_packages")
                    if offline_dir.exists():
                        pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
                        if pip_files:
                            # Определяем site-packages путь
                            venv_lib = venv_path / "lib"
                            site_packages = None
                            if venv_lib.exists():
                                python_dirs = [d for d in venv_lib.iterdir() if d.is_dir() and d.name.startswith('python')]
                                if python_dirs:
                                    site_packages = python_dirs[0] / "site-packages"
                            
                            if site_packages and site_packages.exists():
                                print(f"Installing {len(pip_files)} packages directly to {site_packages}...", flush=True)
                                # Используем распаковку wheel файлов напрямую для офлайн установки без pip
                                import zipfile
                                installed_count = 0
                                for pip_file in pip_files:
                                    if pip_file.suffix == '.whl':
                                        try:
                                            with zipfile.ZipFile(pip_file, 'r') as zip_ref:
                                                zip_ref.extractall(site_packages)
                                            installed_count += 1
                                        except Exception as e:
                                            print(f"Warning: Failed to extract {pip_file.name}: {e}", flush=True)
                                    elif pip_file.suffix == '.tar.gz':
                                        # Для tar.gz файлов пробуем использовать системный pip
                                        try:
                                            result = subprocess.run(
                                                [sys.executable, "-m", "pip", "install", str(pip_file.resolve()), "--target", str(site_packages), "--no-deps", "--quiet"],
                                                check=False,
                                                capture_output=True,
                                                text=True,
                                                timeout=60
                                            )
                                            if result.returncode == 0:
                                                installed_count += 1
                                        except Exception:
                                            pass
                                
                                print(f"Packages installed directly from offline packages ({installed_count}/{len(pip_files)})", flush=True)
                                venv_ready_flag.touch()
                                return True
    
                    print("Warning: pip not available and could not install packages directly.", flush=True)
                    print("Note: venv created without pip. Dependencies may already be installed.", flush=True)
                    # Продолжаем без pip - может быть зависимости уже установлены
                    venv_ready_flag.touch()
                    return True  # Не возвращаем False, чтобы система могла продолжить работу
            else:
                return False
        try:
            # Обновляем pip, setuptools, wheel
            subprocess.run(
                [str(pip_path), "install", "--upgrade", "pip", "setuptools", "wheel"],
                check=False,
                capture_output=True,
                timeout=300
            )
            
            # Пробуем офлайн установку сначала
            offline_dir = Path("offline_packages")
            installed_offline = False
            
            if offline_dir.exists():
                pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
                if pip_files:
                    print(f"Found {len(pip_files)} offline packages, installing from local files...", flush=True)
                    try:
                        # Устанавливаем из локальной директории
                        result = subprocess.run(
                            [
                                str(pip_path), "install",
                                "--no-index",  # Не использовать PyPI
                                "--find-links", str(offline_dir.resolve()),
                                "-r", str(requirements_file)
                            ],
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                        
                        if result.returncode == 0:
                            installed_offline = True
                            print("Successfully installed packages from offline directory", flush=True)
                        else:
                            # Пробуем установить напрямую из файлов
                            print("Trying direct installation from files...", flush=True)
                            for pip_file in pip_files:
                                try:
                                    subprocess.run(
                                        [str(pip_path), "install", str(pip_file), "--no-deps"],
                                        capture_output=True,
                                        text=True,
                                        timeout=60
                                    )
                                except Exception:
                                    pass
                            installed_offline = True  # Частичный успех
                    except Exception as e:
                        print(f"Warning: Offline installation failed: {e}, trying online...", flush=True)
            
            # Если офлайн не сработал или не было файлов, пробуем онлайн
            if not installed_offline:
                print("Installing packages from internet...", flush=True)
                result = subprocess.run(
                    [str(pip_path), "install", "-r", str(requirements_file)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600
                )
            
            venv_ready_flag.touch()
            
            # Создаем venv.tar.gz архив после успешной установки зависимостей
            try:
                import update
                print("Creating venv.tar.gz archive...", flush=True)
                if update.ensure_venv_archive(Path(".")):
                    print("venv.tar.gz archive created successfully", flush=True)
                else:
                    print("Warning: Failed to create venv.tar.gz archive", flush=True)
            except Exception as e:
                print(f"Warning: Could not create venv.tar.gz archive: {e}", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"Error installing requirements: {e}", flush=True)
            if hasattr(e, 'stderr') and e.stderr:
                print(f"Error details: {e.stderr}", flush=True)
            return False
        except subprocess.TimeoutExpired:
            print("Timeout while installing requirements", flush=True)
            return False
        except FileNotFoundError:
            return False
    
    if not is_windows():
        if not system_deps_flag.exists():
            try:
                # Список системных пакетов для установки
                system_packages = ["libddsc0t64", "cyclonedds-dev", "build-essential", "cmake", "libssl-dev"]
                installed_offline = False
                
                # Пробуем офлайн установку сначала
                offline_dir = Path("offline_packages")
                if offline_dir.exists():
                    deb_files = list(offline_dir.glob("*.deb"))
                    if deb_files:
                        # Ищем нужные пакеты
                        needed_debs = []
                        for pkg in system_packages:
                            matching_debs = [d for d in deb_files if pkg.replace("-", "_") in d.name.lower() or pkg in d.name.lower()]
                            needed_debs.extend(matching_debs)
                        
                        if needed_debs:
                            print(f"Found {len(needed_debs)} offline packages for system dependencies, installing...", flush=True)
                            try:
                                install_result = subprocess.run(
                                    ["sudo", "dpkg", "-i"] + [str(d) for d in needed_debs],
                                    capture_output=True,
                                    text=True,
                                    timeout=300
                                )
                                
                                if install_result.returncode != 0:
                                    # Пробуем исправить зависимости
                                    subprocess.run(
                                        ["sudo", "apt-get", "install", "-f", "-y"],
                                        capture_output=True,
                                        text=True,
                                        timeout=300
                                    )
                                
                                installed_offline = True
                            except Exception as e:
                                print(f"Warning: Offline installation failed: {e}", flush=True)
                
                # Если офлайн не сработал, пробуем онлайн
                if not installed_offline:
                    if not check_sudo_permissions():
                        print("Warning: No sudo permissions. System dependencies will not be installed.", flush=True)
                        print("Please run with sudo or install packages manually.", flush=True)
                    else:
                        print("Installing system dependencies from internet...", flush=True)
                        subprocess.run(
                            ["sudo", "apt-get", "update"],
            check=False,
            capture_output=True,
                            timeout=60
                        )
                        install_result = subprocess.run(
                            ["sudo", "apt-get", "install", "-y"] + system_packages,
                            check=False,
                            capture_output=True,
                            timeout=300
                        )
                        stdout_output = install_result.stdout.decode() if install_result.stdout else ''
                
                # Проверяем установку библиотек
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
            except Exception as e:
                print(f"Warning: Could not install system dependencies: {e}", flush=True)
    
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import requests, numpy, flask; print('Core dependencies OK')"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            if "numpy" in result.stderr or "flask" in result.stderr:
                # Если pip доступен в venv, пробуем установить
                if pip_path.exists():
                    try:
                        install_result = subprocess.run(
                            [str(pip_path), "install", "-r", str(requirements_file)],
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=600
                        )
                        if install_result.returncode != 0:
                            # Если не получилось через pip, пробуем установить напрямую из wheel файлов
                            offline_dir = Path("offline_packages")
                            if offline_dir.exists():
                                pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
                                venv_lib = venv_path / "lib"
                                site_packages = None
                                if venv_lib.exists():
                                    python_dirs = [d for d in venv_lib.iterdir() if d.is_dir() and d.name.startswith('python')]
                                    if python_dirs:
                                        site_packages = python_dirs[0] / "site-packages"
                                
                                if site_packages and site_packages.exists():
                                    import zipfile
                                    for pip_file in pip_files:
                                        if pip_file.suffix == '.whl':
                                            try:
                                                with zipfile.ZipFile(pip_file, 'r') as zip_ref:
                                                    zip_ref.extractall(site_packages)
                                            except Exception:
                                                pass
                    except Exception:
                        # Если pip недоступен, устанавливаем напрямую из wheel файлов
                        offline_dir = Path("offline_packages")
                        if offline_dir.exists():
                            pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
                            venv_lib = venv_path / "lib"
                            site_packages = None
                            if venv_lib.exists():
                                python_dirs = [d for d in venv_lib.iterdir() if d.is_dir() and d.name.startswith('python')]
                                if python_dirs:
                                    site_packages = python_dirs[0] / "site-packages"
                            
                            if site_packages and site_packages.exists():
                                import zipfile
                                for pip_file in pip_files:
                                    if pip_file.suffix == '.whl':
                                        try:
                                            with zipfile.ZipFile(pip_file, 'r') as zip_ref:
                                                zip_ref.extractall(site_packages)
                                        except Exception:
                                            pass
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
    
    # Скачиваем системные пакеты
    # Пробуем разные варианты имени пакета python3-venv
    python_package_variants = [
        f"python{python_version}-venv",
        "python3-venv",
    ]
    
    system_packages = [
        ("python3-venv", python_package_variants),  # Пробуем разные варианты
        ("python3-pip", ["python3-pip"]),
        ("build-essential", ["build-essential"]),
        ("python3-dev", ["python3-dev"]),
        ("libssl-dev", ["libssl-dev"]),
        ("libffi-dev", ["libffi-dev"]),
    ]
    
    print(f"Downloading system packages to {offline_dir}...", flush=True)
    for pkg_name, variants in system_packages:
        downloaded = False
        for variant in variants:
            print(f"Trying to download {variant}...", flush=True)
            try:
                result = subprocess.run(
                    ["apt-get", "download", variant],
                    cwd=str(offline_dir),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode == 0:
                    downloaded = True
                    print(f"Successfully downloaded {variant}", flush=True)
                    break
            except Exception as e:
                        continue
                
        if not downloaded:
            print(f"Warning: Failed to download {pkg_name} (tried variants: {', '.join(variants)})", flush=True)
    
    # Скачиваем get-pip.py для офлайн установки pip
    # ВСЕГДА скачиваем обе версии для совместимости с разными версиями Python на других ПК
    print("Downloading get-pip.py (both Python 3.8 compatible and standard versions)...", flush=True)
    try:
        import urllib.request
        get_pip_path = offline_dir / "get-pip.py"
        get_pip_38_path = offline_dir / "get-pip-3.8.py"
        
        # Скачиваем версию для Python 3.8
        try:
            urllib.request.urlretrieve("https://bootstrap.pypa.io/pip/3.8/get-pip.py", str(get_pip_38_path))
            os.chmod(get_pip_38_path, 0o644)
            print(f"Successfully downloaded Python 3.8 compatible get-pip.py", flush=True)
        except Exception as e:
            print(f"Warning: Failed to download Python 3.8 compatible get-pip.py: {e}", flush=True)
        
        # Скачиваем стандартную версию для других версий Python
        try:
            urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", str(get_pip_path))
            os.chmod(get_pip_path, 0o644)  # rw-r--r-- - права на чтение для всех
            print(f"Successfully downloaded standard get-pip.py", flush=True)
        except Exception as e:
            print(f"Warning: Failed to download standard get-pip.py: {e}", flush=True)
    except Exception as e:
        print(f"Warning: Failed to download get-pip.py: {e}", flush=True)
    
    # Скачиваем pip пакеты
    if not requirements_file.exists():
        print(f"Requirements file not found: {requirements_file}", flush=True)
        return False

    print(f"Downloading Python packages from {requirements_file}...", flush=True)
    try:
        # Создаем временный requirements файл без cyclonedds
        import tempfile
        temp_req_file = None
        try:
            with open(requirements_file, 'r', encoding='utf-8') as f:
                req_lines = f.readlines()
            
            # Фильтруем cyclonedds
            filtered_lines = [line for line in req_lines if not line.strip().startswith('cyclonedds')]
            
            if len(filtered_lines) != len(req_lines):
                temp_req_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                temp_req_file.write(''.join(filtered_lines))
                temp_req_file.close()
                req_file_to_use = temp_req_file.name
                print("Skipping cyclonedds (already available offline)", flush=True)
            else:
                req_file_to_use = str(requirements_file)
            
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip", "download",
                    "-r", req_file_to_use,
                    "-d", str(offline_dir),
                    "--prefer-binary"
                ],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                print(f"Warning: Some packages failed to download: {result.stderr}", flush=True)
        finally:
            if temp_req_file and os.path.exists(temp_req_file.name):
                os.unlink(temp_req_file.name)
    except Exception as e:
        print(f"Error downloading pip packages: {e}", flush=True)
        return False
    
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


def install_dependencies_offline():
    """
    Устанавливает зависимости из локальных файлов (офлайн).
    
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
    
    # Устанавливаем системные пакеты
    if not is_windows():
        if not check_sudo_permissions():
            print("Warning: No sudo permissions. System packages will not be installed.", flush=True)
            print("Please run with sudo or install packages manually.", flush=True)
        elif offline_dir.exists():
            deb_files = list(offline_dir.glob("*.deb"))
            if deb_files:
                print(f"Installing {len(deb_files)} system packages from {offline_dir}...", flush=True)
                try:
                    result = subprocess.run(
                        ["sudo", "dpkg", "-i"] + [str(f) for f in deb_files],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode != 0:
                        print("Fixing dependencies...", flush=True)
                        subprocess.run(
                            ["sudo", "apt-get", "install", "-f", "-y"],
                            capture_output=True,
                            text=True,
                            timeout=300
                        )
                    print("System packages installed successfully", flush=True)
                except Exception as e:
                    print(f"Error installing system packages: {e}", flush=True)
                    if has_internet:
                        print("Trying online installation...", flush=True)
                        python_version = get_python_version()
                        package_name = f"python{python_version}-venv"
                        try:
                            subprocess.run(
                                ["sudo", "apt-get", "install", "-y", package_name],
                                capture_output=True,
                                text=True,
                                timeout=120
                            )
                        except Exception:
                            pass
    
    # Устанавливаем pip пакеты
    if offline_dir.exists():
        pip_files = list(offline_dir.glob("*.whl")) + list(offline_dir.glob("*.tar.gz"))
        if pip_files:
            print(f"Installing {len(pip_files)} Python packages from {offline_dir}...", flush=True)
            try:
                # Обновляем pip, setuptools, wheel
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                # Устанавливаем из локальной директории
                result = subprocess.run(
                    [
                        sys.executable, "-m", "pip", "install",
                        "--no-index",
                        "--find-links", str(offline_dir.resolve()),
                        "-r", str(requirements_file)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                
                if result.returncode == 0:
                    print("Python packages installed successfully", flush=True)
                elif has_internet:
                    print("Trying online installation...", flush=True)
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                        capture_output=True,
                        text=True,
                        timeout=600
                    )
            except Exception as e:
                print(f"Error installing pip packages: {e}", flush=True)
                if has_internet:
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
        python_executable = sys.executable
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
                python_executable = str(venv_python.resolve())
                print(f"Using venv Python: {python_executable}", flush=True)
        
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
        copy_result = subprocess.run(
            ["sudo", "cp", str(service_file_path), f"/etc/systemd/system/{service_name}.service"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if copy_result.returncode != 0:
            print(f"Error copying service file: {copy_result.stderr}", flush=True)
            return False
        
        # Перезагружаем systemd
        reload_result = subprocess.run(
            ["sudo", "systemctl", "daemon-reload"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if reload_result.returncode != 0:
            print(f"Error reloading systemd: {reload_result.stderr}", flush=True)
            return False
        
        # Включаем автозапуск
        enable_result = subprocess.run(
            ["sudo", "systemctl", "enable", service_name],
            capture_output=True,
            text=True,
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
            import api.robot as robot_api
            robot_api.RobotAPI.ensure_default_commands()
        except Exception:
            pass
        
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
            # Проверяем полноту комплекта офлайн пакетов
            is_complete, missing = check_offline_packages_completeness()
            
            if not is_complete:
                print(f"Incomplete offline packages set. Missing: {len(missing)} package(s)", flush=True)
                if check_internet():
                    print("Downloading missing dependencies for offline installation...", flush=True)
                    download_dependencies()
                else:
                    print("Warning: No internet connection and incomplete offline packages. Some features may not work.", flush=True)
                    if missing:
                        print(f"Missing packages: {', '.join(missing[:10])}{'...' if len(missing) > 10 else ''}", flush=True)
            else:
                print("Offline packages complete.", flush=True)
            
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
    
    # Обработка аргументов командной строки
    parser = argparse.ArgumentParser(description='RGW2.0 Main Service')
    parser.add_argument('--auto', action='store_true', help='Full automatic setup: download deps, install deps, setup venv, setup autostart')
    parser.add_argument('--setup-venv', action='store_true', help='Setup virtual environment only')
    parser.add_argument('--download-deps', action='store_true', help='Download dependencies for offline installation')
    parser.add_argument('--install-deps', action='store_true', help='Install dependencies from offline packages')
    parser.add_argument('--setup', action='store_true', help='Full setup: download deps, install deps, setup venv, setup autostart')
    args = parser.parse_args()
    
    # Полная автоматическая настройка при первом запуске (--auto)
    if args.auto:
        print("=" * 60, flush=True)
        print("RGW2.0 Automatic Setup", flush=True)
        print("=" * 60, flush=True)
        
        # Скачиваем зависимости если есть интернет
        if check_internet():
            print("Downloading dependencies...", flush=True)
            download_dependencies()
        else:
            print("No internet connection. Using existing offline packages if available.", flush=True)
        
        # Устанавливаем зависимости
        print("Installing dependencies...", flush=True)
        install_dependencies_offline()
        
        # Настраиваем venv
        print("Setting up virtual environment...", flush=True)
        if not setup_virtual_environment():
            print("Error: Failed to setup virtual environment", flush=True)
            sys.exit(1)
        
        # Настраиваем автозапуск
        print("Setting up autostart...", flush=True)
        if not setup_autostart():
            print("Warning: Failed to setup autostart", flush=True)
        
        print("=" * 60, flush=True)
        print("Automatic setup complete!", flush=True)
        print("=" * 60, flush=True)
        sys.exit(0)
    
    # Полная настройка (--setup)
    if args.setup:
        print("=" * 60, flush=True)
        print("RGW2.0 Full Setup", flush=True)
        print("=" * 60, flush=True)
        
        # Скачиваем зависимости если есть интернет
        if check_internet():
            print("Downloading dependencies...", flush=True)
            download_dependencies()
        else:
            print("No internet connection. Using existing offline packages if available.", flush=True)
        
        # Устанавливаем зависимости
        print("Installing dependencies...", flush=True)
        install_dependencies_offline()
        
        # Настраиваем venv
        print("Setting up virtual environment...", flush=True)
        if not setup_virtual_environment():
            print("Error: Failed to setup virtual environment", flush=True)
            sys.exit(1)
        
        # Настраиваем автозапуск
        print("Setting up autostart...", flush=True)
        if not setup_autostart():
            print("Warning: Failed to setup autostart", flush=True)
        
        print("=" * 60, flush=True)
        print("Setup complete!", flush=True)
        print("=" * 60, flush=True)
        sys.exit(0)
    
    # Скачивание зависимостей
    if args.download_deps:
        if download_dependencies():
            sys.exit(0)
        else:
            sys.exit(1)
            
    # Установка зависимостей
    if args.install_deps:
        if install_dependencies_offline():
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Если указан флаг --setup-venv, настраиваем venv и выходим
    if args.setup_venv:
        if setup_virtual_environment():
            sys.exit(0)
        else:
            sys.exit(1)
    
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

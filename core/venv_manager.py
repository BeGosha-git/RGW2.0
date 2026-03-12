"""
Менеджер виртуальных окружений Python.
"""
import os
import sys
import platform
import subprocess
import venv
import tarfile
import shutil
import tempfile
import urllib.request
import re
from pathlib import Path
from typing import Optional, List
from utils.logger import get_logger
from utils.path_utils import get_project_root

logger = get_logger(__name__)


class VenvManager:
    """Класс для управления виртуальными окружениями Python."""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Инициализация менеджера venv.
        
        Args:
            project_root: Корень проекта (по умолчанию определяется автоматически)
        """
        self.project_root = project_root or get_project_root()
        self.is_windows = platform.system() == 'Windows'
    
    def find_python_executable(self, version: str) -> Optional[str]:
        """
        Находит исполняемый файл Python для указанной версии.
        
        Args:
            version: Версия Python (например, "3.8" или "3.11")
            
        Returns:
            Путь к исполняемому файлу Python или None если не найден
        """
        if self.is_windows:
            paths = [
                f"C:\\Python{version.replace('.', '')}\\python.exe",
                f"C:\\Program Files\\Python{version.replace('.', '')}\\python.exe",
            ]
        else:
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
            
            # Проверяем текущий Python если версия совпадает
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
    
    def get_available_python_versions(self) -> List[str]:
        """
        Возвращает список доступных версий Python на системе.
        
        Returns:
            Список версий Python (например, ["3.8", "3.11"])
        """
        available_versions = []
        
        for version in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]:
            python_exe = self.find_python_executable(version)
            if python_exe:
                available_versions.append(version)
        
        return available_versions
    
    def setup_venv_for_version(self, python_version: str) -> bool:
        """
        Создает виртуальное окружение для конкретной версии Python.
        
        Args:
            python_version: Версия Python (например, "3.8" или "3.11")
        
        Returns:
            True если окружение готово, False при ошибке
        """
        venv_name = f"venv-{python_version}"
        venv_path = self.project_root / venv_name
        venv_ready_flag = venv_path / ".ready"
        
        python_exe = self.find_python_executable(python_version)
        if not python_exe:
            logger.error(f"Python {python_version} not found")
            return False
        
        if self.is_windows:
            python_path = venv_path / "Scripts" / "python.exe"
            pip_path = venv_path / "Scripts" / "pip.exe"
        else:
            python_path = venv_path / "bin" / "python"
            pip_path = venv_path / "bin" / "pip"
        
        # Если venv уже готов - готово
        if venv_path.exists() and venv_ready_flag.exists() and python_path.exists():
            logger.debug(f"Virtual environment for Python {python_version} is ready")
            return True
        
        # Проверяем наличие архива venv
        venv_archive = self.project_root / f"{venv_name}.tar.gz"
        if venv_archive.exists():
            logger.info(f"Found {venv_archive.name}, extracting...")
            try:
                if venv_path.exists():
                    shutil.rmtree(venv_path)
                
                with tarfile.open(venv_archive, 'r:gz') as tar:
                    try:
                        tar.extractall(path=str(self.project_root), filter='data')
                    except TypeError:
                        tar.extractall(path=str(self.project_root))
                
                # Переименовываем извлеченный venv
                extracted_venv = self.project_root / "venv"
                if extracted_venv.exists() and not venv_path.exists():
                    extracted_venv.rename(venv_path)
                
                venv_ready_flag.touch()
                logger.info(f"Successfully extracted {venv_archive.name}")
                return True
            except Exception as e:
                logger.warning(f"Failed to extract {venv_archive.name}: {e}")
        
        # Создаем новый venv
        logger.info(f"Creating virtual environment for Python {python_version}...")
        try:
            venv_args = [python_exe, "-m", "venv", str(venv_path)]
            if python_version in ["3.8", "3.11"]:
                venv_args.append("--without-pip")
            
            result = subprocess.run(
                venv_args,
                check=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            logger.info(f"Successfully created venv using Python {python_version}")
        except subprocess.CalledProcessError as e:
            if python_version in ["3.8", "3.11"] and "--without-pip" in str(e):
                try:
                    subprocess.run(
                        [python_exe, "-m", "venv", str(venv_path)],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    logger.info(f"Successfully created venv using Python {python_version} (retry without --without-pip)")
                except subprocess.CalledProcessError as e2:
                    logger.error(f"Error creating venv for Python {python_version}: {e2}")
                    if e2.stderr:
                        logger.error(f"Error details: {e2.stderr[:300]}")
                    return False
            else:
                logger.error(f"Error creating venv for Python {python_version}: {e}")
                if e.stderr:
                    logger.error(f"Error details: {e.stderr[:300]}")
                return False
        
        # Устанавливаем pip если нужно
        if not pip_path.exists():
            if not self._install_pip(python_version, python_path, pip_path):
                return False
        
        venv_ready_flag.touch()
        
        # Создаем архив
        try:
            self._create_venv_archive(python_version)
            logger.info(f"Created archive {venv_name}.tar.gz")
        except Exception as e:
            logger.warning(f"Could not create {venv_name}.tar.gz archive: {e}")
        
        logger.info(f"Virtual environment for Python {python_version} created successfully")
        return True
    
    def _install_pip(self, python_version: str, python_path: Path, pip_path: Path) -> bool:
        """Устанавливает pip в venv."""
        logger.info(f"Installing pip for Python {python_version}...")
        
        offline_dir = self.project_root / "offline_packages"
        get_pip_file = offline_dir / f"get-pip-{python_version}.py"
        if not get_pip_file.exists():
            get_pip_file = offline_dir / "get-pip.py"
        
        # Метод 1: get-pip.py из offline_packages
        if get_pip_file.exists():
            logger.info(f"Trying get-pip.py from offline_packages for Python {python_version}...")
            result = subprocess.run(
                [str(python_path), str(get_pip_file), "--no-warn-script-location"],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and pip_path.exists():
                logger.info(f"Successfully installed pip using offline get-pip.py for Python {python_version}")
                return True
        
        # Метод 2: Скачиваем get-pip.py онлайн
        logger.info(f"Downloading get-pip.py for Python {python_version} from internet...")
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
                logger.info(f"Successfully installed pip for Python {python_version}")
                return True
            else:
                err_text = result.stderr
                logger.warning(f"get-pip.py failed: {err_text[:300]}")
        except Exception as e:
            logger.warning(f"get-pip.py download failed: {e}")
        finally:
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
        
        logger.error(f"All methods failed to install pip for Python {python_version}")
        return False
    
    def _create_venv_archive(self, python_version: str) -> bool:
        """Создает архив venv для конкретной версии Python."""
        try:
            venv_name = f"venv-{python_version}"
            venv_path = self.project_root / venv_name
            venv_archive = self.project_root / f"{venv_name}.tar.gz"
            
            if not venv_path.exists():
                return False
            
            venv_ready_flag = venv_path / ".ready"
            if not venv_ready_flag.exists():
                return False
            
            with tarfile.open(venv_archive, 'w:gz') as tar:
                tar.add(venv_path, arcname=venv_name, filter=lambda tarinfo: None if '__pycache__' in tarinfo.name else tarinfo)
            
            return True
        except Exception:
            return False
    
    def get_venv_path(self, python_version: Optional[str] = None) -> Path:
        """
        Получает путь к виртуальному окружению.
        
        Args:
            python_version: Версия Python (None = основной venv)
        
        Returns:
            Путь к venv
        """
        if python_version:
            return self.project_root / f"venv-{python_version}"
        else:
            return self.project_root / "venv"

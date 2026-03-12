"""
Менеджер зависимостей проекта.
"""
import os
import sys
import subprocess
import platform
from pathlib import Path
from typing import Optional, List, Tuple
from utils.logger import get_logger
from utils.path_utils import get_project_root

logger = get_logger(__name__)


class DependencyManager:
    """Класс для управления зависимостями проекта."""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Инициализация менеджера зависимостей.
        
        Args:
            project_root: Корень проекта (по умолчанию определяется автоматически)
        """
        self.project_root = project_root or get_project_root()
        self.is_windows = platform.system() == 'Windows'
    
    def check_internet(self) -> bool:
        """Проверяет наличие интернет-соединения."""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False
    
    def check_sudo_permissions(self) -> bool:
        """
        Проверяет, есть ли у пользователя права на выполнение sudo команд.
        
        Returns:
            True если есть права, False иначе
        """
        if self.is_windows:
            return True

        try:
            result = subprocess.run(
                ["sudo", "-n", "true"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True

            result = subprocess.run(
                ["which", "sudo"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def install_packages_to_venv(self, venv_path: Path, python_path: Path, 
                                  pip_path: Path, python_version: str) -> bool:
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
        requirements_file = self.project_root / f"requirements-{python_version}.txt"
        if not requirements_file.exists():
            requirements_file = self.project_root / "requirements.txt"
        
        if not requirements_file.exists():
            logger.warning("Requirements file not found")
            return False
        
        # Устанавливаем pip если нужно
        if not pip_path.exists():
            logger.warning(f"pip not found at {pip_path}")
            return False
        
        try:
            logger.info(f"Installing packages from {requirements_file.name} for Python {python_version}...")
            
            # Обновляем pip, setuptools, wheel
            logger.info(f"Updating pip, setuptools, wheel for Python {python_version}...")
            upgrade_cmd = [
                str(pip_path), "install", "--upgrade",
                "pip", "setuptools>=70.1", "wheel"
            ]
            upgrade_result = subprocess.run(
                upgrade_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if upgrade_result.returncode != 0:
                logger.warning(f"Failed to upgrade pip/setuptools/wheel: {upgrade_result.stderr[:200]}")
            
            # Для Python 3.13 дополнительно обновляем setuptools
            if python_version == "3.13":
                logger.info(f"Ensuring setuptools>=70.1 for Python {python_version} build environment...")
                subprocess.run(
                    [str(pip_path), "install", "--upgrade", "--force-reinstall", "setuptools>=70.1"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
            
            # Устанавливаем пакеты из requirements
            install_cmd = [str(pip_path), "install", "-r", str(requirements_file)]
            env = os.environ.copy()
            
            if python_version == "3.13":
                env["PIP_BUILD_ISOLATION"] = "0"
            
            result = subprocess.run(
                install_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
                env=env
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully installed packages from {requirements_file.name}")
                return True
            else:
                if result.stdout:
                    logger.warning(f"pip stdout: {result.stdout[:500]}")
                if result.stderr:
                    logger.warning(f"pip stderr: {result.stderr[:500]}")
                logger.warning(f"Some packages failed to install (exit code: {result.returncode})")
                
                # Проверяем наличие критичных пакетов
                check_result = subprocess.run(
                    [str(python_path), "-c", "import flask; print('Flask OK')"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if check_result.returncode == 0:
                    logger.info("Critical packages installed successfully, continuing...")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to install packages: {e}", exc_info=True)
            return False
    
    def check_offline_packages_completeness(self) -> Tuple[bool, List[str]]:
        """
        Проверяет полноту комплекта офлайн пакетов.
        
        Returns:
            (is_complete: bool, missing_packages: list) - полный ли комплект и список недостающих пакетов
        """
        offline_dir = self.project_root / "offline_packages"
        requirements_file = self.project_root / "requirements.txt"
        
        if not offline_dir.exists():
            return (False, ["all"])
        
        missing = []
        
        # Проверяем системные пакеты
        python_version = self._get_python_version()
        deb_files = list(offline_dir.glob("*.deb"))
        
        system_packages = [
            ("python-venv", [f"python{python_version}-venv", "python3-venv"]),
            ("python3-pip", ["python3-pip"]),
            ("build-essential", ["build-essential"]),
            ("python3-dev", ["python3-dev"]),
            ("libssl-dev", ["libssl-dev"]),
            ("libffi-dev", ["libffi-dev"]),
        ]
        
        for pkg_name, variants in system_packages:
            found = False
            for variant in variants:
                if any(variant.replace("-", "_") in d.name.lower() or variant in d.name.lower() for d in deb_files):
                    found = True
                    break
            if not found:
                missing.append(f"system:{pkg_name}")
        
        # Проверяем Python пакеты из requirements.txt
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
                    
                    pkg_name = req_line.split('>=')[0].split('==')[0].split('<=')[0].split('>')[0].split('<')[0].strip()
                    
                    if pkg_name.lower() == "cyclonedds":
                        continue
                    
                    found = any(pkg_name.lower() in name for name in pip_file_names)
                    if not found:
                        missing.append(f"pip:{pkg_name}")
            except Exception as e:
                logger.error(f"Could not check requirements completeness: {e}")
        
        is_complete = len(missing) == 0
        return (is_complete, missing)
    
    def _get_python_version(self) -> str:
        """Определяет версию Python для установки правильных пакетов."""
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                import re
                version_match = re.search(r'(\d+)\.(\d+)', result.stdout)
                if version_match:
                    return f"{version_match.group(1)}.{version_match.group(2)}"
        except Exception:
            pass
        return "3.8"

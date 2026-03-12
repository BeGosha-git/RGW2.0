"""
Менеджер системных операций (автозапуск, порты и т.д.).
"""
import os
import sys
import subprocess
import platform
import signal
from pathlib import Path
from typing import Optional, Set
from utils.logger import get_logger
from utils.path_utils import get_project_root
from utils.network_utils import PortManager

logger = get_logger(__name__)


class SystemManager:
    """Класс для управления системными операциями."""
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Инициализация системного менеджера.
        
        Args:
            project_root: Корень проекта (по умолчанию определяется автоматически)
        """
        self.project_root = project_root or get_project_root()
        self.is_windows = platform.system() == 'Windows'
        self.port_manager = PortManager()
    
    def setup_autostart(self) -> bool:
        """
        Создает systemd сервис для автозапуска приложения.
        
        Returns:
            True если сервис создан успешно, False при ошибке
        """
        if self.is_windows:
            logger.info("Autostart setup is not supported on Windows")
            return False
        
        try:
            script_path = self.project_root / "main.py"
            script_dir = self.project_root
            
            # Определяем Python для использования
            python_executable = sys.executable
            venv_path = script_dir / "venv"
            venv_ready_flag = venv_path / ".ready"
            
            if venv_path.exists() and venv_ready_flag.exists():
                venv_python = venv_path / "bin" / "python3"
                if not venv_python.exists():
                    venv_python = venv_path / "bin" / "python"
                
                if venv_python.exists():
                    python_executable = str(venv_python.resolve())
                    logger.info(f"Using venv Python: {python_executable}")
            
            # Определяем реального пользователя
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
            import tempfile
            temp_dir = Path.home() / ".tmp"
            temp_dir.mkdir(exist_ok=True, mode=0o755)
            service_file_path = temp_dir / f"{service_name}.service"
            
            try:
                service_file_path.write_text(service_file_content, encoding='utf-8')
                os.chmod(service_file_path, 0o644)
            except PermissionError as e:
                logger.error(f"Permission error creating temp file: {e}")
                service_file_path = Path(f"/tmp/{service_name}.service")
                try:
                    service_file_path.write_text(service_file_content, encoding='utf-8')
                    os.chmod(service_file_path, 0o644)
                except Exception as e2:
                    logger.error(f"Error creating service file: {e2}")
                    return False
            
            # Копируем сервис файл в systemd
            copy_result = subprocess.run(
                ["sudo", "cp", str(service_file_path), f"/etc/systemd/system/{service_name}.service"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if copy_result.returncode != 0:
                logger.error(f"Error copying service file: {copy_result.stderr}")
                return False
            
            # Перезагружаем systemd
            reload_result = subprocess.run(
                ["sudo", "systemctl", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if reload_result.returncode != 0:
                logger.error(f"Error reloading systemd: {reload_result.stderr}")
                return False
            
            # Включаем автозапуск
            enable_result = subprocess.run(
                ["sudo", "systemctl", "enable", service_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if enable_result.returncode != 0:
                logger.error(f"Error enabling service: {enable_result.stderr}")
                return False
            
            logger.info(f"Autostart service '{service_name}' created and enabled successfully!")
            logger.info(f"To start the service: sudo systemctl start {service_name}")
            logger.info(f"To check status: sudo systemctl status {service_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting up autostart: {e}", exc_info=True)
            return False
    
    def cleanup_ports(self, ports: Optional[Set[int]] = None) -> None:
        """
        Освобождает порты, используемые сервисами.
        
        Args:
            ports: Множество портов для освобождения (если None, определяет автоматически)
        """
        if ports is None:
            ports = self._get_service_ports()
        
        self.port_manager.free_ports(ports)
    
    def _get_service_ports(self) -> Set[int]:
        """Получает порты, используемые сервисами."""
        ports = set()
        
        try:
            import services_manager
            manager = services_manager.get_services_manager()
            
            web_service = manager.get_service("web")
            if web_service:
                web_params = manager.get_service_parameters("web")
                web_port = web_params.get("port", 8080)
                ports.add(web_port)
            
            api_service = manager.get_service("api")
            if api_service:
                api_params = manager.get_service_parameters("api")
                api_port = api_params.get("port", 5000)
                ports.add(api_port)
            
            scanner_service = manager.get_service("scanner_service")
            if scanner_service:
                scanner_params = manager.get_service_parameters("scanner_service")
                scanner_port = scanner_params.get("port", 8080)
                ports.add(scanner_port)
        except Exception as e:
            logger.warning(f"Error getting service ports: {e}")
        
        return ports
    
    def is_autostart_configured(self) -> bool:
        """Проверяет, настроен ли автозапуск."""
        if self.is_windows:
            return False
        
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "rgw2"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

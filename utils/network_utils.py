"""
Утилиты для работы с сетью (порты, соединения и т.д.).
"""
import socket
import subprocess
from typing import Optional, Set
from .logger import get_logger

logger = get_logger(__name__)


class PortManager:
    """Менеджер для работы с портами."""
    
    @staticmethod
    def check_port_available(port: int, host: str = '127.0.0.1') -> bool:
        """
        Проверяет, свободен ли порт.
        
        Args:
            port: Номер порта
            host: Хост для проверки
            
        Returns:
            True если порт свободен
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            return result != 0
        except Exception:
            return False
    
    @staticmethod
    def free_port(port: int) -> bool:
        """
        Освобождает порт, убивая процесс который его использует.
        
        Args:
            port: Номер порта
            
        Returns:
            True если порт освобожден
        """
        try:
            # Пробуем fuser
            result = subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                capture_output=True,
                timeout=2,
                stderr=subprocess.DEVNULL
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        
        try:
            # Пробуем lsof + kill
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                timeout=2,
                text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        subprocess.run(
                            ["kill", "-9", pid],
                            capture_output=True,
                            timeout=1,
                            stderr=subprocess.DEVNULL
                        )
                    except Exception:
                        pass
                return True
        except Exception:
            pass
        
        return False
    
    @staticmethod
    def find_free_port(start_port: int = 5000, end_port: int = 65535) -> Optional[int]:
        """
        Находит свободный порт в указанном диапазоне.
        
        Args:
            start_port: Начальный порт
            end_port: Конечный порт
            
        Returns:
            Номер свободного порта или None
        """
        for port in range(start_port, end_port + 1):
            if PortManager.check_port_available(port):
                return port
        return None
    
    @staticmethod
    def free_ports(ports: Set[int]) -> None:
        """
        Освобождает несколько портов.
        
        Args:
            ports: Множество портов для освобождения
        """
        for port in ports:
            PortManager.free_port(port)


def check_port_available(port: int, host: str = '127.0.0.1') -> bool:
    """
    Проверяет, свободен ли порт (удобная функция).
    
    Args:
        port: Номер порта
        host: Хост для проверки
        
    Returns:
        True если порт свободен
    """
    return PortManager.check_port_available(port, host)

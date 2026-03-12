"""
Ядро системы RGW2.0 - основные классы и модули.
"""
from .venv_manager import VenvManager
from .dependency_manager import DependencyManager
from .system_manager import SystemManager

__all__ = [
    'VenvManager',
    'DependencyManager',
    'SystemManager',
]

# Инициализация логирования при импорте
from utils.logger import setup_logging
import os
log_level = os.getenv('RGW_LOG_LEVEL', 'INFO')
setup_logging(level=log_level)

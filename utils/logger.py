"""
Единый модуль логирования для проекта RGW2.0.
Обеспечивает единообразное логирование во всех модулях.
"""
import logging
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Форматтер с цветами для консоли."""
    
    # ANSI коды цветов
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',       # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        """Форматирует запись лога с цветами."""
        if sys.stdout.isatty() and os.getenv('TERM') != 'dumb':
            log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


class RGWLogger:
    """Единый логгер для проекта RGW2.0."""
    
    _loggers: dict = {}
    _initialized = False
    
    @classmethod
    def setup(cls, 
              level: str = 'INFO',
              log_file: Optional[Path] = None,
              format_string: Optional[str] = None,
              use_colors: bool = True):
        """
        Настраивает систему логирования.
        
        Args:
            level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Путь к файлу логов (опционально)
            format_string: Кастомный формат строки (опционально)
            use_colors: Использовать цвета в консоли
        """
        if cls._initialized:
            return
        
        # Определяем уровень логирования
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        # Формат по умолчанию
        if format_string is None:
            format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Настраиваем root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Удаляем существующие обработчики
        root_logger.handlers.clear()
        
        # Консольный обработчик
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        
        if use_colors and sys.stdout.isatty() and os.getenv('TERM') != 'dumb':
            console_formatter = ColoredFormatter(format_string)
        else:
            console_formatter = logging.Formatter(format_string)
        
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # Файловый обработчик (если указан)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(log_level)
            file_formatter = logging.Formatter(format_string)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        
        # Настраиваем логирование для сторонних библиотек
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('requests').setLevel(logging.WARNING)
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        
        # Подавляем логи OpenCV если доступен
        try:
            import cv2
            os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'
            os.environ['OPENCV_VIDEOIO_DEBUG'] = '0'
            try:
                cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
            except (AttributeError, ImportError):
                try:
                    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
                except (AttributeError, ImportError):
                    pass
        except ImportError:
            pass
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Получает логгер для указанного модуля.
        
        Args:
            name: Имя модуля (обычно __name__)
            
        Returns:
            Настроенный логгер
        """
        if not cls._initialized:
            cls.setup()
        
        # Нормализуем имя логгера
        if name.startswith('services.'):
            logger_name = name.replace('services.', '')
        elif name.startswith('api.'):
            logger_name = name.replace('api.', '')
        else:
            logger_name = name
        
        if logger_name not in cls._loggers:
            logger = logging.getLogger(logger_name)
            cls._loggers[logger_name] = logger
        
        return cls._loggers.get(logger_name, logging.getLogger(logger_name))


def setup_logging(level: str = 'INFO', 
                  log_file: Optional[Path] = None,
                  format_string: Optional[str] = None,
                  use_colors: bool = True):
    """
    Настраивает систему логирования (удобная функция).
    
    Args:
        level: Уровень логирования
        log_file: Путь к файлу логов
        format_string: Кастомный формат
        use_colors: Использовать цвета
    """
    RGWLogger.setup(level, log_file, format_string, use_colors)


def get_logger(name: str) -> logging.Logger:
    """
    Получает логгер для модуля (удобная функция).
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Настроенный логгер
    """
    return RGWLogger.get_logger(name)


# Автоматическая настройка при импорте
if not RGWLogger._initialized:
    # Проверяем переменную окружения для уровня логирования
    log_level = os.getenv('RGW_LOG_LEVEL', 'INFO')
    log_file = os.getenv('RGW_LOG_FILE')
    if log_file:
        log_file = Path(log_file)
    
    RGWLogger.setup(level=log_level, log_file=log_file)

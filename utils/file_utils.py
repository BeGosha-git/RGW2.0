"""
Утилиты для работы с файлами (JSON, текстовые файлы и т.д.).
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from .logger import get_logger

logger = get_logger(__name__)


class JSONFileManager:
    """Менеджер для работы с JSON файлами."""
    
    def __init__(self, file_path: Path, default_data: Optional[Dict[str, Any]] = None):
        """
        Инициализация менеджера JSON файла.
        
        Args:
            file_path: Путь к JSON файлу
            default_data: Данные по умолчанию если файл не существует
        """
        self.file_path = Path(file_path)
        self.default_data = default_data or {}
    
    def load(self) -> Dict[str, Any]:
        """
        Загружает данные из JSON файла.
        
        Returns:
            Словарь с данными
        """
        if not self.file_path.exists():
            return self.default_data.copy()
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else self.default_data.copy()
        except Exception as e:
            logger.error(f"Error loading JSON file {self.file_path}: {e}")
            return self.default_data.copy()
    
    def save(self, data: Dict[str, Any]) -> bool:
        """
        Сохраняет данные в JSON файл.
        
        Args:
            data: Данные для сохранения
            
        Returns:
            True если успешно
        """
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving JSON file {self.file_path}: {e}")
            return False
    
    def update(self, updates: Dict[str, Any]) -> bool:
        """
        Обновляет данные в JSON файле.
        
        Args:
            updates: Словарь с обновлениями
            
        Returns:
            True если успешно
        """
        data = self.load()
        data.update(updates)
        return self.save(data)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение по ключу.
        
        Args:
            key: Ключ (поддерживает вложенные ключи через точку, например "services.web")
            default: Значение по умолчанию
            
        Returns:
            Значение или default
        """
        data = self.load()
        keys = key.split('.')
        value = data
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, key: str, value: Any) -> bool:
        """
        Устанавливает значение по ключу.
        
        Args:
            key: Ключ (поддерживает вложенные ключи через точку)
            value: Значение для установки
            
        Returns:
            True если успешно
        """
        data = self.load()
        keys = key.split('.')
        current = data
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        return self.save(data)
    
    def exists(self) -> bool:
        """Проверяет существование файла."""
        return self.file_path.exists()


def ensure_data_dir(data_dir: Optional[Path] = None) -> Path:
    """
    Создает директорию data если её нет.
    
    Args:
        data_dir: Путь к директории data (по умолчанию data/ в корне проекта)
        
    Returns:
        Путь к директории data
    """
    if data_dir is None:
        from .path_utils import get_project_root
        data_dir = get_project_root() / "data"
    
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

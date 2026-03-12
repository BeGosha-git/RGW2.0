"""
Утилиты для работы с путями.
"""
from pathlib import Path
from typing import Optional


# Кэш для корня проекта
_project_root: Optional[Path] = None


def get_project_root() -> Path:
    """
    Получает корневую директорию проекта (где находится main.py).
    
    Returns:
        Путь к корню проекта
    """
    global _project_root
    
    if _project_root is None:
        # Ищем main.py в текущей директории и родительских
        current = Path(__file__).resolve()
        
        # Поднимаемся вверх до тех пор, пока не найдем main.py
        for parent in [current.parent] + list(current.parents):
            if (parent / "main.py").exists():
                _project_root = parent
                break
        
        # Если не нашли, используем родительскую директорию utils
        if _project_root is None:
            _project_root = current.parent.parent
    
    return _project_root


def get_data_dir() -> Path:
    """
    Получает директорию data.
    
    Returns:
        Путь к директории data
    """
    return get_project_root() / "data"


def get_services_dir() -> Path:
    """
    Получает директорию services.
    
    Returns:
        Путь к директории services
    """
    return get_project_root() / "services"


def get_api_dir() -> Path:
    """
    Получает директорию api.
    
    Returns:
        Путь к директории api
    """
    return get_project_root() / "api"


def get_venv_path(python_version: Optional[str] = None) -> Path:
    """
    Получает путь к виртуальному окружению.
    
    Args:
        python_version: Версия Python (например, "3.8", "3.11")
        
    Returns:
        Путь к venv
    """
    root = get_project_root()
    
    if python_version:
        return root / f"venv-{python_version}"
    else:
        return root / "venv"

"""
Скрипт для инициализации settings.json из переменных окружения.
Используется в Docker контейнерах.
"""
import json
import os
import sys
from pathlib import Path

# Определяем корень проекта (папка с main.py)
# init_settings.py находится в services/windows_docker/, поэтому поднимаемся на 2 уровня вверх
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

def init_settings():
    """Создает или обновляет settings.json из переменных окружения."""
    settings = {
        "RobotType": os.getenv("ROBOT_TYPE", "PC"),
        "RobotID": os.getenv("ROBOT_ID", "0001"),
        "RobotGroup": os.getenv("ROBOT_GROUP", "white"),
        "VersionPriority": os.getenv("VERSION_PRIORITY", "STABLE")
    }
    
    # Создаем папку data если её нет
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Читаем существующие настройки если файл есть
    settings_file = data_dir / "settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                existing_settings = json.load(f)
                # Обновляем только новые параметры (не перезаписываем существующие)
                for key, value in settings.items():
                    if key not in existing_settings:
                        existing_settings[key] = value
                settings = existing_settings
        except Exception:
            pass  # Если не удалось прочитать, используем новые настройки
    
    # Записываем настройки
    with open(settings_file, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)
    
    print(f"Settings initialized: RobotID={settings['RobotID']}, RobotType={settings['RobotType']}", flush=True)
    print(f"Settings file path: {settings_file}", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)

if __name__ == '__main__':
    try:
        init_settings()
        print("init_settings.py completed successfully", flush=True)
    except Exception as e:
        print(f"Error in init_settings.py: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

"""
Точка входа для сервиса управления моторами Unitree.
"""
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Зависимости настраиваются автоматически в unitree_motor_control.py
from services.unitree_motor_control.unitree_motor_control import run

if __name__ == '__main__':
    run()

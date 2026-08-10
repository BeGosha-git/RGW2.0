"""
Точка входа для сервиса звука Unitree G1.
Автоматически обнаруживается services_manager (run.py) благодаря
импорту services_manager внутри g1_sound_service.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.g1_sound.g1_sound_service import run

if __name__ == "__main__":
    run()

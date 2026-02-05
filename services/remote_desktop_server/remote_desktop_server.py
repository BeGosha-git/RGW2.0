"""
Сервис «сервер удалённого стола». Запускается всегда вместе с RGW.
Порт 9009. Реле между хостами и клиентами.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services_manager
from services.remote_desktop.remote_desktop_server import run as server_run, DEFAULT_PORT


def run():
    """Точка входа: запуск сервера с параметрами из services_manager."""
    params = services_manager.get_services_manager().get_service_parameters("remote_desktop_server")
    port = int(params.get("server_port", params.get("port", DEFAULT_PORT)))
    server_run(port=port)


if __name__ == "__main__":
    run()

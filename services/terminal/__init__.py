"""
Сервис WebSocket-терминала — предоставляет полноценный PTY-шелл через WebSocket.
Каждое подключение получает отдельный /bin/bash в отдельном PTY.
"""
from .terminal import run_service_loop, get_ws_port

__all__ = ['run_service_loop', 'get_ws_port']

"""
Сервис для захвата видео с камер (RealSense и USB камеры).
"""
from .camera_stream import detect_cameras, get_selected_cameras

__all__ = ['detect_cameras', 'get_selected_cameras']
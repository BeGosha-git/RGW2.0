"""
Сервис для захвата видео с камер и трансляции через UDP и HTTP MJPEG.
Поддерживает RealSense и обычные USB камеры.
"""
import os
import sys
import time
import threading
import socket
import warnings
import contextlib
from pathlib import Path
from typing import Dict, Optional, List
from collections import deque

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services_manager
import status

# Опциональные зависимости
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
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
    CV2_AVAILABLE = False
    np = None

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False

SERVICE_NAME = "camera_stream"

# Глобальное хранилище потоков камер
_camera_streams: Dict[str, Dict] = {}
_streams_lock = threading.Lock()


@contextlib.contextmanager
def _suppress_stderr():
    """Подавляет C-level stderr (fd 2) для подавления сообщений OpenCV/RealSense."""
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        old_stderr_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)
        try:
            yield
        finally:
            os.dup2(old_stderr_fd, 2)
            os.close(old_stderr_fd)
    except Exception:
        yield


def get_service_name() -> str:
    return SERVICE_NAME


def _try_open_camera(camera_idx: int):
    """Попытка открыть USB камеру с разными backend'ами. Возвращает VideoCapture или None."""
    if not CV2_AVAILABLE:
        return None

    backends = [cv2.CAP_V4L2, cv2.CAP_ANY, cv2.CAP_V4L]

    for backend in backends:
        cap = None
        try:
            with _suppress_stderr():
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    cap = cv2.VideoCapture(camera_idx, backend)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            return cap
                        cap.release()
                    else:
                        cap.release()
        except Exception:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
    return None


def detect_cameras() -> List[Dict]:
    """Обнаруживает USB и RealSense камеры."""
    cameras = []

    # USB камеры через OpenCV
    if CV2_AVAILABLE:
        for i in range(10):
            try:
                with _suppress_stderr():
                    cap = _try_open_camera(i)
                if cap is not None:
                    try:
                        with _suppress_stderr():
                            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            fps = cap.get(cv2.CAP_PROP_FPS)
                        if width == 0 or height == 0:
                            width, height = 640, 480
                        cameras.append({
                            "id": f"usb_{i}",
                            "type": "usb",
                            "name": f"USB Camera {i}",
                            "device_path": f"/dev/video{i}",
                            "index": i,
                            "width": width,
                            "height": height,
                            "fps": fps if fps > 0 else 30.0,
                            "available": True
                        })
                    finally:
                        with _suppress_stderr():
                            cap.release()
            except Exception:
                pass

    # RealSense камеры
    if REALSENSE_AVAILABLE:
        try:
            with _suppress_stderr():
                ctx = rs.context()
                devices = ctx.query_devices()
                for idx, dev in enumerate(devices):
                    try:
                        cameras.append({
                            "id": f"realsense_{idx}",
                            "type": "realsense",
                            "name": f"RealSense {dev.get_info(rs.camera_info.name)}",
                            "serial": dev.get_info(rs.camera_info.serial_number),
                            "index": idx,
                            "available": True
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    return cameras


def _find_camera(camera_id: str, cameras: List[Dict]) -> Optional[Dict]:
    """Ищет камеру по id."""
    for cam in cameras:
        if cam["id"] == camera_id:
            return cam
    return None


# ─── UDP фрагментация ──────────────────────────────────────────────────────────
# Максимальный размер UDP payload (с запасом от 65507)
UDP_MAX_PAYLOAD = 60000
UDP_HEADER_SIZE = 8  # frame_id(4) + chunk_idx(2) + total_chunks(2)
UDP_CHUNK_SIZE = UDP_MAX_PAYLOAD - UDP_HEADER_SIZE


def _send_udp_frame(sock: socket.socket, frame_bytes: bytes, port: int, frame_id: int):
    """Отправляет JPEG кадр по UDP с фрагментацией если нужно."""
    total = (len(frame_bytes) + UDP_CHUNK_SIZE - 1) // UDP_CHUNK_SIZE
    total = max(1, total)
    for i in range(total):
        chunk = frame_bytes[i * UDP_CHUNK_SIZE:(i + 1) * UDP_CHUNK_SIZE]
        # header: frame_id (4 bytes BE) + chunk_idx (2 bytes BE) + total_chunks (2 bytes BE)
        header = (frame_id & 0xFFFFFFFF).to_bytes(4, 'big') + \
                 i.to_bytes(2, 'big') + total.to_bytes(2, 'big')
        try:
            sock.sendto(header + chunk, ('127.0.0.1', port))
        except Exception:
            pass


class CameraStream:
    """Управляет потоком с одной камеры: захват → frame_queue + UDP."""

    def __init__(self, camera_info: Dict, udp_port: int = None,
                 width: int = 640, height: int = 480, fps: int = 30):
        self.camera_info = camera_info
        self.camera_id = camera_info["id"]
        self.udp_port = udp_port
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.cap = None
        self.pipeline = None
        self.udp_socket = None
        self.frame_queue: deque = deque(maxlen=3)
        self._frame_event = threading.Event()  # сигнал о новом кадре

    def start(self):
        if self.running:
            return
        self.running = True
        if self.camera_info["type"] == "realsense":
            self._start_realsense()
        else:
            self._start_usb()
        if self.running:
            self.thread = threading.Thread(target=self._stream_loop, daemon=True)
            self.thread.start()

    def _start_realsense(self):
        if not REALSENSE_AVAILABLE:
            self.running = False
            return
        try:
            with _suppress_stderr():
                self.pipeline = rs.pipeline()
                config = rs.config()
                serial = self.camera_info.get("serial", "")
                if serial:
                    config.enable_device(serial)
                config.enable_stream(rs.stream.color, self.width, self.height,
                                     rs.format.bgr8, self.fps)
                self.pipeline.start(config)
        except Exception as e:
            print(f"[CameraStream] RealSense start error ({self.camera_id}): {e}", flush=True)
            self.running = False

    def _start_usb(self):
        if not CV2_AVAILABLE:
            self.running = False
            return
        try:
            idx = self.camera_info.get("index", 0)
            with _suppress_stderr():
                self.cap = _try_open_camera(idx)
            if not self.cap or not self.cap.isOpened():
                self.running = False
                return
            with _suppress_stderr():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception as e:
            print(f"[CameraStream] USB start error ({self.camera_id}): {e}", flush=True)
            self.running = False

    def _stream_loop(self):
        if self.udp_port:
            try:
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            except Exception as e:
                print(f"[CameraStream] UDP socket error: {e}", flush=True)

        frame_id = 0
        interval = 1.0 / self.fps

        while self.running:
            t0 = time.time()
            frame = None

            try:
                if self.camera_info["type"] == "realsense" and self.pipeline and np:
                    try:
                        with _suppress_stderr():
                            frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                            cf = frames.get_color_frame()
                            if cf:
                                frame = np.asanyarray(cf.get_data())
                    except Exception:
                        time.sleep(0.05)
                        continue
                elif self.cap:
                    with _suppress_stderr():
                        ret, frame = self.cap.read()
                    if not ret:
                        time.sleep(0.05)
                        continue

                if frame is not None:
                    self.frame_queue.append(frame.copy())
                    self._frame_event.set()

                    if self.udp_port and self.udp_socket and CV2_AVAILABLE:
                        try:
                            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                            _, buf = cv2.imencode('.jpg', frame, encode_param)
                            _send_udp_frame(self.udp_socket, buf.tobytes(),
                                            self.udp_port, frame_id)
                            frame_id = (frame_id + 1) & 0xFFFFFFFF
                        except Exception:
                            pass

            except Exception as e:
                time.sleep(0.05)
                continue

            # Выдерживаем FPS
            elapsed = time.time() - t0
            sleep_t = interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

        self._cleanup()

    def _cleanup(self):
        if self.cap:
            try:
                with _suppress_stderr():
                    self.cap.release()
            except Exception:
                pass
            self.cap = None
        if self.pipeline:
            try:
                with _suppress_stderr():
                    self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            self.udp_socket = None

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        self._cleanup()

    def get_latest_frame(self, width: int = None, height: int = None,
                         quality: int = 80, wait: bool = True) -> Optional[bytes]:
        """Возвращает последний кадр в виде JPEG bytes."""
        if wait:
            self._frame_event.wait(timeout=0.5)
            self._frame_event.clear()

        if not self.frame_queue or not CV2_AVAILABLE:
            return None

        try:
            frame = self.frame_queue[-1].copy()
            if width and height and (width != frame.shape[1] or height != frame.shape[0]):
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buf = cv2.imencode('.jpg', frame, encode_param)
            return buf.tobytes()
        except Exception:
            return None


# ─── Публичный API ─────────────────────────────────────────────────────────────

def get_camera_stream(camera_id: str) -> Optional[CameraStream]:
    with _streams_lock:
        return _camera_streams.get(camera_id, {}).get("stream")


def start_camera_stream(camera_id: str, udp_port: int = None,
                        width: int = None, height: int = None) -> bool:
    """Запускает стрим по camera_id. UDP для первых 3 камер назначается автоматически."""
    cameras = detect_cameras()
    camera_info = _find_camera(camera_id, cameras)

    if not camera_info:
        print(f"[CameraStream] Camera '{camera_id}' not found. Available: {[c['id'] for c in cameras]}", flush=True)
        return False

    with _streams_lock:
        if camera_id in _camera_streams:
            return True  # уже запущен

        cam_idx = camera_info.get("index", 0)

        # UDP для первых 3 камер
        if udp_port is None and cam_idx < 3:
            udp_port = 5005 + cam_idx

        # Разрешение: для UDP хотим максимальное, иначе 640x480
        if width is None:
            width = 1280 if udp_port else 640
        if height is None:
            height = 720 if udp_port else 480

        stream = CameraStream(camera_info, udp_port=udp_port, width=width, height=height)
        stream.start()

        if stream.running:
            _camera_streams[camera_id] = {
                "stream": stream,
                "camera_info": camera_info,
                "started_at": time.time()
            }
            return True

    return False


def stop_camera_stream(camera_id: str) -> bool:
    with _streams_lock:
        if camera_id in _camera_streams:
            _camera_streams[camera_id]["stream"].stop()
            del _camera_streams[camera_id]
            return True
    return False


def get_all_streams() -> Dict:
    with _streams_lock:
        return {
            cid: {
                "camera_info": info["camera_info"],
                "started_at": info["started_at"],
                "running": info["stream"].running,
                "udp_port": info["stream"].udp_port,
            }
            for cid, info in _camera_streams.items()
        }


# ─── Цикл сервиса ──────────────────────────────────────────────────────────────

def run_service_loop():
    service_name = get_service_name()
    try:
        manager = services_manager.get_services_manager()
    except Exception as e:
        print(f"[CameraStream] services_manager error: {e}", flush=True)
        return

    print("[CameraStream] Service started", flush=True)
    status.register_service_data(service_name, {
        "status": "running",
        "started_at": time.time(),
        "cameras_detected": 0,
        "streams_active": 0
    })

    while True:
        try:
            svc_info = manager.get_service(service_name)
            svc_status = svc_info.get("status", "ON")

            if svc_status == "OFF":
                print("[CameraStream] Service OFF — stopping all streams", flush=True)
                for cid in list(_camera_streams.keys()):
                    stop_camera_stream(cid)
                status.unregister_service_data(service_name)
                break
            elif svc_status == "SLEEP":
                time.sleep(1)
                continue

            cameras = detect_cameras()
            prev = status.get_service_data(service_name) or {}
            status.register_service_data(service_name, {
                "status": "running",
                "started_at": prev.get("started_at", time.time()),
                "cameras_detected": len(cameras),
                "streams_active": len(_camera_streams),
                "cameras": cameras
            })
            time.sleep(5)

        except KeyboardInterrupt:
            for cid in list(_camera_streams.keys()):
                stop_camera_stream(cid)
            status.unregister_service_data(service_name)
            break
        except Exception as e:
            print(f"[CameraStream] Error: {e}", flush=True)
            time.sleep(1)


def run():
    if not CV2_AVAILABLE and not REALSENSE_AVAILABLE:
        print("[CameraStream] Warning: OpenCV/RealSense not available", flush=True)
    run_service_loop()


if __name__ == '__main__':
    run()

"""
Camera stream service: camera discovery + live frame streaming helpers.
Supports RealSense and V4L2 USB cameras.
"""
import contextlib
import os
import socket
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services_manager
import status

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    np = None

try:
    import pyrealsense2 as rs
    REALSENSE_AVAILABLE = True
except ImportError:
    REALSENSE_AVAILABLE = False

SERVICE_NAME = "camera_stream"
REALSENSE_UDP_PORT = 5006

_camera_streams: Dict[str, Dict] = {}
_streams_lock = threading.Lock()


@contextlib.contextmanager
def _suppress_stderr():
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
    if not CV2_AVAILABLE:
        return None
    for backend in (cv2.CAP_V4L2, cv2.CAP_ANY, cv2.CAP_V4L):
        cap = None
        try:
            with _suppress_stderr():
                cap = cv2.VideoCapture(camera_idx, backend)
            if not cap or not cap.isOpened():
                if cap:
                    cap.release()
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap
            cap.release()
        except Exception:
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
    return None


def detect_cameras() -> List[Dict]:
    cameras: List[Dict] = []
    if CV2_AVAILABLE:
        for i in range(10):
            cap = _try_open_camera(i)
            if cap is None:
                continue
            try:
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                cameras.append({
                    "id": f"usb_{i}",
                    "type": "usb",
                    "name": f"USB Camera {i}",
                    "device_path": f"/dev/video{i}",
                    "index": i,
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "available": True,
                })
            finally:
                cap.release()

    if REALSENSE_AVAILABLE:
        try:
            ctx = rs.context()
            for idx, dev in enumerate(ctx.query_devices()):
                cameras.append({
                    "id": f"realsense_{idx}",
                    "type": "realsense",
                    "name": f"RealSense {dev.get_info(rs.camera_info.name)}",
                    "serial": dev.get_info(rs.camera_info.serial_number),
                    "index": idx,
                    "available": True,
                })
        except Exception:
            pass
    return cameras


def _find_camera(camera_id: str, cameras: List[Dict]) -> Optional[Dict]:
    for cam in cameras:
        if cam.get("id") == camera_id:
            return cam
    return None


class CameraStream:
    def __init__(self, camera_info: Dict, udp_port: int = None, width: int = 640, height: int = 480, fps: int = 25):
        self.camera_info = camera_info
        self.udp_port = udp_port
        self.width = width
        self.height = height
        self.fps = fps
        self.running = False
        self.cap = None
        self.pipeline = None
        self.thread = None
        self.frame_queue = deque(maxlen=1)
        self.frame_event = threading.Event()
        self.stop_event = threading.Event()
        self.udp_socket = None

    def _start_realsense(self) -> bool:
        if not REALSENSE_AVAILABLE:
            return False
        try:
            self.pipeline = rs.pipeline()
            config = rs.config()
            serial = self.camera_info.get("serial")
            if serial:
                config.enable_device(serial)
            config.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
            self.pipeline.start(config)
            frames = self.pipeline.wait_for_frames(timeout_ms=2000)
            return bool(frames and frames.get_color_frame())
        except Exception:
            return False

    def _start_usb(self) -> bool:
        self.cap = _try_open_camera(self.camera_info.get("index", 0))
        if not self.cap:
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        ok, frame = self.cap.read()
        return bool(ok and frame is not None)

    def start(self) -> bool:
        if self.running:
            return True
        if self.camera_info.get("type") == "realsense":
            if not self._start_realsense():
                return False
        else:
            if not self._start_usb():
                return False
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def _loop(self):
        if self.udp_port:
            try:
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            except Exception:
                self.udp_socket = None

        while self.running and not self.stop_event.is_set():
            frame = None
            try:
                if self.camera_info.get("type") == "realsense" and self.pipeline:
                    frames = self.pipeline.wait_for_frames(timeout_ms=1000)
                    color = frames.get_color_frame() if frames else None
                    if color is not None:
                        frame = np.asanyarray(color.get_data())
                elif self.cap:
                    ok, frame = self.cap.read()
                    if not ok:
                        frame = None
                if frame is not None:
                    self.frame_queue.clear()
                    self.frame_queue.append(frame.copy())
                    self.frame_event.set()
            except Exception:
                pass
            time.sleep(max(0.01, 1.0 / max(1, self.fps)))
        self._cleanup()

    def get_latest_frame(self, quality: int = 80, wait: bool = True) -> Optional[bytes]:
        if not CV2_AVAILABLE:
            return None
        if wait:
            self.frame_event.wait(timeout=0.5)
            self.frame_event.clear()
        if not self.frame_queue:
            return None
        try:
            frame = self.frame_queue[-1]
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok and buf is not None:
                return buf.tobytes()
        except Exception:
            return None
        return None

    def stop(self):
        self.running = False
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self._cleanup()

    def _cleanup(self):
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        if self.pipeline:
            try:
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


def get_camera_stream(camera_id: str) -> Optional[CameraStream]:
    with _streams_lock:
        return _camera_streams.get(camera_id, {}).get("stream")


def start_camera_stream(camera_id: str, udp_port: int = None, width: int = None, height: int = None) -> bool:
    cameras = detect_cameras()
    info = _find_camera(camera_id, cameras)
    if not info:
        return False
    with _streams_lock:
        if camera_id in _camera_streams:
            return True
        if info["type"] == "realsense":
            udp_port = REALSENSE_UDP_PORT if udp_port is None else udp_port
            width = 1024 if width is None else width
            height = 576 if height is None else height
        else:
            idx = info.get("index", 0)
            if udp_port is None and idx < 3:
                udp_port = 5005 + idx
            width = 1024 if width is None and udp_port else (640 if width is None else width)
            height = 576 if height is None and udp_port else (480 if height is None else height)
        stream = CameraStream(info, udp_port=udp_port, width=width, height=height, fps=25)
        if not stream.start():
            return False
        _camera_streams[camera_id] = {
            "stream": stream,
            "camera_info": info,
            "started_at": time.time(),
            "udp_port": udp_port,
        }
        return True


def stop_camera_stream(camera_id: str) -> bool:
    with _streams_lock:
        if camera_id not in _camera_streams:
            return False
        _camera_streams[camera_id]["stream"].stop()
        del _camera_streams[camera_id]
        return True


def get_all_streams() -> Dict:
    with _streams_lock:
        return {
            cid: {
                "camera_info": data["camera_info"],
                "started_at": data["started_at"],
                "running": data["stream"].running,
                "udp_port": data.get("udp_port"),
            }
            for cid, data in _camera_streams.items()
        }


def run_service_loop():
    manager = services_manager.get_services_manager()
    status.register_service_data(SERVICE_NAME, {"status": "running", "started_at": time.time()})
    while True:
        try:
            service = manager.get_service(SERVICE_NAME)
            st = service.get("status", "ON")
            if st == "OFF":
                for cid in list(_camera_streams.keys()):
                    stop_camera_stream(cid)
                status.unregister_service_data(SERVICE_NAME)
                break
            if st == "SLEEP":
                time.sleep(1)
                continue
            cameras = detect_cameras()
            status.register_service_data(SERVICE_NAME, {
                "status": "running",
                "cameras_detected": len(cameras),
                "streams_active": len(_camera_streams),
                "cameras": cameras,
                "realsense_udp_port": REALSENSE_UDP_PORT,
            })
            time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(1)


def run():
    run_service_loop()


if __name__ == "__main__":
    run()
"""
Сервис для захвата видео с камер и трансляции через UDP и HTTP MJPEG.
Поддерживает RealSense и обычные USB камеры с улучшенной стабильностью.
"""
import os
import sys
import time
import threading
import socket
import warnings
import contextlib
import atexit
from pathlib import Path
from typing import Dict, Optional, List
from collections import deque
from queue import Queue, Empty, Full

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
_streams_lock = threading.RLock()

# UDP порт для RealSense стрима (отдельный стабильный порт)
REALSENSE_UDP_PORT = 5006

# Быстрое завершение: короткий poll RealSense, быстрый join после release устройства
_STREAM_JOIN_TIMEOUT_SEC = float(os.environ.get("RGW2_CAMERA_JOIN_TIMEOUT", "0.85"))
_RS_LOOP_POLL_MS = int(os.environ.get("RGW2_CAMERA_RS_POLL_MS", "350"))


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
    """Попытка открыть USB камеру через V4L2 backend'ы. Возвращает VideoCapture или None.

    CAP_ANY намеренно исключён: на системах с GStreamer он может выбрать gst-launch
    pipeline с внутренней очередью ~1 сек, что добавляет скрытую задержку.
    Используем только низкоуровневые V4L2 бэкенды.
    """
    if not CV2_AVAILABLE:
        return None

    backends = [cv2.CAP_V4L2, cv2.CAP_V4L]

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
                            "fps": fps if fps > 0 else 25.0,
                            "available": True
                        })
                    finally:
                        with _suppress_stderr():
                            cap.release()
            except Exception:
                pass

    # Fallback: если OpenCV не доступен или нет прав открыть камеру, всё равно
    # показываем устройства /dev/video* в списке (available будет False без прав).
    try:
        existing_ids = {c.get("id") for c in cameras if isinstance(c, dict)}
        for i in range(10):
            dev_path = f"/dev/video{i}"
            if not os.path.exists(dev_path):
                continue
            cam_id = f"usb_{i}"
            if cam_id in existing_ids:
                continue
            can_rw = os.access(dev_path, os.R_OK | os.W_OK)
            cameras.append({
                "id": cam_id,
                "type": "usb",
                "name": f"USB Camera {i}",
                "device_path": dev_path,
                "index": i,
                "width": 640,
                "height": 480,
                "fps": 25.0,
                "available": bool(can_rw),
            })
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


def get_selected_cameras() -> List[Dict]:
    """
    Возвращает выбранные камеры: всегда usb_2 и еще одну из usb_1, usb_3, usb_4, usb_5.
    Перебирает от 1 до 5 без повторений, если не получается захватить - ничего не возвращает.
    """
    all_cameras = detect_cameras()
    # Показываем только реально доступные USB-камеры.
    usb_cameras = [
        cam for cam in all_cameras
        if str(cam.get("id", "")).startswith("usb_") and bool(cam.get("available", True))
    ]
    selected = []
    
    # Предпочитаем usb_2, но не "ломаем" список если она недоступна (например, нет прав).
    usb_2_camera = next((cam for cam in usb_cameras if cam.get("id") == "usb_2"), None)
    if usb_2_camera:
        selected.append(usb_2_camera)
    else:
        # Fallback: берём первую доступную USB-камеру
        first_usb = next((cam for cam in usb_cameras), None)
        if first_usb:
            selected.append(first_usb)
        else:
            return []
    
    # Перебираем usb_1, usb_3, usb_4, usb_5 без повторений
    candidates = [1, 3, 4, 5]  # Исключаем 2, так как уже добавили
    for idx in candidates:
        camera_id = f"usb_{idx}"
        for cam in usb_cameras:
            if cam.get("id") == camera_id:
                # Проверяем, что камера не usb_2 (на случай если она уже добавлена)
                if cam.get("id") != "usb_2":
                    selected.append(cam)
                    return selected  # Возвращаем как только нашли одну
    
    # Если не нашли вторую камеру, возвращаем одну
    return selected


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


def _send_udp_frame(sock: socket.socket, frame_bytes: bytes, port: int, frame_id: int, host: str = '127.0.0.1'):
    """Отправляет JPEG кадр по UDP с фрагментацией если нужно."""
    total = (len(frame_bytes) + UDP_CHUNK_SIZE - 1) // UDP_CHUNK_SIZE
    total = max(1, total)
    for i in range(total):
        chunk = frame_bytes[i * UDP_CHUNK_SIZE:(i + 1) * UDP_CHUNK_SIZE]
        # header: frame_id (4 bytes BE) + chunk_idx (2 bytes BE) + total_chunks (2 bytes BE)
        header = (frame_id & 0xFFFFFFFF).to_bytes(4, 'big') + \
                 i.to_bytes(2, 'big') + total.to_bytes(2, 'big')
        try:
            sock.sendto(header + chunk, (host, port))
        except Exception:
            pass


class CameraStream:
    """Улучшенный поток для чтения кадров с камеры с автоматическим перезапуском."""
    
    def __init__(self, camera_info: Dict, udp_port: int = None,
                 width: int = 640, height: int = 480, fps: int = 25,
                 capture_fps: Optional[int] = None):
        self.camera_info = camera_info
        self.camera_id = camera_info["id"]
        self.udp_port = udp_port
        self.width = width
        self.height = height
        # Stream/encode pacing (background caching/UDP sending).
        # Capture FPS can be higher; we try not to constrain capture.
        self.stream_fps = int(fps)
        self.capture_fps = int(capture_fps) if capture_fps is not None else None
        # If enabled, we will explicitly set CAP_PROP_FPS for USB.
        # Default is disabled to avoid artificially constraining capture.
        self._usb_set_fps = int(os.environ.get("RGW2_CAMERA_SET_USB_FPS", "0")) == 1
        if self.capture_fps is not None:
            self.capture_fps = max(1, self.capture_fps)
        self.running = False
        self.thread: Optional[threading.Thread] = None  # encode/udp loop
        self.capture_thread: Optional[threading.Thread] = None  # capture loop (drop frames)
        self.cap = None
        self.pipeline = None
        self.udp_socket = None
        self.frame_queue: deque = deque(maxlen=1)  # Уменьшаем размер очереди до 1
        self._frame_event = threading.Event()
        # Cached JPEG to avoid per-client encoding spikes/lag
        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None
        self._latest_jpeg_ts: float = 0.0
        # Small cache for non-default (w,h,quality) JPEGs.
        # Keyed by encoded frame_id to avoid returning stale data.
        self._jpeg_cache: Dict[Tuple[int, int, int], Tuple[int, float, bytes]] = {}
        self._jpeg_cache_max_keys = int(os.environ.get("RGW2_CAMERA_JPEG_CACHE_KEYS", "6"))
        # Prefer lowering quality over lowering FPS for "real-time" feel.
        self._jpeg_quality = int(os.environ.get("RGW2_CAMERA_JPEG_QUALITY", "60"))
        # Hard cap on allowed buffering/latency: drop frames older than this.
        self._max_frame_age_sec = float(os.environ.get("RGW2_CAMERA_MAX_AGE_SEC", "0.5"))
        self.error_count = 0
        self.max_errors = 5
        self.last_frame_time = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        self._frame_lock = threading.Lock()
        self._latest_frame_raw: Optional["np.ndarray"] = None
        self._latest_frame_ts: float = 0.0
        self._latest_frame_id: int = 0
        # Moving average of capture FPS (for /control debug).
        self._capture_ts_window: deque = deque(maxlen=240)
        self._capture_fps_ma: float = 0.0
        # Best-effort CUDA availability for image operations.
        self._cuda_available = False
        try:
            self._cuda_available = bool(hasattr(cv2, "cuda") and cv2.cuda.getCudaEnabledDeviceCount() > 0)
        except Exception:
            self._cuda_available = False

    def get_capture_fps(self) -> Optional[float]:
        """Returns moving average capture FPS (seconds window), or None if not enough data."""
        if self._capture_fps_ma and self._capture_fps_ma > 0:
            return float(self._capture_fps_ma)
        return None
        
    def start(self):
        """Запуск потока камеры."""
        with self.lock:
            if self.running:
                return True
            try:
                self.stop_event.clear()
                if self.camera_info["type"] == "realsense":
                    if not self._start_realsense():
                        return False
                else:
                    if not self._start_usb():
                        return False
                
                self.running = True
                self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
                self.thread = threading.Thread(target=self._stream_loop, daemon=True)
                self.capture_thread.start()
                self.thread.start()
                return True
            except Exception as e:
                print(f"[CameraStream] Error starting camera {self.camera_id}: {e}", flush=True)
                return False

    def _push_frame(self, frame) -> None:
        try:
            with self._frame_lock:
                self._latest_frame_raw = frame
                self._latest_frame_ts = time.time()
                self._latest_frame_id = (self._latest_frame_id + 1) & 0x7FFFFFFF
            # Capture FPS moving average (1s window, best-effort).
            try:
                now_m = time.monotonic()
                self._capture_ts_window.append(now_m)
                cutoff = now_m - 1.0
                while self._capture_ts_window and self._capture_ts_window[0] < cutoff:
                    self._capture_ts_window.popleft()
                if len(self._capture_ts_window) >= 2:
                    span = max(1e-6, now_m - self._capture_ts_window[0])
                    self._capture_fps_ma = (len(self._capture_ts_window) - 1) / span
            except Exception:
                pass
            while len(self.frame_queue) > 0:
                try:
                    self.frame_queue.pop()
                except Exception:
                    break
            self.frame_queue.append(frame)
            self._frame_event.set()
            self.last_frame_time = time.time()
        except Exception:
            pass

    def _capture_loop(self):
        """Capture loop: keeps only newest frame (drop frames)."""
        while self.running and not self.stop_event.is_set():
            frame = None
            try:
                if self.camera_info["type"] == "realsense":
                    if not self.pipeline:
                        self.stop_event.wait(timeout=0.02)
                        continue
                    with _suppress_stderr():
                        frames = self.pipeline.wait_for_frames(timeout_ms=_RS_LOOP_POLL_MS)
                    if frames:
                        cf = frames.get_color_frame()
                        if cf:
                            frame = np.asanyarray(cf.get_data())
                else:
                    if not self.cap or (hasattr(self.cap, "isOpened") and not self.cap.isOpened()):
                        self.stop_event.wait(timeout=0.02)
                        continue
                    with _suppress_stderr():
                        if hasattr(self.cap, "grab") and self.cap.grab():
                            ok, fr = self.cap.retrieve()
                        else:
                            ok, fr = self.cap.read()
                    if ok and fr is not None:
                        frame = fr

                if frame is not None:
                    self._push_frame(frame.copy())
            except Exception:
                pass

            self.stop_event.wait(timeout=0.001)
    
    def _start_realsense(self) -> bool:
        """Запуск RealSense камеры с улучшенной обработкой ошибок."""
        if not REALSENSE_AVAILABLE:
            return False
        
        # Сначала закрываем старый pipeline если есть (с защитой от segfault)
        if self.pipeline is not None:
            try:
                with _suppress_stderr():
                    try:
                        if hasattr(self.pipeline, 'stop'):
                            self.pipeline.stop()
                    except (RuntimeError, AttributeError, Exception):
                        # Игнорируем ошибки при остановке
                        pass
            except Exception:
                pass
            finally:
                self.pipeline = None
                # Даем время системе освободить ресурсы
                time.sleep(0.1)
        
        # Небольшая пауза перед перезапуском
        time.sleep(0.5)
        
        try:
            with _suppress_stderr():
                self.pipeline = rs.pipeline()
                config = rs.config()
                serial = self.camera_info.get("serial", "")
                if serial:
                    config.enable_device(serial)
                config.enable_stream(rs.stream.color, self.width, self.height,
                                     rs.format.bgr8, int(self.capture_fps or self.stream_fps))
                self.pipeline.start(config)
                
                # Проверяем, что камера работает с правильной обработкой генератора
                try:
                    frames = self.pipeline.wait_for_frames(timeout_ms=2000)
                    if frames:
                        cf = frames.get_color_frame()
                        if cf:
                            # Успешно получили кадр
                            return True
                        else:
                            # Генератор вернул None, закрываем pipeline
                            raise RuntimeError("No color frame received")
                    else:
                        # Генератор вернул None
                        raise RuntimeError("No frames received")
                except StopIteration:
                    # Генератор закончился нормально, но это ошибка для нас
                    raise RuntimeError("Frame generator stopped unexpectedly")
                except Exception as frame_error:
                    # Ошибка при получении кадров, закрываем pipeline
                    raise frame_error
        except Exception as e:
            #print(f"[CameraStream] RealSense start error ({self.camera_id}): {e}", flush=True)
            # Гарантированно закрываем pipeline (с защитой от segfault)
            if self.pipeline is not None:
                try:
                    with _suppress_stderr():
                        try:
                            if hasattr(self.pipeline, 'stop'):
                                self.pipeline.stop()
                        except (RuntimeError, AttributeError, Exception):
                            # Игнорируем ошибки при остановке
                            pass
                except Exception:
                    pass
                finally:
                    self.pipeline = None
                    # Даем время системе освободить ресурсы
                    time.sleep(0.1)
            return False
    
    def _start_usb(self) -> bool:
        """Запуск USB камеры с улучшенной обработкой ошибок."""
        if not CV2_AVAILABLE:
            return False
        try:
            idx = self.camera_info.get("index", 0)
            with _suppress_stderr():
                self.cap = _try_open_camera(idx)
            if not self.cap or not self.cap.isOpened():
                #print(f"[CameraStream] USB open failed ({self.camera_id}) idx={idx} path={self.camera_info.get('device_path')}", flush=True)
                return False
            with _suppress_stderr():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if self.capture_fps is not None and self._usb_set_fps:
                    self.cap.set(cv2.CAP_PROP_FPS, self.capture_fps)
                # Request minimal V4L2 kernel buffer: 1 frame prevents stale-frame latency.
                # Note: some drivers ignore this, so we also drain below.
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # Drain V4L2 kernel buffer that accumulated during detect_cameras() probing.
            # Each grab() returns immediately when a frame is already queued, so this
            # is fast (<5 ms total) if frames were buffered; if none are queued it just
            # reads one warm-up frame.  This is the primary fix for 1-second latency on
            # cameras whose V4L2 driver doesn't honour BUFFERSIZE=1.
            with _suppress_stderr():
                for _ in range(5):
                    ret, _ = self.cap.read()
                    if not ret:
                        break

            # Final verification read
            with _suppress_stderr():
                ret, frame = self.cap.read()
            if ret and frame is not None:
                return True
            else:
                #print(f"[CameraStream] USB read failed ({self.camera_id}) idx={idx}", flush=True)
                self.cap.release()
                self.cap = None
                return False
        except Exception as e:
            #print(f"[CameraStream] USB start error ({self.camera_id}): {e}", flush=True)
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            return False

    def _restart_camera(self) -> bool:
        """Перезапуск камеры при проблемах."""
        try:
            # Закрываем текущий capture/pipeline с гарантированным освобождением
            if self.cap:
                try:
                    with _suppress_stderr():
                        self.cap.release()
                except Exception:
                    pass
                finally:
                    self.cap = None
            
            if self.pipeline is not None:
                try:
                    # Останавливаем pipeline с обработкой генератора (с защитой от segfault)
                    with _suppress_stderr():
                        try:
                            if hasattr(self.pipeline, 'stop'):
                                self.pipeline.stop()
                        except (RuntimeError, AttributeError, Exception) as stop_error:
                            # Даже если stop() выбросил исключение, продолжаем
                            print(f"[CameraStream] Pipeline stop error (ignored): {stop_error}", flush=True)
                except Exception as e:
                    print(f"[CameraStream] Pipeline cleanup error (ignored): {e}", flush=True)
                finally:
                    # Гарантированно очищаем ссылку
                    self.pipeline = None
                    # Даем время системе освободить ресурсы
                    time.sleep(0.1)
            
            # Пауза перед перезапуском для стабильности
            time.sleep(1.0)
            
            # Перезапускаем
            if self.camera_info["type"] == "realsense":
                return self._start_realsense()
            else:
                return self._start_usb()
                
        except Exception as e:
            #print(f"[CameraStream] Error restarting camera {self.camera_id}: {e}", flush=True)
            # Гарантируем очистку при ошибке (с защитой от segfault)
            if self.pipeline is not None:
                try:
                    with _suppress_stderr():
                        try:
                            if hasattr(self.pipeline, 'stop'):
                                self.pipeline.stop()
                        except (RuntimeError, AttributeError, Exception):
                            # Игнорируем ошибки при остановке
                            pass
                except Exception:
                    pass
                finally:
                    self.pipeline = None
                    # Даем время системе освободить ресурсы
                    time.sleep(0.1)
            return False
    
    def _stream_loop(self):
        """Encode+UDP loop at target FPS (stable)."""
        if self.udp_port:
            try:
                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception as e:
                print(f"[CameraStream] UDP socket error: {e}", flush=True)

        frame_id = 0
        interval = max(0.005, 1.0 / max(1, int(self.stream_fps)))
        last_encoded_local_id = -1

        while self.running and not self.stop_event.is_set():
            t0 = time.time()
            frame = None
            frame_ts = 0.0
            local_id = -1

            try:
                # Wait for a new frame (real-time), but keep loop responsive.
                self._frame_event.wait(timeout=min(interval, 0.2))
                with self._frame_lock:
                    local_id = int(self._latest_frame_id)
                    frame_ts = float(self._latest_frame_ts or 0.0)
                    if self._latest_frame_raw is not None:
                        frame = self._latest_frame_raw

                # We only encode on new frames; avoids jitter from re-encoding old frame.
                if local_id == last_encoded_local_id:
                    frame = None

                # Hard latency cap: if capture is stale, drop it and wait for fresh.
                if frame is not None and frame_ts > 0:
                    age = time.time() - frame_ts
                    if age > self._max_frame_age_sec:
                        frame = None
                    
                if frame is not None:
                    # Encode once per captured frame to keep stable FPS and reduce latency.
                    # Clients will reuse cached JPEG instead of encoding in each request.
                    encoded_jpeg: Optional[bytes] = None
                    if CV2_AVAILABLE:
                        try:
                            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(self._jpeg_quality)]
                            ok, buf = cv2.imencode('.jpg', frame, encode_param)
                            if ok and buf is not None:
                                encoded_jpeg = buf.tobytes()
                                with self._jpeg_lock:
                                    self._latest_jpeg = encoded_jpeg
                                    self._latest_jpeg_ts = time.time()
                        except Exception as e:
                            pass
                    last_encoded_local_id = local_id
                    # We consumed the newest frame; clear so waiters can block again.
                    # (capture thread will set again on next frame)
                    try:
                        self._frame_event.clear()
                    except Exception:
                        pass

                    # Отправка по UDP: используем уже закодированный JPEG (без повторного imencode)
                    if encoded_jpeg and self.udp_port and self.udp_socket:
                        try:
                            _send_udp_frame(self.udp_socket, encoded_jpeg, self.udp_port, frame_id)
                            frame_id = (frame_id + 1) & 0xFFFFFFFF
                        except Exception:
                            pass
                
            except Exception as e:
                self.error_count += 1
                self.consecutive_errors += 1
                if self.consecutive_errors >= self.max_consecutive_errors:
                    #print(f"[CameraStream] Critical error in stream loop {self.camera_id}: {e}", flush=True)
                    # При критической ошибке закрываем pipeline перед перезапуском
                    if self.pipeline:
                        try:
                            with _suppress_stderr():
                                self.pipeline.stop()
                        except Exception:
                            pass
                        finally:
                            self.pipeline = None
                    if self.stop_event.is_set() or not self.running:
                        break
                    try:
                        if self._restart_camera():
                            self.consecutive_errors = 0
                    except Exception as restart_error:
                        print(f"[CameraStream] Failed to restart camera {self.camera_id}: {restart_error}", flush=True)
                self.stop_event.wait(timeout=0.5)
                continue

            # Выдерживаем FPS; wait прерывается по stop_event (быстрая остановка сервиса)
            elapsed = time.time() - t0
            sleep_t = interval - elapsed
            if sleep_t > 0.001:
                self.stop_event.wait(timeout=min(sleep_t, 0.25))
        
        self._cleanup()

    def _release_hardware_unlocked(self) -> None:
        """Закрыть cap / pipeline / UDP до join — разблокирует cap.read() и wait_for_frames()."""
        if self.udp_socket is not None:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            finally:
                self.udp_socket = None

        if self.cap is not None:
            try:
                if hasattr(self.cap, 'isOpened') and self.cap.isOpened():
                    with _suppress_stderr():
                        self.cap.release()
                elif hasattr(self.cap, 'release'):
                    with _suppress_stderr():
                        self.cap.release()
            except Exception:
                pass
            finally:
                self.cap = None

        if self.pipeline is not None:
            try:
                with _suppress_stderr():
                    if hasattr(self.pipeline, 'stop'):
                        self.pipeline.stop()
            except Exception:
                pass
            finally:
                self.pipeline = None

    def _cleanup(self):
        """Идемпотентная очистка (cap/pipeline/UDP уже могли быть закрыты в stop())."""
        self._release_hardware_unlocked()

    def stop(self):
        """Остановка: закрываем железо до join, чтобы read()/wait_for_frames() не висели."""
        with self.lock:
            if not self.running:
                return
            self.running = False
            self.stop_event.set()
            thr = self.thread
            cap_thr = self.capture_thread
        self._release_hardware_unlocked()
        if cap_thr and cap_thr.is_alive():
            cap_thr.join(timeout=_STREAM_JOIN_TIMEOUT_SEC)
        if thr and thr.is_alive():
            thr.join(timeout=_STREAM_JOIN_TIMEOUT_SEC)
        with self.lock:
            self.thread = None
            self.capture_thread = None
        self._cleanup()
    
    def get_latest_frame(self, width: int = None, height: int = None,
                         quality: int = 80, wait: bool = True) -> Optional[bytes]:
        """Возвращает последний кадр в виде JPEG bytes с улучшенной резкостью и контрастностью."""
        if wait:
            # wait for at least one frame; do not clear event to avoid multi-client jitter
            self._frame_event.wait(timeout=0.5)

        # Fast path: return cached JPEG for default size/quality
        if width is None and height is None and int(quality) == int(self._jpeg_quality):
            with self._jpeg_lock:
                if self._latest_jpeg is not None and (time.time() - float(self._latest_jpeg_ts or 0.0)) <= self._max_frame_age_sec:
                    return self._latest_jpeg

        if not CV2_AVAILABLE:
            with self._jpeg_lock:
                return self._latest_jpeg

        try:
            # Read the newest frame atomically.
            with self._frame_lock:
                frame = self._latest_frame_raw
                frame_ts = float(self._latest_frame_ts or 0.0)
                frame_id = int(self._latest_frame_id or 0)

            if frame is None:
                return None

            # Hard realtime cap: do not encode frames older than allowed.
            if frame_ts > 0:
                age = time.time() - frame_ts
                if age > self._max_frame_age_sec:
                    return None

            # IMPORTANT (performance):
            # WebRTC requests often specify width/height and varying quality.
            # For these "non-default" requests we do a fast path: resize + JPEG encode only.
            non_default = bool(width or height or int(quality) != int(self._jpeg_quality))

            target_w = int(width) if width is not None else int(frame.shape[1])
            target_h = int(height) if height is not None else int(frame.shape[0])

            if non_default:
                key = (target_w, target_h, int(quality))
                cached = self._jpeg_cache.get(key)
                if cached is not None:
                    cached_frame_id, cached_ts, cached_bytes = cached
                    if cached_frame_id == frame_id:
                        return cached_bytes

                # Resize (best-effort GPU).
                out = frame
                if target_w != frame.shape[1] or target_h != frame.shape[0]:
                    if self._cuda_available:
                        try:
                            gpu = cv2.cuda_GpuMat()
                            gpu.upload(frame)
                            out_gpu = cv2.cuda.resize(gpu, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                            out = out_gpu.download()
                        except Exception:
                            out = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                    else:
                        out = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
                ok, buf = cv2.imencode('.jpg', out, encode_param)
                if not (ok and buf is not None):
                    return None

                jpg = buf.tobytes()
                if len(self._jpeg_cache) >= self._jpeg_cache_max_keys:
                    self._jpeg_cache.clear()
                self._jpeg_cache[key] = (frame_id, time.time(), jpg)
                return jpg

            # Default request path: apply mild enhancement (used by MJPEG and default cache).
            frame_enhanced = cv2.convertScaleAbs(frame, alpha=1.2, beta=0)
            gaussian = cv2.GaussianBlur(frame_enhanced, (0, 0), 2.0)
            frame_enhanced = cv2.addWeighted(frame_enhanced, 1.2, gaussian, -0.2, 0)
            frame_enhanced = np.clip(frame_enhanced, 0, 255).astype(np.uint8)

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
            ok, buf = cv2.imencode('.jpg', frame_enhanced, encode_param)
            if ok and buf is not None:
                return buf.tobytes()
        except Exception:
            return None


# ─── Публичный API ─────────────────────────────────────────────────────────────

def get_camera_stream(camera_id: str) -> Optional[CameraStream]:
    with _streams_lock:
        return _camera_streams.get(camera_id, {}).get("stream")


def start_camera_stream(camera_id: str, udp_port: int = None,
                        width: int = None, height: int = None) -> bool:
    """Запускает стрим по camera_id. RealSense автоматически получает UDP порт 5006."""
    cameras = detect_cameras()
    camera_info = _find_camera(camera_id, cameras)
    
    if not camera_info:
        #print(f"[CameraStream] Camera '{camera_id}' not found. Available: {[c['id'] for c in cameras]}", flush=True)
        return False
    
    with _streams_lock:
        if camera_id in _camera_streams:
            return True  # уже запущен

    cam_idx = camera_info.get("index", 0)
    stream_fps_env = int(os.environ.get("RGW2_CAMERA_STREAM_FPS", "25"))

    # UDP-поток (если udp_port задан извне) используется для UDP/MJPEG сценариев.
    if camera_info["type"] == "realsense":
        # Для WebRTC (когда udp_port не задан) оставляем параметры, ориентированные на 640x480.
        if width is None:
            width = 640 if udp_port is None else 1024
        if height is None:
            height = 480 if udp_port is None else 576
        capture_fps = int(os.environ.get("RGW2_CAPTURE_FPS", "60"))
        stream_fps = min(stream_fps_env, capture_fps)
    else:
        # Разрешение: для UDP 80% от максимального, иначе 640x480
        if width is None:
            width = 1024 if udp_port else 640  # 80% от 1280
        if height is None:
            height = 576 if udp_port else 480  # 80% от 720
        capture_fps = camera_info.get("fps")
        capture_fps = int(capture_fps) if capture_fps else int(os.environ.get("RGW2_CAPTURE_FPS", "30"))
        stream_fps = min(stream_fps_env, capture_fps)

    # Инициализация стрима выполняется вне лока — может занимать 0.5–1.5 сек
    stream = CameraStream(
        camera_info,
        udp_port=udp_port,
        width=width,
        height=height,
        fps=stream_fps,
        capture_fps=capture_fps,
    )
    if not stream.start():
        #print(f"[CameraStream] Failed to start stream for {camera_id}", flush=True)
        return False

    with _streams_lock:
        # Повторная проверка после захвата лока: параллельный вызов мог успеть запустить стрим
        if camera_id in _camera_streams:
            stream.stop()
            return True
        _camera_streams[camera_id] = {
            "stream": stream,
            "camera_info": camera_info,
            "started_at": time.time(),
            "udp_port": udp_port
        }
        #print(f"[CameraStream] Started camera {camera_id} with UDP port {udp_port}", flush=True)

    return True


def stop_camera_stream(camera_id: str) -> bool:
    stream = None
    with _streams_lock:
        entry = _camera_streams.pop(camera_id, None)
        if entry is not None:
            stream = entry.get("stream")
    if stream is not None:
        stream.stop()
        return True
    return False


def get_all_streams() -> Dict:
    with _streams_lock:
        return {
            cid: {
                "camera_info": info["camera_info"],
                "started_at": info["started_at"],
                "running": info["stream"].running,
                "udp_port": info.get("udp_port"),
            }
            for cid, info in _camera_streams.items()
        }


# ─── Цикл сервиса ──────────────────────────────────────────────────────────────

def _cleanup_all_streams():
    """Безопасная очистка всех потоков камер при завершении."""
    print("[CameraStream] Cleaning up all camera streams...", flush=True)
    snapshots = []
    with _streams_lock:
        snapshots = [(cid, data["stream"]) for cid, data in list(_camera_streams.items())]
        _camera_streams.clear()
    for cid, stream in snapshots:
        try:
            stream.stop()
        except Exception as e:
            print(f"[CameraStream] Error stopping stream {cid}: {e}", flush=True)
    print("[CameraStream] All streams cleaned up", flush=True)


def run_service_loop():
    service_name = get_service_name()
    
    # Регистрируем очистку при завершении (atexit работает в любом потоке)
    # signal.signal() работает только в главном потоке, поэтому не используем его здесь
    atexit.register(_cleanup_all_streams)
    
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
    
    try:
        while True:
            try:
                svc_info = manager.get_service(service_name)
                svc_status = svc_info.get("status", "ON")
                
                if svc_status == "OFF":
                    print("[CameraStream] Service OFF — stopping all streams", flush=True)
                    _cleanup_all_streams()
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
                    "cameras": cameras,
                    "realsense_udp_port": REALSENSE_UDP_PORT
                })
                time.sleep(5)
                
            except KeyboardInterrupt:
                _cleanup_all_streams()
                status.unregister_service_data(service_name)
                break
            except Exception as e:
                print(f"[CameraStream] Error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(1)
    finally:
        # Гарантированная очистка при любом завершении
        _cleanup_all_streams()


def run():
    if not CV2_AVAILABLE and not REALSENSE_AVAILABLE:
        print("[CameraStream] Warning: OpenCV/RealSense not available", flush=True)
    run_service_loop()


if __name__ == '__main__':
    run()

"""
Хост-агент удалённого стола: регистрируется на сервере, отдаёт картинку экрана(ов),
принимает события мыши и клавиатуры. Запускается как сервис RGW (или вручную).
"""
import asyncio
import io
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services_manager
import status

from services.remote_desktop.protocol import (
    TYPE_JSON,
    TYPE_FRAME,
    encode_message,
    read_message,
    MSG_MOUSE,
    MSG_KEY,
    MSG_OK,
    MSG_ERROR,
)

# Опциональные зависимости (установить: pip install mss Pillow pynput)
try:
    import mss
    import mss.tools
except ImportError:
    mss = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:
    from pynput.mouse import Controller as MouseController, Button
    from pynput.keyboard import Controller as KeyboardController, Key
except ImportError:
    MouseController = KeyboardController = Button = Key = None

DEFAULT_SERVER_PORT = 9009
DEFAULT_WAKE_PASSWORD = "1055"
SERVICE_NAME = "remote_desktop"

# Глобальный ингибитор сна (subprocess или None)
_sleep_inhibit_process = None


def _get_pc_name():
    return os.environ.get("RGW_PC_NAME", socket.gethostname()) or "pc"


def _get_mac_address():
    """Первый не-loopback MAC для Wake-on-LAN (Linux)."""
    try:
        for name in ("eth0", "enp0s3", "eno1", "enp0s25", "wlan0"):
            path = Path("/sys/class/net") / name / "address"
            if path.exists():
                return path.read_text().strip()
        for p in Path("/sys/class/net").iterdir():
            if p.is_dir() and not p.name.startswith("lo"):
                f = p / "address"
                if f.exists():
                    return f.read_text().strip()
    except Exception:
        pass
    return ""


def _start_sleep_inhibit():
    """Предотвращение перехода в сон (Ubuntu 24)."""
    global _sleep_inhibit_process
    if _sleep_inhibit_process is not None:
        return
    try:
        import subprocess
        _sleep_inhibit_process = subprocess.Popen(
            [
                "systemd-inhibit",
                "--what=idle:sleep",
                "--who=rgw-remote-desktop",
                "--why=active_remote_session",
                "--mode=block",
                "sleep",
                "infinity",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _stop_sleep_inhibit():
    global _sleep_inhibit_process
    if _sleep_inhibit_process is not None:
        try:
            _sleep_inhibit_process.terminate()
            _sleep_inhibit_process.wait(timeout=2)
        except Exception:
            _sleep_inhibit_process.kill()
        _sleep_inhibit_process = None


def send_json(writer: asyncio.StreamWriter, obj: dict):
    data = encode_message(TYPE_JSON, json.dumps(obj).encode("utf-8"))
    writer.write(data)


def send_frame(writer: asyncio.StreamWriter, frame_bytes: bytes):
    writer.write(encode_message(TYPE_FRAME, frame_bytes))


def _placeholder_frame() -> bytes:
    """Минимальный JPEG 320x240 (серый) — если захват недоступен."""
    if not Image:
        return b""
    try:
        pil = Image.new("RGB", (320, 240), color=(64, 64, 64))
        buf = io.BytesIO()
        pil.save(buf, "JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        return b""


def _capture_all_screens(quality: int = 60) -> bytes | None:
    """Захват всех мониторов в один JPEG. При ошибке — заглушка."""
    if not mss or not Image:
        return _placeholder_frame() or None
    try:
        with mss.mss() as sct:
            mon_all = sct.monitors[0]
            img = sct.grab(mon_all)
            pil = Image.frombytes("RGB", (img.width, img.height), img.rgb)
            buf = io.BytesIO()
            pil.save(buf, "JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return _placeholder_frame() or None


def _apply_mouse(msg: dict):
    if not MouseController:
        return
    try:
        ctrl = MouseController()
        scroll = msg.get("scroll")
        if scroll:
            # Скролл: не двигаем мышь, только прокручиваем
            dx = msg.get("dx", 0)
            dy = msg.get("dy", 0)
            ctrl.scroll(int(dx), int(dy))
        else:
            # Обычное движение/клик: двигаем мышь и обрабатываем кнопки
            x = msg.get("x")
            y = msg.get("y")
            if x is not None and y is not None:
                ctrl.position = (int(x), int(y))
            btn = msg.get("button")
            pressed = msg.get("pressed", True)
            if btn is not None:
                if btn == "left":
                    b = Button.left
                elif btn == "right":
                    b = Button.right
                else:
                    b = Button.middle
                if pressed:
                    ctrl.press(b)
                else:
                    ctrl.release(b)
    except Exception:
        pass


# Сопоставление нашего формата -> pynput Key
_KEY_MAP = {
    "return": "enter",
    "escape": "esc",
    "prior": "page_up",
    "next": "page_down",
    "num_lock": "num_lock",
    "backspace": "backspace",
    "tab": "tab",
    "space": "space",
    "delete": "delete",
    "home": "home",
    "end": "end",
    "insert": "insert",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "alt_l": "alt_l",
    "alt_r": "alt_r",
    "ctrl_l": "ctrl_l",
    "ctrl_r": "ctrl_r",
    "shift_l": "shift_l",
    "shift_r": "shift_r",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
}


def _key_from_name(name: str):
    if not name:
        return name
    base = name.replace("Key.", "").lower()
    base = _KEY_MAP.get(base, base)
    try:
        k = getattr(Key, base, None)
        if k is not None:
            return k
    except Exception:
        pass
    return name if len(name) == 1 else name


def _apply_key(msg: dict):
    if not KeyboardController:
        return
    try:
        ctrl = KeyboardController()
        key = msg.get("key")
        pressed = msg.get("pressed", True)
        if key is None:
            return
        k = _key_from_name(key)
        if pressed:
            ctrl.press(k)
        else:
            ctrl.release(k)
    except Exception:
        pass


async def host_loop(server_host: str, server_port: int, pc_name: str, wake_password: str):
    status.register_service_data(SERVICE_NAME, {
        "status": "connecting",
        "server": f"{server_host}:{server_port}",
        "pc_name": pc_name,
    })
    try:
        reader, writer = await asyncio.open_connection(server_host, server_port)
    except Exception as e:
        status.register_service_data(SERVICE_NAME, {"status": "error", "error": str(e)})
        print(f"[RemoteDesktop] Cannot connect to server: {e}", flush=True)
        return
    # Регистрация (mac для Wake-on-LAN при пробуждении)
    send_json(writer, {
        "type": "host_register",
        "name": pc_name,
        "wake_password": wake_password,
        "mac": _get_mac_address(),
    })
    await writer.drain()
    msg, _ = await read_message(reader)
    if not msg or msg.get("type") != MSG_OK:
        status.register_service_data(SERVICE_NAME, {"status": "error", "error": "Registration failed"})
        writer.close()
        await writer.wait_closed()
        return
    _start_sleep_inhibit()
    status.register_service_data(SERVICE_NAME, {
        "status": "running",
        "server": f"{server_host}:{server_port}",
        "pc_name": pc_name,
        "host_id": msg.get("host_id"),
    })
    print(f"[RemoteDesktop] Registered as {pc_name}", flush=True)
    frame_interval = 1 / 15  # 15 FPS
    last_frame = 0
    try:
        while True:
            # Отправка кадра
            now = time.monotonic()
            if now - last_frame >= frame_interval:
                frame_bytes = _capture_all_screens()
                if frame_bytes:
                    send_frame(writer, frame_bytes)
                    await writer.drain()
                last_frame = now
            # Чтение входящих (mouse/key) с таймаутом
            try:
                msg_or_frame, _ = await asyncio.wait_for(read_message(reader), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            if msg_or_frame is None:
                break
            if isinstance(msg_or_frame, dict):
                t = msg_or_frame.get("type")
                if t == MSG_MOUSE:
                    _apply_mouse(msg_or_frame)
                elif t == MSG_KEY:
                    _apply_key(msg_or_frame)
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    except Exception as e:
        print(f"[RemoteDesktop] Error: {e}", flush=True)
    finally:
        _stop_sleep_inhibit()
        status.unregister_service_data(SERVICE_NAME)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print("[RemoteDesktop] Disconnected", flush=True)


def _load_config_file():
    """Читает server_host и server_port из config.txt в папке сервиса."""
    cfg = Path(__file__).parent / "config.txt"
    out = {}
    if not cfg.exists():
        return out
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                key, _, val = line.partition("=")
                key, val = key.strip().lower(), val.strip()
                if key == "server_host":
                    out["server_host"] = val
                elif key == "server_port" and val.isdigit():
                    out["server_port"] = int(val)
    except Exception:
        pass
    return out


def run():
    """Точка входа для RGW: запуск хоста. IP берётся из config.txt или из параметров сервиса."""
    service_name = SERVICE_NAME
    file_cfg = _load_config_file()
    manager = services_manager.get_services_manager()
    params = manager.get_service_parameters(service_name)
    server_host = (file_cfg.get("server_host") or params.get("server_host") or "").strip()
    server_port = file_cfg.get("server_port") or int(params.get("server_port", DEFAULT_SERVER_PORT))
    pc_name = (params.get("pc_name") or _get_pc_name()).strip() or _get_pc_name()
    wake_password = str(params.get("wake_password", DEFAULT_WAKE_PASSWORD))
    if not server_host:
        print("[RemoteDesktop] server_host не задан. Укажите IP в services/remote_desktop/config.txt или в параметрах сервиса.", flush=True)
        return
    if not mss or not Image:
        print("[RemoteDesktop] Install: pip install mss Pillow pynput", flush=True)
        return
    asyncio.run(host_loop(server_host, server_port, pc_name, wake_password))


if __name__ == "__main__":
    run()

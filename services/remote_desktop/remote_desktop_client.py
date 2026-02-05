"""
Клиент удалённого стола. Запуск ТОЛЬКО ВРУЧНУЮ.
Подключается к серверу, запрашивает список ПК, после выбора показывает экран и отправляет мышь/клавиатуру.

Запуск: python -m services.remote_desktop.remote_desktop_client [server_ip] [port]
Пример: python -m services.remote_desktop.remote_desktop_client 192.168.1.100 9009
"""
import io
import json
import queue
import socket
import struct
import sys
import threading
from pathlib import Path
from tkinter import Tk, Canvas, messagebox, simpledialog, TclError

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.remote_desktop.protocol import (
    TYPE_JSON,
    TYPE_FRAME,
    encode_message,
    LEN_FMT,
    HEADER_SIZE,
    MSG_HOST_LIST,
    MSG_HOST_SELECT,
    MSG_MOUSE,
    MSG_KEY,
)

try:
    from PIL import Image
except ImportError:
    Image = None

DEFAULT_PORT = 9009


def _load_client_config():
    """Читает server_host и server_port из config.txt в папке remote_desktop."""
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


class SocketReader:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                return buf
            buf += chunk
        return buf


def read_message_sync(reader: SocketReader):
    """Синхронное чтение одного сообщения. Returns (payload, msg_type) or (None, None)."""
    header = reader.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE:
        return None, None
    length, = struct.unpack(LEN_FMT, header[:4])
    msg_type = header[4]
    payload = reader.read(length)
    if len(payload) < length:
        return None, None
    if msg_type == TYPE_JSON:
        try:
            return json.loads(payload.decode("utf-8")), TYPE_JSON
        except Exception:
            return None, None
    return payload, msg_type


def send_json_sync(sock: socket.socket, obj: dict):
    data = encode_message(TYPE_JSON, json.dumps(obj).encode("utf-8"))
    sock.sendall(data)


def request_hosts(host: str, port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((host, port))
        reader = SocketReader(sock)
        send_json_sync(sock, {"type": MSG_HOST_LIST})
        msg, _ = read_message_sync(reader)
        sock.close()
        if msg and msg.get("type") == "hosts":
            return msg.get("hosts", [])
    except Exception:
        pass
    return None


def run_client_gui(server_host: str, server_port: int):
    hosts = request_hosts(server_host, server_port)
    if not hosts:
        messagebox.showerror("Ошибка", f"Не удалось получить список ПК от {server_host}:{server_port}")
        return
    # Всегда показываем выбор (даже если хост один)
    names = [h.get("name", "?") for h in hosts]
    idx = simpledialog.askinteger(
        "Выбор ПК",
        "Введите номер ПК (1..%d):\n\n%s" % (len(hosts), "\n".join("%d. %s" % (i + 1, n) for i, n in enumerate(names))),
        minvalue=1,
        maxvalue=len(hosts),
    )
    if idx is None:
        return
    choice = hosts[idx - 1]
    host_id = choice["host_id"]
    host_name = choice.get("name", host_id)
    # Подключаемся и переходим в режим управления
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    try:
        sock.connect((server_host, server_port))
    except Exception as e:
        messagebox.showerror("Ошибка", "Подключение к серверу: %s" % e)
        return
    send_json_sync(sock, {"type": MSG_HOST_SELECT, "host_id": host_id})
    reader = SocketReader(sock)
    msg, _ = read_message_sync(reader)
    if not msg or msg.get("type") != "ok":
        messagebox.showerror("Ошибка", msg.get("message", "Хост недоступен"))
        sock.close()
        return
    sock.settimeout(2.0)
    frame_queue = queue.Queue(maxsize=5)
    closed = threading.Event()

    def recv_thread():
        try:
            while not closed.is_set():
                m, t = read_message_sync(reader)
                if m is None:
                    break
                if t == TYPE_FRAME:
                    try:
                        frame_queue.put_nowait(m)
                    except queue.Full:
                        try:
                            frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                        frame_queue.put_nowait(m)
        except Exception:
            pass
        closed.set()

    th = threading.Thread(target=recv_thread, daemon=True)
    th.start()

    root = Tk()
    root.title("Удалённый стол — %s" % host_name)
    root.geometry("1024x768")
    canvas = Canvas(root, bg="gray20", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    # Размер удалённого экрана (обновляется с первого кадра; до этого мышь масштабируется по умолчанию)
    remote_size = [1920, 1080]
    photo_ref = []  # храним ссылку на PhotoImage, иначе GC удалит

    def update_image():
        if closed.is_set():
            try:
                root.destroy()
            except TclError:
                pass
            return
        try:
            frame_bytes = frame_queue.get_nowait()
        except queue.Empty:
            root.after(33, update_image)
            return
        if not Image:
            root.after(33, update_image)
            return
        try:
            from PIL import ImageTk
            pil = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
            remote_size[0], remote_size[1] = pil.size
            root.update_idletasks()
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw < 100:
                cw = 1024
            if ch < 100:
                ch = 768
            pil_scaled = pil.resize((cw, ch), getattr(Image, "Resampling", Image).LANCZOS)
            photo = ImageTk.PhotoImage(pil_scaled)
            photo_ref.append(photo)
            if len(photo_ref) > 3:
                photo_ref.pop(0)
            canvas.delete("all")
            canvas.create_image(0, 0, anchor="nw", image=photo)
        except Exception:
            pass
        root.after(1, update_image)

    def to_remote_xy(canvas_x, canvas_y):
        cw = max(canvas.winfo_width(), 1)
        ch = max(canvas.winfo_height(), 1)
        sx = remote_size[0] / cw
        sy = remote_size[1] / ch
        return int(canvas_x * sx), int(canvas_y * sy)

    def on_mouse_event(event, button=None, pressed=True):
        rx, ry = to_remote_xy(event.x, event.y)
        msg = {"type": MSG_MOUSE, "x": rx, "y": ry}
        if button:
            msg["button"] = button
            msg["pressed"] = pressed
        try:
            send_json_sync(sock, msg)
        except Exception:
            pass

    def on_motion(event):
        on_mouse_event(event)

    def on_click(event):
        btn = "left"
        if event.num == 3:
            btn = "right"
        elif event.num == 2:
            btn = "middle"
        on_mouse_event(event, button=btn, pressed=True)
        root.after(100, lambda: on_mouse_event(event, button=btn, pressed=False))

    def on_scroll(event):
        rx, ry = to_remote_xy(event.x, event.y)
        delta = -1 if event.delta > 0 else 1
        try:
            send_json_sync(sock, {"type": MSG_MOUSE, "x": rx, "y": ry, "scroll": True, "dx": 0, "dy": delta})
        except Exception:
            pass

    def send_key(key_str, pressed):
        try:
            send_json_sync(sock, {"type": MSG_KEY, "key": key_str, "pressed": pressed})
        except Exception:
            pass

    def on_key_press(event):
        # Для набора текста: event.char — символ с учётом раскладки и Shift (например "ф", "@")
        char = event.char
        if char and len(char) == 1:
            k = char
        else:
            key = event.keysym
            k = key if len(key) == 1 else "Key.%s" % key.lower()
        send_key(k, True)
        return "break"

    def on_key_release(event):
        char = event.char
        if char and len(char) == 1:
            k = char
        else:
            key = event.keysym
            k = key if len(key) == 1 else "Key.%s" % key.lower()
        send_key(k, False)
        return "break"

    def focus_for_keys(_=None):
        root.focus_set()

    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Enter>", focus_for_keys)
    canvas.bind("<Button-1>", lambda e: (on_click(e), focus_for_keys()))
    canvas.bind("<Button-2>", lambda e: (on_click(e), focus_for_keys()))
    canvas.bind("<Button-3>", lambda e: (on_click(e), focus_for_keys()))
    canvas.bind("<MouseWheel>", on_scroll)
    canvas.bind("<FocusIn>", focus_for_keys)
    root.bind("<KeyPress>", on_key_press)
    root.bind("<KeyRelease>", on_key_release)
    root.after(100, focus_for_keys)

    def on_closing():
        closed.set()
        try:
            sock.close()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.after(100, update_image)
    root.mainloop()


def run():
    # IP/порт: сначала аргументы, потом config.txt (без диалога)
    server_host = (sys.argv[1].strip() if len(sys.argv) > 1 else "") or ""
    port = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if not server_host or port is None:
        cfg = _load_client_config()
        server_host = server_host or (cfg.get("server_host") or "").strip()
        port = port if port is not None else cfg.get("server_port") or DEFAULT_PORT
    if not server_host:
        print("Укажите IP сервера: в services/remote_desktop/config.txt (server_host=...) или аргументом: python -m ... remote_desktop_client <IP> [порт]", flush=True)
        return
    run_client_gui(server_host, port)


if __name__ == "__main__":
    run()

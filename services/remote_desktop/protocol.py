"""
Общий протокол удалённого стола: форматы сообщений и константы.
Связь: ПК (host) <-> сервер <-> ПК (client). Все сообщения через сервер.
"""
import json
import struct

# Заголовок: 4 байта длина (big-endian), 1 байт тип (0=JSON, 1=binary frame)
HEADER_SIZE = 5
LEN_FMT = ">I"  # unsigned int, 4 bytes
TYPE_JSON = 0
TYPE_FRAME = 1


def encode_message(msg_type: int, payload: bytes) -> bytes:
    """Кодирует сообщение: 4 байта длина payload, 1 байт тип, затем payload."""
    length = len(payload)
    return struct.pack(LEN_FMT, length) + bytes([msg_type]) + payload


def encode_json(obj: dict) -> bytes:
    return encode_message(TYPE_JSON, json.dumps(obj).encode("utf-8"))


def encode_frame(frame_bytes: bytes) -> bytes:
    return encode_message(TYPE_FRAME, frame_bytes)


def read_header(reader) -> tuple:
    """
    Читает заголовок (5 байт). reader должен иметь read(n) или быть asyncio.StreamReader.
    Returns: (length, msg_type) или None при EOF.
    """
    data = _read_exact(reader, HEADER_SIZE)
    if not data or len(data) < HEADER_SIZE:
        return None
    length, = struct.unpack(LEN_FMT, data[:4])
    msg_type = data[4]
    return (length, msg_type)


def read_payload(reader, length: int) -> bytes:
    return _read_exact(reader, length)


def _read_exact(reader, n: int) -> bytes:
    """Синхронное чтение ровно n байт."""
    buf = b""
    while len(buf) < n:
        chunk = reader.read(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


async def read_header_async(reader, n: int = HEADER_SIZE) -> tuple | None:
    """Асинхронно читает заголовок."""
    data = await _read_exact_async(reader, HEADER_SIZE)
    if not data or len(data) < HEADER_SIZE:
        return None
    length, = struct.unpack(LEN_FMT, data[:4])
    msg_type = data[4]
    return (length, msg_type)


async def read_payload_async(reader, length: int) -> bytes:
    return await _read_exact_async(reader, length)


async def _read_exact_async(reader, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


async def read_message(reader):
    """
    Асинхронно читает одно сообщение (заголовок + payload).
    Returns: (payload, msg_type) — payload это dict для TYPE_JSON или bytes для TYPE_FRAME; при EOF (None, None).
    """
    header = await read_header_async(reader)
    if header is None:
        return None, None
    length, msg_type = header
    payload = await read_payload_async(reader, length)
    if len(payload) < length:
        return None, None
    if msg_type == TYPE_JSON:
        try:
            import json
            return json.loads(payload.decode("utf-8")), TYPE_JSON
        except Exception:
            return None, None
    return payload, TYPE_FRAME


# Типы JSON-сообщений
MSG_HOST_REGISTER = "host_register"
MSG_HOST_LIST = "host_list"
MSG_HOST_SELECT = "host_select"
MSG_MOUSE = "mouse"
MSG_KEY = "key"
MSG_FRAME = "frame"
MSG_OK = "ok"
MSG_ERROR = "error"
MSG_PING = "ping"
MSG_PONG = "pong"
MSG_WAKE_REQUEST = "wake_request"  # клиент просит разбудить хост (WoL и т.д.)

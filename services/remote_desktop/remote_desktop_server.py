"""
Сервер удалённого стола. Запуск ТОЛЬКО ВРУЧНУЮ.
Порт 9009. Реле между хостами (ПК под управлением) и клиентами (управляющие ПК).

Запуск: python -m services.remote_desktop.remote_desktop_server
или: cd services/remote_desktop && python remote_desktop_server.py
"""
import asyncio
import json
import sys
from pathlib import Path

# Корень проекта в path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.remote_desktop.protocol import (
    HEADER_SIZE,
    TYPE_JSON,
    TYPE_FRAME,
    encode_message,
    read_header_async,
    read_payload_async,
    MSG_HOST_REGISTER,
    MSG_HOST_LIST,
    MSG_HOST_SELECT,
    MSG_OK,
    MSG_ERROR,
    MSG_WAKE_REQUEST,
)

DEFAULT_PORT = 9009
HOSTS = {}  # host_id -> {name, writer, addr, mac, wake_password}
OFFLINE_HOSTS = {}  # host_id -> {name, mac, wake_password} для WoL после отключения
CLIENT_TO_HOST = {}  # client_writer -> host_id
HOST_TO_CLIENTS = {}  # host_id -> set(client_writer)


def send_wol(mac_str: str, _wake_password: str = ""):
    """Отправка Wake-on-LAN magic packet. mac_str: 'AA:BB:CC:DD:EE:FF' или без двоеточий."""
    if not mac_str or len(mac_str.replace(":", "").replace("-", "")) != 12:
        return False
    try:
        mac_hex = mac_str.replace(":", "").replace("-", "")
        mac_bytes = bytes.fromhex(mac_hex)
        if len(mac_bytes) != 6:
            return False
        packet = b"\xff" * 6 + mac_bytes * 16
        sock = __import__("socket").socket(__import__("socket").AF_INET, __import__("socket").SOCK_DGRAM)
        sock.setsockopt(__import__("socket").SOL_SOCKET, __import__("socket").SO_BROADCAST, 1)
        sock.sendto(packet, ("<broadcast>", 9))
        sock.close()
        return True
    except Exception:
        return False


def send_json(writer: asyncio.StreamWriter, obj: dict):
    data = encode_message(TYPE_JSON, json.dumps(obj).encode("utf-8"))
    writer.write(data)


def send_frame(writer: asyncio.StreamWriter, frame_bytes: bytes):
    data = encode_message(TYPE_FRAME, frame_bytes)
    writer.write(data)


async def read_message(reader: asyncio.StreamReader):
    header = await read_header_async(reader)
    if header is None:
        return None, None
    length, msg_type = header
    payload = await read_payload_async(reader, length)
    if len(payload) < length:
        return None, None
    if msg_type == TYPE_JSON:
        try:
            return json.loads(payload.decode("utf-8")), TYPE_JSON
        except Exception:
            return None, None
    return payload, TYPE_FRAME


async def handle_host(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, addr, first_msg=None):
    host_id = None
    try:
        msg = first_msg
        if msg is None:
            msg, _ = await read_message(reader)
        if not msg or msg.get("type") != MSG_HOST_REGISTER:
            send_json(writer, {"type": MSG_ERROR, "message": "Expected host_register"})
            return
        name = msg.get("name", "unknown")
        mac = msg.get("mac", "")
        wake_password = msg.get("wake_password", "")
        host_id = msg.get("host_id") or f"{addr[0]}:{addr[1]}_{id(writer)}"
        HOSTS[host_id] = {
            "name": name,
            "writer": writer,
            "addr": addr,
            "mac": mac,
            "wake_password": wake_password,
        }
        HOST_TO_CLIENTS[host_id] = set()
        send_json(writer, {"type": MSG_OK, "host_id": host_id})
        print(f"[RD Server] Host registered: {name} ({host_id})", flush=True)
        while True:
            msg_or_frame, msg_type = await read_message(reader)
            if msg_or_frame is None:
                break
            if msg_type == TYPE_FRAME:
                for client in HOST_TO_CLIENTS.get(host_id, set()):
                    try:
                        send_frame(client, msg_or_frame)
                        await client.drain()
                    except Exception:
                        pass
            # остальные JSON от хоста (ping/pong) можно игнорировать или пробрасывать
        return
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    except Exception as e:
        print(f"[RD Server] Host error: {e}", flush=True)
    finally:
        if host_id and host_id in HOSTS:
            info = HOSTS[host_id]
            if info.get("mac"):
                OFFLINE_HOSTS[host_id] = {
                    "name": info.get("name", ""),
                    "mac": info["mac"],
                    "wake_password": info.get("wake_password", ""),
                }
            for client in HOST_TO_CLIENTS.get(host_id, set()):
                try:
                    client.close()
                    await client.wait_closed()
                except Exception:
                    pass
            HOST_TO_CLIENTS.pop(host_id, None)
            HOSTS.pop(host_id, None)
            print(f"[RD Server] Host gone: {host_id}", flush=True)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, addr):
    host_id = None
    try:
        msg, _ = await read_message(reader)
        if not msg:
            return
        t = msg.get("type")
        if t == MSG_HOST_LIST:
            list_ = [{"host_id": hid, "name": h["name"]} for hid, h in HOSTS.items()]
            send_json(writer, {"type": "hosts", "hosts": list_})
            writer.close()
            await writer.wait_closed()
            return
        if t == MSG_HOST_SELECT:
            host_id = msg.get("host_id")
            if not host_id or host_id not in HOSTS:
                send_json(writer, {"type": MSG_ERROR, "message": "Host not found"})
                return
            host_info = HOSTS[host_id]
            host_writer = host_info["writer"]
            CLIENT_TO_HOST[writer] = host_id
            HOST_TO_CLIENTS.setdefault(host_id, set()).add(writer)
            send_json(writer, {"type": MSG_OK, "host_id": host_id, "name": host_info["name"]})
            # Реле: от клиента -> хост (JSON: mouse/key)
            async def relay_client_to_host():
                try:
                    while True:
                        msg_or_frame, msg_type = await read_message(reader)
                        if msg_or_frame is None:
                            break
                        try:
                            if msg_type == TYPE_JSON:
                                send_json(host_writer, msg_or_frame)
                            else:
                                send_frame(host_writer, msg_or_frame)
                            await host_writer.drain()
                        except Exception:
                            break
                except Exception:
                    pass
            asyncio.create_task(relay_client_to_host())
            return
        if t == MSG_WAKE_REQUEST:
            host_id = msg.get("host_id")
            if host_id and host_id in HOSTS:
                send_json(writer, {"type": MSG_ERROR, "message": "Host already online"})
            elif host_id and host_id in OFFLINE_HOSTS:
                off = OFFLINE_HOSTS[host_id]
                sent = send_wol(off.get("mac", ""), off.get("wake_password", ""))
                send_json(writer, {"type": MSG_OK, "message": "wake_sent" if sent else "wake_failed"})
            else:
                send_json(writer, {"type": MSG_ERROR, "message": "Host not found or no MAC"})
            writer.close()
            await writer.wait_closed()
            return
        send_json(writer, {"type": MSG_ERROR, "message": "Unknown request"})
        return
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
        pass
    except Exception as e:
        print(f"[RD Server] Client error: {e}", flush=True)
    finally:
        if writer in CLIENT_TO_HOST:
            host_id = CLIENT_TO_HOST.pop(writer, None)
            if host_id and host_id in HOST_TO_CLIENTS:
                HOST_TO_CLIENTS[host_id].discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def accept_loop(port: int):
    async def handle(reader, writer):
        addr = writer.get_extra_info("peername", ("?", "?"))
        first_msg = await read_message(reader)
        if first_msg[0] is None:
            writer.close()
            await writer.wait_closed()
            return
        msg, _ = first_msg
        if msg.get("type") == MSG_HOST_REGISTER:
            await handle_host(reader, writer, addr, first_msg=msg)
        else:
            # Клиент: list или select. Мы уже прочитали первое сообщение — передаём его в handle_client
            await handle_client_first_msg(reader, writer, addr, msg)
        return

    async def handle_client_first_msg(reader, writer, addr, first_msg):
        host_id = None
        try:
            t = first_msg.get("type")
            if t == MSG_WAKE_REQUEST:
                hid = first_msg.get("host_id")
                if hid and hid in HOSTS:
                    send_json(writer, {"type": MSG_ERROR, "message": "Host already online"})
                elif hid and hid in OFFLINE_HOSTS:
                    off = OFFLINE_HOSTS[hid]
                    sent = send_wol(off.get("mac", ""), off.get("wake_password", ""))
                    send_json(writer, {"type": MSG_OK, "message": "wake_sent" if sent else "wake_failed"})
                else:
                    send_json(writer, {"type": MSG_ERROR, "message": "Host not found or no MAC"})
                writer.close()
                await writer.wait_closed()
                return
            if t == MSG_HOST_LIST:
                list_ = [{"host_id": hid, "name": h["name"]} for hid, h in HOSTS.items()]
                send_json(writer, {"type": "hosts", "hosts": list_})
                writer.close()
                await writer.wait_closed()
                return
            if t == MSG_HOST_SELECT:
                host_id = first_msg.get("host_id")
                if not host_id or host_id not in HOSTS:
                    send_json(writer, {"type": MSG_ERROR, "message": "Host not found"})
                    return
                host_info = HOSTS[host_id]
                host_writer = host_info["writer"]
                CLIENT_TO_HOST[writer] = host_id
                HOST_TO_CLIENTS.setdefault(host_id, set()).add(writer)
                send_json(writer, {"type": MSG_OK, "host_id": host_id, "name": host_info["name"]})
                await writer.drain()
                while True:
                    msg_or_frame, msg_type = await read_message(reader)
                    if msg_or_frame is None:
                        break
                    try:
                        if msg_type == TYPE_JSON:
                            send_json(host_writer, msg_or_frame)
                        else:
                            send_frame(host_writer, msg_or_frame)
                        await host_writer.drain()
                    except Exception:
                        break
                return
            send_json(writer, {"type": MSG_ERROR, "message": "Unknown request"})
        except Exception as e:
            print(f"[RD Server] Client error: {e}", flush=True)
        finally:
            if writer in CLIENT_TO_HOST:
                host_id = CLIENT_TO_HOST.pop(writer, None)
                if host_id and host_id in HOST_TO_CLIENTS:
                    HOST_TO_CLIENTS[host_id].discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle, "0.0.0.0", port)
    print(f"[RD Server] Listening on 0.0.0.0:{port}", flush=True)
    async with server:
        await server.serve_forever()


def run(port: int = DEFAULT_PORT):
    asyncio.run(accept_loop(port))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    run(port)

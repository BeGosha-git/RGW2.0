"""
WebSocket PTY terminal service.

Each WebSocket connection spawns a dedicated /bin/bash inside a PTY.
The PTY master fd is bridged bidirectionally to the WebSocket:
  - browser → WS → write(master_fd)
  - read(master_fd) → WS → browser

Special JSON messages from the browser:
  {"type": "resize", "cols": <int>, "rows": <int>}  — resize terminal window
"""
import asyncio
import fcntl
import json
import os
import pty
import struct
import subprocess
import sys
import termios
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import services_manager
import status

_DEFAULT_PORT = 8765
_ws_port = _DEFAULT_PORT


def _check_port_available(check_port: int) -> bool:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        result = sock.connect_ex(('127.0.0.1', int(check_port)))
        sock.close()
        return result != 0
    except Exception:
        sock.close()
        return False

# ── helpers ────────────────────────────────────────────────────────────────────

def _set_winsize(fd: int, cols: int, rows: int) -> None:
    """Set PTY window size via ioctl."""
    fcntl.ioctl(fd, termios.TIOCSWINSZ,
                struct.pack('HHHH', rows, cols, 0, 0))


def _build_env() -> dict:
    """Build a sane environment for the child shell."""
    env = os.environ.copy()
    env.setdefault('TERM', 'xterm-256color')
    env.setdefault('COLORTERM', 'truecolor')
    env.setdefault('LANG', 'en_US.UTF-8')
    env.setdefault('HOME', os.path.expanduser('~'))
    env.setdefault('PATH', '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    # Start shell in project root
    env['PWD'] = str(ROOT)
    return env


# ── WebSocket handler ──────────────────────────────────────────────────────────

async def _terminal_handler(websocket):
    """Handle one WebSocket connection: one PTY session."""
    master_fd, slave_fd = os.openpty()
    _set_winsize(slave_fd, cols=220, rows=50)

    env = _build_env()
    try:
        proc = subprocess.Popen(
            ['/bin/bash', '--login'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            cwd=str(ROOT),
            env=env,
            preexec_fn=os.setsid,
        )
    except Exception as e:
        await websocket.send(f'\r\n[Terminal] Failed to start shell: {e}\r\n'.encode())
        os.close(master_fd)
        os.close(slave_fd)
        return

    os.close(slave_fd)  # parent does not need slave end
    loop = asyncio.get_event_loop()

    # ── PTY → WebSocket (reader task) ──────────────────────────────────────────
    async def pty_to_ws():
        try:
            while True:
                data = await loop.run_in_executor(None, _read_pty, master_fd)
                if data is None:
                    break
                await websocket.send(data)
        except Exception:
            pass

    def _read_pty(fd: int):
        try:
            return os.read(fd, 4096)
        except OSError:
            return None

    reader_task = asyncio.ensure_future(pty_to_ws())

    # ── WebSocket → PTY ────────────────────────────────────────────────────────
    try:
        async for message in websocket:
            if proc.poll() is not None:
                break
            if isinstance(message, str):
                try:
                    msg = json.loads(message)
                    if msg.get('type') == 'resize':
                        cols = int(msg.get('cols', 80))
                        rows = int(msg.get('rows', 24))
                        _set_winsize(master_fd, cols, rows)
                        continue
                except (json.JSONDecodeError, ValueError):
                    pass
                data = message.encode('utf-8', errors='replace')
            else:
                data = message
            try:
                os.write(master_fd, data)
            except OSError:
                break
    except Exception:
        pass
    finally:
        reader_task.cancel()
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# ── Service loop ───────────────────────────────────────────────────────────────

def get_ws_port() -> int:
    return _ws_port


def run_service_loop():
    global _ws_port
    service_name = 'terminal'

    try:
        manager = services_manager.get_services_manager()
        params = manager.get_service_parameters(service_name)
        _ws_port = int(params.get('port', _DEFAULT_PORT))
    except Exception:
        _ws_port = _DEFAULT_PORT

    # If port is busy, pick a fallback and persist it.
    if not _check_port_available(_ws_port):
        for try_port in (8765, 8766, 8767, 8768, 8775, 8776):
            if _check_port_available(try_port):
                _ws_port = int(try_port)
                try:
                    manager = services_manager.get_services_manager()
                    manager.update_service_parameter(service_name, 'port', _ws_port)
                except Exception:
                    pass
                break

    status.register_service_data(service_name, {
        'status': 'running',
        'port': _ws_port,
    })
    print(f'[Terminal] WebSocket PTY server starting on port {_ws_port}', flush=True)

    async def _serve():
        try:
            import websockets
        except ImportError:
            print('[Terminal] ERROR: websockets library not installed. '
                  'Run: pip install websockets>=11', flush=True)
            return

        async with websockets.serve(
            _terminal_handler,
            '0.0.0.0',
            _ws_port,
            ping_interval=20,
            ping_timeout=30,
            max_size=2 ** 20,
        ):
            print(f'[Terminal] Listening on ws://0.0.0.0:{_ws_port}', flush=True)
            status.register_service_data(service_name, {
                'status': 'running',
                'port': _ws_port,
            })
            await asyncio.Future()  # run forever

    # Run the asyncio event loop in this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_serve())
    except Exception as e:
        print(f'[Terminal] Server stopped: {e}', flush=True)
    finally:
        status.unregister_service_data(service_name)
        loop.close()


# Alias expected by run.py service loader
run = run_service_loop

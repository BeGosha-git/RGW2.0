"""
Сервис воспроизведения звука на роботе Unitree G1.

Архитектура повторяет принятую в проекте схему для G1-модулей (arm actions, loco):
- Вся работа с нативным Unitree SDK / CycloneDDS выполняется в отдельном subprocess
  (через `api/g1_sound_cli.py`), чтобы сбой нативной DDS-библиотеки не ронял
  основной процесс rgw2.
- Сам сервис (этот модуль) отвечает за подготовку аудио (WAV / тон / TTS),
  валидацию данных и регистрацию статуса в services_manager / status.

Звук отправляется на робота через DDS-топик `rt/audio_data` с типом `AudioData_`
(IDL содержит поля `time_frame` (uint64) и `data` (sequence<uint8>)). Данные —
сырые 16-битные знаковые PCM младшим байтом вперёд (little-endian).
"""
from __future__ import annotations

import os
import sys
import time
import wave
import json
import math
import struct
import base64
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

# Добавляем корневую директорию в путь для импорта модулей проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import services_manager
import status

SERVICE_NAME = "g1_sound"

# Параметры по умолчанию для PCM (совместимы с G1 audio-модулем).
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2  # bytes (16-bit PCM)

# Максимальный размер аудио-чанка при отправке по DDS (ограничение встроенного
# буфера audio-модуля). Отрисовка дорожек большего размера выполняется порциями.
AUDIO_CHUNK_BYTES = 32 * 1024

# Резервный каталог для аудиофайлов, поставляемых/загружаемых через API.
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "sounds"

# Доступные сгенерированные тоны (частота Гц, длительность мс).
_AVAILABLE_TONES: Dict[str, Dict[str, Any]] = {
    "beep": {"freq": 880, "duration_ms": 200},
    "success": {"freq": 1320, "duration_ms": 300},
    "error": {"freq": 220, "duration_ms": 400},
    "ding": {"freq": 1046, "duration_ms": 250},
    "attention": {"freq": 1568, "duration_ms": 350},
    "alert": {"freq": 440, "duration_ms": 500},
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def make_tone_pcm(
    freq: float = 880.0,
    duration_ms: int = 300,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = 0.4,
) -> bytes:
    """
    Генерирует 16-бит знаковый mono PCM (little-endian) для синусоидального тона
    с плавными фронтами (без щелчков в начале/конце).

    Args:
        freq: Частота тона, Гц.
        duration_ms: Длительность, мс.
        sample_rate: Частота дискретизации, Гц.
        amplitude: Амплитуда сигнала (0..1).

    Returns:
        bytes: PCM-данные.
    """
    n = int(sample_rate * duration_ms / 1000.0)
    if n <= 0:
        return b""
    amplitude = max(0.0, min(1.0, amplitude))
    ramp = max(1, int(sample_rate * 0.02))  # 20 мс плавного нарастания/спада
    buf = bytearray()
    for i in range(n):
        t = i / float(sample_rate)
        env = 1.0
        if i < ramp:
            env = i / float(ramp)
        elif i > n - ramp:
            env = max(0.0, (n - i) / float(ramp))
        sample = amplitude * env * math.sin(2.0 * math.pi * freq * t)
        buf += struct.pack("<h", int(max(-1.0, min(1.0, sample)) * 32767))
    return bytes(buf)


def wav_to_pcm(
    wav_bytes: bytes,
    target_sample_rate: int = DEFAULT_SAMPLE_RATE,
    target_channels: int = DEFAULT_CHANNELS,
) -> Dict[str, Any]:
    """
    Читает WAV-файл (из bytes) и преобразует его в моно 16-бит PCM
    с заданной частотой дискретизации (простая downmix/resample).

    Если файл уже 16-бит mono и совпадает по частоте — возвращается как есть.

    Args:
        wav_bytes: Содержимое WAV-файла.
        target_sample_rate: Целевая частота дискретизации.
        target_channels: Целевое число каналов (1).

    Returns:
        Словарь с ключами: success, pcm (bytes), sample_rate, channels, duration_ms.
    """
    try:
        import io

        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            nchannels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            raw = w.readframes(nframes)
    except Exception as e:
        return {"success": False, "message": f"Некорректный WAV-файл: {e}"}

    if sampwidth != 2:
        return {
            "success": False,
            "message": f"Поддерживается только 16-бит PCM, получено {sampwidth * 8} бит.",
        }

    # Распаковываем в список значений
    samples = list(struct.iter_unpack("<h", raw))
    values = [s[0] for s in samples]
    n = len(values)

    # Downmix до 1 канала (усреднение).
    if nchannels > 1:
        mixed = []
        for i in range(0, n - nchannels + 1, nchannels):
            ch = values[i : i + nchannels]
            mixed.append(round(sum(ch) / float(nchannels)))
        values = mixed
        n = len(values)

    # Resample до целевой частоты.
    if framerate != target_sample_rate and n > 0:
        ratio = float(framerate) / float(target_sample_rate)
        target_n = int(n / ratio)
        resampled = []
        for i in range(target_n):
            src = int(i * ratio)
            src = min(src, n - 1)
            resampled.append(values[src])
        values = resampled

    # Упаковываем обратно в 16-бит little-endian.
    out = bytearray()
    for v in values:
        out += struct.pack("<h", max(-32768, min(32767, v)))

    duration_ms = int(len(values) / float(target_sample_rate) * 1000.0)

    return {
        "success": True,
        "pcm": bytes(out),
        "sample_rate": target_sample_rate,
        "channels": target_channels,
        "duration_ms": duration_ms,
        "source": {"sample_rate": framerate, "channels": nchannels},
    }


def _tts_pcm(text: str, voice: Optional[str] = None) -> Optional[bytes]:
    """
    Пытается синтезировать речь через espeak-ng/base (если установлен).
    Возвращает PCM (16-bit mono) или None, если TTS недоступен.
    """
    for name, args in (
        ("espeak-ng", ["-q", "-w", "-"]),
        ("espeak", ["-q", "-w", "-"]),
    ):
        exe = None
        for base in ("/usr/bin", "/usr/local/bin", "/bin"):
            p = Path(base) / name
            if p.exists():
                exe = str(p)
                break
        if not exe:
            continue
        try:
            proc = subprocess.run(
                [exe] + args + ["-s", "150", text],
                capture_output=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except Exception:
            continue
    return None


class G1SoundService:
    """
    Сервис воспроизведения звука на Unitree G1.

    Лениво инициализирует DDS-канал и умеет:
      - воспроизводить WAV-файлы (из data/sounds или переданные raw PCM);
      - генерировать тоны-подсказки;
      - синтезировать речь (TTS) при наличии espeak;
      - проигрывать звук в фоне через отдельный процесс.
    """

    _instance: Optional["G1SoundService"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._initialized = False
        self._last_error: Optional[str] = None
        self._network_interface: str = "eth0"
        self._domain_id: int = 0
        self._playing = False
        self._last_play: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> "G1SoundService":
        """Возвращает синглтон сервиса."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # ------------------------------------------------------------------ конфиг
    def _load_network_config(self) -> None:
        """Загружает сетевую конфигурацию из services.json (приоритет: g1_sound, затем unitree_motor_control)."""
        try:
            manager = services_manager.get_services_manager()
            params = manager.get_service_parameters(SERVICE_NAME)
            self._network_interface = str(params.get("network", "") or "")
            self._domain_id = int(params.get("id", -1) or -1)
            # Если у g1_sound явно не заданы, берём из unitree_motor_control.
            if not self._network_interface or self._domain_id < 0:
                p = manager.get_service_parameters("unitree_motor_control")
                self._network_interface = str(p.get("network", "eth0") or "eth0") if not self._network_interface else self._network_interface
                self._domain_id = int(p.get("id", 0) or 0) if self._domain_id < 0 else self._domain_id
            if not self._network_interface:
                self._network_interface = "eth0"
        except Exception:
            self._network_interface = "eth0"
            self._domain_id = 0

    # ------------------------------------------------------------- низкий уровень
    def _run_cli(self, args: List[str], timeout: float = 60.0) -> Dict[str, Any]:
        """
        Запускает api/g1_sound_cli.py в subprocess и возвращает JSON-результат.
        """
        cli = PROJECT_ROOT / "api" / "g1_sound_cli.py"
        if not cli.exists():
            return {
                "success": False,
                "message": f"CLI-помощник не найден: {cli}",
            }

        base_args = [
            sys.executable,
            str(cli),
            str(PROJECT_ROOT),
            self._network_interface,
            str(self._domain_id),
        ]

        try:
            proc = subprocess.run(
                base_args + list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(PROJECT_ROOT),
                env=self._cli_env(),
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Таймаут subprocess (g1_sound_cli)"}
        except Exception as e:
            return {"success": False, "message": f"Ошибка запуска subprocess: {e}"}

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        try:
            # CLI печатает одну JSON-строку.
            line = stdout.strip().splitlines()[-1] if stdout.strip() else "{}"
            result = json.loads(line)
            if isinstance(result, dict):
                result.setdefault("stderr", stderr[-500:] if stderr else "")
                return result
        except Exception:
            pass

        return {
            "success": False,
            "message": (
                f"subprocess вернул не JSON (rc={proc.returncode}). "
                f"stdout={stdout[-300:]!r} stderr={stderr[-300:]!r}"
            ),
        }

    def _cli_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        # Чтобы дочерний процесс видел venv SDK.
        for k in ("VIRTUAL_ENV", "LD_LIBRARY_PATH", "CYCLONEDDS_HOME"):
            if k in os.environ:
                env[k] = os.environ[k]
        return env

    # ------------------------------------------------------------------ статус
    def _sync_status(self, extra: Optional[Dict[str, Any]] = None) -> None:
        data = {
            "status": "running" if self._initialized else "not_initialized",
            "network_interface": self._network_interface,
            "domain_id": self._domain_id,
            "playing": self._playing,
            "last_play": self._last_play,
            "updated_at": time.time(),
        }
        if self._last_error:
            data["last_error"] = self._last_error
        if extra:
            data.update(extra)
        status.register_service_data(SERVICE_NAME, data)

    def status_info(self) -> Dict[str, Any]:
        """Возвращает текущий статус сервиса для API."""
        return {
            "success": True,
            "service": SERVICE_NAME,
            "initialized": self._initialized,
            "playing": self._playing,
            "network_interface": self._network_interface,
            "domain_id": self._domain_id,
            "last_error": self._last_error,
            "last_play": self._last_play,
        }

    # ------------------------------------------------------------------- звук
    def play_pcm(
        self,
        pcm: bytes,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        label: str = "custom",
        stop_current: bool = True,
    ) -> Dict[str, Any]:
        """
        Воспроизводит PCM-данные на роботе через DDS (в subprocess).
        """
        if not pcm:
            return {"success": False, "message": "Пустые PCM-данные"}

        self._load_network_config()

        data_b64 = base64.b64encode(pcm).decode("ascii")

        payload = {
            "op": "play",
            "b64": data_b64,
            "sample_rate": int(sample_rate),
            "channels": int(channels),
            "label": str(label),
            "stop_current": bool(stop_current),
        }
        result = self._run_cli([json.dumps(payload)])

        with self._lock:
            self._playing = bool(result.get("success"))
            if result.get("success"):
                self._last_play = {
                    "label": label,
                    "duration_ms": result.get("duration_ms"),
                    "sent_bytes": result.get("sent_bytes"),
                    "at": _now_ms(),
                }
                self._last_error = None
            else:
                self._last_error = result.get("message")

        self._sync_status()
        return result

    def play_wav(
        self,
        wav_bytes: bytes,
        *,
        label: str = "wav",
        target_sample_rate: int = DEFAULT_SAMPLE_RATE,
        stop_current: bool = True,
    ) -> Dict[str, Any]:
        """
        Воспроизводит WAV-файл на роботе (конвертирует в 16-бит моно PCM).
        """
        conv = wav_to_pcm(wav_bytes, target_sample_rate=target_sample_rate)
        if not conv.get("success"):
            return conv
        return self.play_pcm(
            conv["pcm"],
            sample_rate=conv["sample_rate"],
            channels=conv["channels"],
            label=label,
            stop_current=stop_current,
        )

    def play_tone(self, name: str, stop_current: bool = True) -> Dict[str, Any]:
        """
        Воспроизводит короткий тон-подсказку по имени.
        """
        tone = _AVAILABLE_TONES.get(str(name).strip().lower())
        if tone is None:
            return {
                "success": False,
                "message": f"Неизвестный тон: {name}. Доступно: {sorted(_AVAILABLE_TONES)}",
            }
        pcm = make_tone_pcm(freq=tone["freq"], duration_ms=tone["duration_ms"])
        return self.play_pcm(
            pcm,
            sample_rate=DEFAULT_SAMPLE_RATE,
            channels=DEFAULT_CHANNELS,
            label=f"tone:{name}",
            stop_current=stop_current,
        )

    def play_file(self, filename: str, stop_current: bool = True) -> Dict[str, Any]:
        """
        Воспроизводит WAV-файл из каталога data/sounds по имени файла.
        """
        if not filename:
            return {"success": False, "message": "filename required"}

        DEFAULT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        # Безопасный путь (без выхода за пределы каталога).
        safe_name = Path(filename).name
        path = (DEFAULT_AUDIO_DIR / safe_name).resolve()
        try:
            path.relative_to(DEFAULT_AUDIO_DIR.resolve())
        except Exception:
            return {"success": False, "message": "Недопустимое имя файла"}

        if not path.exists() or not path.is_file():
            return {
                "success": False,
                "message": f"Файл не найден: {safe_name}",
                "dir": str(DEFAULT_AUDIO_DIR),
                "files": self.list_files()["files"],
            }

        try:
            data = path.read_bytes()
        except Exception as e:
            return {"success": False, "message": f"Ошибка чтения файла: {e}"}

        return self.play_wav(data, label=f"file:{safe_name}", stop_current=stop_current)

    def play_speak(self, text: str, stop_current: bool = True) -> Dict[str, Any]:
        """
        Синтезирует речь (TTS) и воспроизводит её.
        """
        text = str(text or "").strip()
        if not text:
            return {"success": False, "message": "text required"}

        wav = _tts_pcm(text)
        if not wav:
            return {
                "success": False,
                "message": "TTS недоступен (требуется espeak-ng или espeak в системе)",
            }
        return self.play_wav(wav, label="tts", stop_current=stop_current)

    def stop(self) -> Dict[str, Any]:
        """Останавливает текущее воспроизведение (шлёт пустой/тихий чанк)."""
        self._load_network_config()
        payload = {"op": "stop"}
        result = self._run_cli([json.dumps(payload)])
        with self._lock:
            self._playing = False
            if result.get("success"):
                self._last_error = None
        self._sync_status()
        return result

    def list_files(self) -> Dict[str, Any]:
        """Список доступных WAV-файлов в data/sounds."""
        DEFAULT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for p in sorted(DEFAULT_AUDIO_DIR.glob("*.wav")):
            files.append({"name": p.name, "size": p.stat().st_size})
        return {"success": True, "dir": str(DEFAULT_AUDIO_DIR), "files": files}

    def list_tones(self) -> Dict[str, Any]:
        """Список доступных тонов."""
        return {
            "success": True,
            "tones": [
                {"name": name, **({k: v for k, v in meta.items()})}
                for name, meta in _AVAILABLE_TONES.items()
            ],
        }


def get_g1_sound_service() -> G1SoundService:
    """Возвращает синглтон сервиса (для subprocess-вызова)."""
    return G1SoundService.get_instance()


# ----------------------------------------------------------------- бэкграунд-поток
def run_service(interval: int = 5):
    """
    Точка входа для фонового сервиса (используется run.py / main.py).

    Регистрирует данные в status.py и раз в интервал синхронизирует статус.
    Реальная работа (play/stop) вызывается по REST API — цикл здесь только
    поддерживает сервис активным и отвечающим.
    """
    instance = G1SoundService.get_instance()
    instance._load_network_config()

    print(f"Service {SERVICE_NAME} started", flush=True)
    status.register_service_data(
        SERVICE_NAME,
        {
            "status": "running",
            "started_at": time.time(),
            "initialized": False,
        },
    )

    try:
        manager = services_manager.get_services_manager()
    except Exception:
        manager = None

    while True:
        try:
            if manager is not None:
                service_info = manager.get_service(SERVICE_NAME)
                service_status = service_info.get("status", "ON")
                if service_status == "OFF":
                    print(f"Service {SERVICE_NAME} is OFF. Stopping...", flush=True)
                    status.unregister_service_data(SERVICE_NAME)
                    break
                elif service_status == "SLEEP":
                    time.sleep(interval)
                    continue
            instance._sync_status({"alive": True})
        except KeyboardInterrupt:
            print(f"\nService {SERVICE_NAME} stopped by user", flush=True)
            status.unregister_service_data(SERVICE_NAME)
            break
        except Exception as e:
            print(f"Error in service {SERVICE_NAME}: {e}", flush=True)
            instance._last_error = str(e)
        time.sleep(interval)


def run():
    run_service()


def main():
    run()


if __name__ == "__main__":
    run()

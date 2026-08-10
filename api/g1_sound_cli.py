#!/usr/bin/env python3
"""
CLI-помощник для воспроизведения звука на Unitree G1 через DDS.

Запускается в отдельном subprocess (из services.g1_sound.g1_sound_service),
чтобы нативный CycloneDDS / Unitree SDK не мог уронить основной процесс rgw2.

Usage:
  python3 api/g1_sound_cli.py <PROJECT_ROOT> <net_if> <domain_id> <payload_json>

payload_json (одна JSON-строка):
  {"op": "play", "b64": "<base64 PCM>", "sample_rate": 16000, "channels": 1,
   "label": "...", "stop_current": true}
  {"op": "stop"}

На выходе — одна JSON-строка в stdout.

Звук публикуется в DDS-топик `rt/audio_data` с типом `unitree_go.msg.dds_.AudioData_`.
Поле `data` содержит сырые 16-битные знаковые PCM (little-endian). Поле `time_frame`
— метка времени для синхронизации модуля аудио на роботе.

Параметры (sample_rate / channels) используются только для расчёта длительности
и разделения на чанки; сам модуль аудио на роботе ожидает данные, совместимые с
его внутренним форматом (обычно 16-bit mono). При необходимости отрисовка идёт
небольшими порциями (AUDIO_CHUNK_BYTES) с паузой между ними.
"""

from __future__ import annotations

import base64
import json
import sys
import time


AUDIO_CHUNK_BYTES = 32 * 1024
INTER_CHUNK_DELAY = 0.05  # секунд между чанками, чтобы модуль успевал воспроизводить


def _fail(message: str, **extra):
    out = {"success": False, "message": message}
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    raise SystemExit(0)


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        _fail("usage: g1_sound_cli.py <PROJECT_ROOT> <net_if> <domain_id> <payload_json>")

    project_root = argv[1]
    net_if = argv[2]
    try:
        domain_id = int(argv[3])
    except Exception:
        _fail("invalid domain_id", domain_id=argv[3])
    try:
        payload = json.loads(argv[4] or "{}")
    except Exception:
        _fail("invalid payload_json")

    op = str(payload.get("op") or "").strip().lower()

    # Добавляем пути для импорта vendored SDK.
    sys.path.insert(0, project_root)
    sys.path.insert(0, f"{project_root.rstrip('/')}/services/unitree_motor_control")

    try:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher
        from unitree_sdk2py.idl.unitree_go.msg.dds_ import AudioData_
    except Exception as e:
        _fail(f"Failed to import unitree_sdk2py: {e}")

    sample_rate = int(payload.get("sample_rate", 16000) or 16000)
    channels = int(payload.get("channels", 1) or 1)
    label = str(payload.get("label") or "sound")

    # If no playback is needed (e.g. "stop"), we initialize DDS only for stop.
    pcm = b""
    if op == "play":
        b64 = payload.get("b64") or ""
        try:
            pcm = base64.b64decode(b64)
        except Exception as e:
            _fail(f"Invalid base64 PCM: {e}")
        if not pcm:
            _fail("Empty PCM data")

    try:
        ChannelFactoryInitialize(domain_id, net_if)
    except Exception as e:
        _fail(f"DDS init failed: {e}", network=net_if, domain_id=domain_id)

    publisher = ChannelPublisher("rt/audio_data", AudioData_)
    publisher.Init()

    try:
        if op == "stop":
            # Тихий чанк останавливает/сбрасывает буфер воспроизведения.
            silence = bytes(max(1, int(sample_rate * 0.05)) * 2)  # 50 мс тишины
            sample = AudioData_(time_frame=int(time.time() * 1_000_000), data=list(silence))
            publisher.Write(sample, timeout=5.0)
            print(json.dumps({"success": True, "op": "stop", "label": label}, ensure_ascii=False))
            return 0

        if op == "play":
            duration_ms = int(len(pcm) / float(sample_rate * channels) * 1000.0)
            sent = 0
            # Разбиваем на чанки с паузой между ними.
            chunk_total = max(1, len(pcm) // AUDIO_CHUNK_BYTES + (1 if len(pcm) % AUDIO_CHUNK_BYTES else 0))
            for idx in range(chunk_total):
                chunk = pcm[idx * AUDIO_CHUNK_BYTES : (idx + 1) * AUDIO_CHUNK_BYTES]
                sample = AudioData_(
                    time_frame=int(time.time() * 1_000_000),
                    data=list(chunk),
                )
                if not publisher.Write(sample, timeout=5.0):
                    _fail(
                        "Failed to write audio chunk to rt/audio_data "
                        f"(no matching reader?) chunk={idx + 1}/{chunk_total}",
                        op=op,
                        label=label,
                        sent_bytes=sent,
                        duration_ms=duration_ms,
                    )
                sent += len(chunk)
                if idx < chunk_total - 1 and INTER_CHUNK_DELAY > 0:
                    time.sleep(INTER_CHUNK_DELAY)

            print(
                json.dumps(
                    {
                        "success": True,
                        "op": op,
                        "label": label,
                        "sent_bytes": sent,
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "duration_ms": duration_ms,
                        "chunks": chunk_total,
                        "topic": "rt/audio_data",
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        _fail("unknown op", op=op)
    finally:
        try:
            publisher.Close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

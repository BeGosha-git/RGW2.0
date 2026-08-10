"""
API маршруты для воспроизведения звука на Unitree G1.
"""
from __future__ import annotations

import base64

from flask import Blueprint, jsonify, request

import api.robot as robot_api

bp = Blueprint("sound", __name__)


@bp.route("/api/robot/g1/sound/info", methods=["GET"])
def api_g1_sound_info():
    """Список доступных тонов, файлов и статус звукового модуля G1."""
    return jsonify(robot_api.RobotAPI.get_g1_sound_info()), 200


@bp.route("/api/robot/g1/sound/tones", methods=["GET"])
def api_g1_sound_tones():
    """Список доступных тонов-подсказок."""
    try:
        from services.g1_sound.g1_sound_service import get_g1_sound_service

        result = get_g1_sound_service().list_tones()
        return jsonify(result), (200 if result.get("success") else 500)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/robot/g1/sound/files", methods=["GET"])
def api_g1_sound_files():
    """Список WAV-файлов в data/sounds."""
    try:
        from services.g1_sound.g1_sound_service import get_g1_sound_service

        result = get_g1_sound_service().list_files()
        return jsonify(result), (200 if result.get("success") else 500)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/robot/g1/sound/play/tone", methods=["POST"])
def api_g1_sound_play_tone():
    """Воспроизводит предустановленный тон: {"name": "beep"|"success"|...}"""
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"success": False, "message": "name required"}), 400
    result = robot_api.RobotAPI.play_g1_tone(name)
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/sound/play/file", methods=["POST"])
def api_g1_sound_play_file():
    """Воспроизводит WAV-файл из data/sounds: {"filename": "hello.wav"}"""
    data = request.get_json() or {}
    filename = str(data.get("filename", "")).strip()
    if not filename:
        return jsonify({"success": False, "message": "filename required"}), 400
    result = robot_api.RobotAPI.play_g1_file(filename)
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/sound/play/speak", methods=["POST"])
def api_g1_sound_speak():
    """Синтезирует и воспроизводит речь: {"text": "Привет!"} (требуется espeak)"""
    data = request.get_json() or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"success": False, "message": "text required"}), 400
    result = robot_api.RobotAPI.speak_g1(text)
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/sound/play/pcm", methods=["POST"])
def api_g1_sound_play_pcm():
    """
    Воспроизводит переданный аудио (16-бит PCM или WAV).
    Принимает JSON:
      {"data": "<base64>", "sample_rate": 16000, "channels": 1, "format": "pcm"|"wav"}
    либо multipart/form-data с полем "data" (raw байты WAV/PCM).
    """
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        raw = request.files.get("data")
        if raw is None:
            return jsonify({"success": False, "message": "field 'data' is required (file)"}), 400
        raw_bytes = raw.read()
        fmt = (request.form.get("format") or "wav").strip().lower()
        sample_rate = int(request.form.get("sample_rate", 16000))
    else:
        data = request.get_json() or {}
        b64 = data.get("data") or ""
        try:
            raw_bytes = base64.b64decode(b64)
        except Exception as e:
            return jsonify({"success": False, "message": f"invalid base64 data: {e}"}), 400
        fmt = (data.get("format") or "pcm").strip().lower()
        sample_rate = int(data.get("sample_rate", 16000))

    if not raw_bytes:
        return jsonify({"success": False, "message": "empty data"}), 400

    if fmt in ("wav", "wave"):
        try:
            from services.g1_sound.g1_sound_service import get_g1_sound_service

            result = get_g1_sound_service().play_wav(
                raw_bytes,
                label="upload",
                target_sample_rate=int(sample_rate),
                stop_current=True,
            )
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
    else:
        # Рaw PCM — отправляем через subprocess.
        import base64 as _b64

        result = robot_api.RobotAPI.play_g1_wav_b64(
            _b64.b64encode(raw_bytes).decode("ascii"),
            sample_rate=int(sample_rate),
        )

    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/sound/stop", methods=["POST"])
def api_g1_sound_stop():
    """Останавливает текущее воспроизведение звука."""
    result = robot_api.RobotAPI.stop_g1_sound()
    return jsonify(result), (200 if result.get("success") else 400)


@bp.route("/api/robot/g1/sound/upload", methods=["POST"])
def api_g1_sound_upload():
    """
    Загружает WAV-файл в каталог data/sounds (multipart/form-data).
    Поле "file" — аудиофайл, "filename" (опционально) — имя для сохранения.
    """
    f = request.files.get("file")
    if f is None:
        return jsonify({"success": False, "message": "field 'file' is required"}), 400

    from pathlib import Path
    from api._paths import PROJECT_ROOT

    sounds_dir = PROJECT_ROOT / "data" / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)

    filename = str((request.form.get("filename") or f.filename or "sound.wav")).strip()
    safe_name = Path(filename).name
    if not safe_name.lower().endswith(".wav"):
        safe_name += ".wav"

    dest = (sounds_dir / safe_name).resolve()
    try:
        dest.relative_to(sounds_dir.resolve())
    except Exception:
        return jsonify({"success": False, "message": "invalid filename"}), 400

    try:
        f.save(str(dest))
    except Exception as e:
        return jsonify({"success": False, "message": f"failed to save file: {e}"}), 500

    return jsonify({"success": True, "filename": safe_name, "path": str(dest)}), 200

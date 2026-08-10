"""
Создание каталога data/ и обязательных JSON при первом запуске (если файлов нет).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from utils.path_utils import get_data_dir, get_project_root


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bootstrap_data_files(project_root: Optional[Path] = None) -> None:
    """
    Гарантирует наличие data/ и базовых файлов конфигурации.
    Не перезаписывает существующие файлы (кроме случаев, оговорённых отдельно).
    """
    root = project_root or get_project_root()
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "unitree_model").mkdir(parents=True, exist_ok=True)


    settings_path = data / "settings.json"
    if not settings_path.exists():
        _write_json(
            settings_path,
            {
                "RobotType": "SERVER",
                "RobotID": "0000",
                "RobotGroup": "default",
                "VersionPriority": "STABLE",
            },
        )

    sudo_path = data / "sudo_passwords.json"
    if not sudo_path.exists():
        sudo_path.write_text("{}\n", encoding="utf-8")

    try:
        from services.advanced_render.world import ensure_advanced_world_file

        ensure_advanced_world_file(data / "advanced_world.json")
    except Exception:
        pass

    version_path = data / "version.json"
    if not version_path.exists():
        try:
            import update

            old = os.getcwd()
            try:
                os.chdir(str(root))
                update.update_version_file(skip_venv_archive=True)
            finally:
                os.chdir(old)
        except Exception:
            _write_json(
                version_path,
                {"version": "1.00.01", "version_type": "STABLE", "files": []},
            )


def get_data_dir_bootstrap() -> Path:
    """Удобная обёртка: создать data и вернуть путь."""
    bootstrap_data_files()
    return get_data_dir()

"""
Сервис выполнения предустановленных действий рук для Unitree G1.
"""
from __future__ import annotations

import sys
import threading
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

from services.unitree_motor_control.dependencies import setup_cyclonedds_environment

setup_cyclonedds_environment()

SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


def _elf_machine(path: Path) -> Optional[int]:
    try:
        with open(path, "rb") as f:
            hdr = f.read(20)
        if len(hdr) < 20 or hdr[:4] != b"\x7fELF":
            return None
        # e_machine (16-bit) offset 18, little endian for common Linux targets.
        return int.from_bytes(hdr[18:20], byteorder="little", signed=False)
    except Exception:
        return None


def _prepare_cyclonedds_runtime() -> None:
    """
    На aarch64 старый wheel cyclonedds может содержать x86_64 libddsc и падать до fallback.
    В этом случае отключаем wheel-loader и принудительно указываем системный CycloneDDS.
    """
    cyclonedds_home_candidates = [
        Path("/home/unitree/cyclonedds_ws/install/cyclonedds"),
        Path.home() / "cyclonedds_ws" / "install" / "cyclonedds",
    ]
    for candidate in cyclonedds_home_candidates:
        lib_path = candidate / "lib" / "libddsc.so"
        if lib_path.exists():
            os.environ.setdefault("CYCLONEDDS_HOME", str(candidate))
            break

    if "CYCLONEDDS_HOME" in os.environ:
        ddslib = Path(os.environ["CYCLONEDDS_HOME"]) / "lib"
        if ddslib.exists():
            ld = os.environ.get("LD_LIBRARY_PATH", "")
            if str(ddslib) not in ld:
                os.environ["LD_LIBRARY_PATH"] = f"{ddslib}:{ld}" if ld else str(ddslib)

    machine = os.uname().machine.lower()
    if machine in {"aarch64", "arm64"}:
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        lib_py = PROJECT_ROOT / "venv" / "lib" / f"python{py_ver}" / "site-packages"
        wheel_lib = next((lib_py / "cyclonedds.libs").glob("libddsc*.so*"), None)
        if wheel_lib:
            em = _elf_machine(wheel_lib)
            # 62 = x86_64, 183 = aarch64
            if em == 62:
                raise RuntimeError(
                    "CycloneDDS in venv has x86_64 binaries on aarch64 host. "
                    f"Rebuild/recreate venv for this device. Bad file: {wheel_lib}"
                )


def _ensure_local_cyclonedds() -> None:
    """
    Ensure cyclonedds is installed from local wheels (offline-first).
    """
    host_arch = os.uname().machine.lower()
    host_arch = "aarch64" if host_arch in {"aarch64", "arm64"} else host_arch

    def _current_arch() -> str:
        try:
            import cyclonedds as _c
            pkg_dir = Path(_c.__file__).resolve().parent
            so_files = sorted(pkg_dir.glob("_clayer*.so"))
            if not so_files:
                return "unknown"
            em = _elf_machine(so_files[0])
            if em == 183:
                return "aarch64"
            if em == 62:
                return "x86_64"
            return "unknown"
        except Exception:
            return "missing"

    cur = _current_arch()
    if cur != "missing" and (host_arch not in {"aarch64", "x86_64"} or cur in {"unknown", host_arch}):
        return

    local_wheel_dirs = [
        SERVICE_DIR / "offline_packages",
        PROJECT_ROOT / "offline_packages",
    ]
    for wheel_dir in local_wheel_dirs:
        if not wheel_dir.exists():
            continue
        if host_arch == "aarch64":
            wheel = next(wheel_dir.glob("cyclonedds-*-linux_aarch64.whl"), None)
        elif host_arch == "x86_64":
            wheel = next(wheel_dir.glob("cyclonedds-*-linux_x86_64.whl"), None)
        else:
            wheel = next(wheel_dir.glob("cyclonedds-*.whl"), None)
        if not wheel:
            continue

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-index",
            "--find-links",
            str(wheel_dir),
            str(wheel),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return

    raise RuntimeError(
        "cyclonedds is missing/incompatible and no suitable local wheel was found in "
        f"{SERVICE_DIR / 'offline_packages'} or {PROJECT_ROOT / 'offline_packages'}"
    )

_ACTION_MAP: Dict[str, int] = {
    "release arm": 99,
    "two-hand kiss": 11,
    "left kiss": 12,
    "right kiss": 13,
    "hands up": 15,
    "clap": 17,
    "high five": 18,
    "hug": 19,
    "heart": 20,
    "right heart": 21,
    "reject": 22,
    "right hand up": 23,
    "x-ray": 24,
    "face wave": 25,
    "high wave": 26,
    "shake hand": 27,
}

# Логика опций как в официальном примере Unitree (id 0..15).
# duration_ms — примерное время физического выполнения движения (RPC fire-and-forget).
# Агент сценария будет ждать это время после получения ответа SDK, чтобы не запускать
# следующую команду пока робот ещё двигается.
_OPTION_LIST = [
    # (name, option_id, duration_ms)
    ("release arm",    0,  2000),
    ("shake hand",     1,  4000),
    ("high five",      2,  4000),
    ("hug",            3,  5000),
    ("high wave",      4,  4000),
    ("clap",           5,  4000),
    ("face wave",      6,  4000),
    ("left kiss",      7,  4000),
    ("heart",          8,  5000),
    ("right heart",    9,  5000),
    ("hands up",      10,  4000),
    ("x-ray",         11,  5000),
    ("right hand up", 12,  3000),
    ("reject",        13,  4000),
    ("right kiss",    14,  4000),
    ("two-hand kiss", 15,  5000),
]
_OPTION_ID_BY_NAME: Dict[str, int] = {name: idx for name, _, idx in _OPTION_LIST}  # type: ignore[misc]
_OPTION_ID_BY_NAME = {name: opt_id for name, opt_id, _ in _OPTION_LIST}
_DURATION_MS_BY_NAME: Dict[str, int] = {name: dur for name, _, dur in _OPTION_LIST}
# Для этих опций в примере выполняется auto-release через 2 секунды.
_AUTO_RELEASE_OPTION_IDS = {1, 2, 3, 8, 9, 10, 11, 12, 13}
# Нефатальные коды ответа SDK (3104 считается валидным по факту поведения робота).
# 31 = занято/не готово (временное состояние), обрабатываем через retry.
_NON_FATAL_CODES = {0, 3104}
# Коды при которых имеет смысл повтор (SDK временно занят или ещё не готов).
# 31   = SDK занят/не готов
# 3102 = RPC_ERR_CLIENT_SEND (ошибка отправки — может быть временной при инициализации DDS)
_RETRY_CODES = {31, 3102}


class G1ArmActionService:
    """Лениво инициализирует SDK-клиент и выполняет arm actions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client = None
        self._initialized = False
        self._last_error: Optional[str] = None
        self._network_interface: str = "eth0"
        self._domain_id: int = 0

    def init(self, network_interface: str = "eth0", domain_id: int = 0) -> None:
        with self._lock:
            if self._initialized:
                return
            _ensure_local_cyclonedds()
            _prepare_cyclonedds_runtime()
            try:
                from unitree_sdk2py.core.channel import ChannelFactoryInitialize
                from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map
            except Exception as e:
                self._last_error = (
                    f"G1 SDK import error: {e}. "
                    f"Expected local SDK at: {SERVICE_DIR / 'unitree_sdk2py'}"
                )
                raise RuntimeError(self._last_error) from e
            _ACTION_MAP.update(action_map)

            ChannelFactoryInitialize(domain_id, network_interface)
            client = G1ArmActionClient()
            client.SetTimeout(5.0)
            client.Init()

            self._client = client
            self._initialized = True
            self._network_interface = network_interface
            self._domain_id = domain_id
            self._last_error = None

    def ensure_initialized(self, network_interface: str = "eth0", domain_id: int = 0) -> None:
        if not self._initialized:
            self.init(network_interface=network_interface, domain_id=domain_id)

    def execute(self, action_name: str, network_interface: str = "eth0", domain_id: int = 0) -> Dict[str, Any]:
        option_id = _OPTION_ID_BY_NAME.get(action_name)
        action_id = _ACTION_MAP.get(action_name)
        # duration_ms is only used for actions that require auto-release (i.e. "reset motors").
        duration_ms = max(0, int(_DURATION_MS_BY_NAME.get(action_name, 3000)))
        if action_id is None or option_id is None:
            return {
                "success": False,
                "message": f"Unknown G1 action: {action_name}",
                "available_actions": [name for name, _, _ in _OPTION_LIST],
            }

        try:
            self.ensure_initialized(network_interface=network_interface, domain_id=domain_id)
            reset_code: Optional[int] = None
            result_code: Optional[int] = None
            max_retries = 5
            retry_delay = 1.0  # секунды между попытками

            with self._lock:
                if self._client is None:
                    raise RuntimeError("G1 action client is not initialized")
                # Сброс удержания/контекста перед новым жестом (в примере Unitree первым пунктом — release arm).
                release_id = _ACTION_MAP.get("release arm")
                if release_id is not None and action_name != "release arm":
                    for _attempt in range(max_retries):
                        reset_code = self._client.ExecuteAction(release_id)
                        if reset_code in _NON_FATAL_CODES or reset_code not in _RETRY_CODES:
                            break
                        time.sleep(retry_delay)

                for _attempt in range(max_retries):
                    result_code = self._client.ExecuteAction(action_id)
                    if result_code in _NON_FATAL_CODES or result_code not in _RETRY_CODES:
                        break
                    time.sleep(retry_delay)

                if result_code not in _NON_FATAL_CODES:
                    return {
                        "success": False,
                        "message": f"G1 action rejected by SDK (code={result_code}): {action_name}",
                        "action": action_name,
                        "action_id": action_id,
                        "option_id": option_id,
                        "code": result_code,
                        **({"reset_code": reset_code} if reset_code is not None else {}),
                    }
                # Как в g1_arm_action_example.py: после жеста release arm (для перечисленных option_id).
                need_auto_release = (
                    option_id in _AUTO_RELEASE_OPTION_IDS
                    and release_id is not None
                )

            # Если нужен авто-сброс (release arm) — ждём физическое выполнение жеста,
            # иначе не задерживаем сценарий (SDK вызов fire-and-forget).
            if need_auto_release and duration_ms > 0:
                time.sleep(duration_ms / 1000.0)

            if need_auto_release:
                release_code: Optional[int] = None
                with self._lock:
                    if self._client is None:
                        raise RuntimeError("G1 action client is not initialized")
                    release_code = self._client.ExecuteAction(release_id)
                if release_code not in _NON_FATAL_CODES:
                    return {
                        "success": False,
                        "message": (
                            f"G1 action executed but auto-release failed "
                            f"(code={release_code}) after: {action_name}"
                        ),
                        "action": action_name,
                        "action_id": action_id,
                        "option_id": option_id,
                        "code": release_code,
                        # Return duration only when it matters (reset case)
                        "duration_ms": duration_ms if need_auto_release else 0,
                    }

            return {
                "success": True,
                "message": (
                    f"G1 action executed: {action_name}"
                    if result_code == 0
                    else f"G1 action accepted with non-fatal SDK code={result_code}: {action_name}"
                ),
                "action": action_name,
                "action_id": action_id,
                "option_id": option_id,
                "code": result_code,
                # Return duration only when it matters (reset case)
                "duration_ms": duration_ms if need_auto_release else 0,
                **(
                    {"reset_code": reset_code}
                    if reset_code is not None and action_name != "release arm"
                    else {}
                ),
            }
        except Exception as e:
            self._last_error = str(e)
            return {
                "success": False,
                "message": f"Failed to execute G1 action: {e}",
                "action": action_name,
            }

    def status(self) -> Dict[str, Any]:
        return {
            "success": True,
            "initialized": self._initialized,
            "network_interface": self._network_interface,
            "domain_id": self._domain_id,
            "last_error": self._last_error,
            "actions_count": len(_ACTION_MAP),
        }


_service = G1ArmActionService()


def get_g1_arm_action_service() -> G1ArmActionService:
    return _service


def get_g1_actions() -> Dict[str, int]:
    return dict(_ACTION_MAP)

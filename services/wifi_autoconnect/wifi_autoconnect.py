"""
Сервис для автоматического подключения к Wi-Fi сети BeRobots.
Логика совпадает с connect_wifi.sh: Managed mode, nmcli rescan + delete + connect ifname,
при неудаче — wpa_supplicant + dhclient.
"""
import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Добавляем корневую директорию в путь для импорта модулей проекта
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Импортируем services_manager для обнаружения сервиса
import services_manager

# Имя сервиса для регистрации
SERVICE_NAME = "wifi_autoconnect"

def get_service_name() -> str:
    """Возвращает имя сервиса."""
    return SERVICE_NAME

# Параметры Wi-Fi сети (как в connect_wifi.sh)
WIFI_SSID = "BeRobots"
WIFI_PASSWORD = "Unitree0408"
# Интерфейс по умолчанию — wlan0 (как в скрипте); иначе RGW2_WIFI_IFACE=wlp2s0
WIFI_IFACE = os.environ.get("RGW2_WIFI_IFACE", "wlan0")


def _nmcli_env():
    env = os.environ.copy()
    env.setdefault("LANG", "C")
    env.setdefault("LC_ALL", "C")
    return env


def _with_sudo(argv):
    """Те же команды, что в .sh с sudo; под root sudo не добавляем."""
    if os.geteuid() == 0:
        return argv
    return ["sudo", *argv]


def _run(argv, timeout=120, input_text=None, capture=True, check=False):
    kw = {
        "timeout": timeout,
        "env": _nmcli_env(),
    }
    if capture:
        kw["capture_output"] = True
        kw["text"] = True
    if input_text is not None:
        kw["input"] = input_text
    return subprocess.run(_with_sudo(argv), **kw)


def check_internet():
    """Проверяет наличие интернет-соединения."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def get_wifi_device():
    """Первое Wi-Fi устройство из nmcli (fallback, если заданный интерфейс недоступен)."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=_nmcli_env(),
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line and ':wifi' in line:
                    device = line.split(':')[0]
                    if device and device != '':
                        return device
    except Exception as e:
        print(f"[WiFiAutoConnect] Error getting WiFi device: {e}", flush=True)
    return None


def iface_exists(iface: str) -> bool:
    try:
        r = subprocess.run(
            ["ip", "link", "show", iface],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_wifi_iface() -> Optional[str]:
    """Как connect_wifi.sh: предпочитаем wlan0 (или RGW2_WIFI_IFACE), иначе первое wifi из nmcli."""
    if iface_exists(WIFI_IFACE):
        return WIFI_IFACE
    fallback = get_wifi_device()
    if fallback:
        print(
            f"[WiFiAutoConnect] {WIFI_IFACE} not found, using nmcli device {fallback}",
            flush=True,
        )
        return fallback
    print(
        f"[WiFiAutoConnect] No WiFi interface ({WIFI_IFACE} missing and nmcli empty)",
        flush=True,
    )
    return None


def ensure_managed_mode(iface: str) -> None:
    """Шаг 1 из connect_wifi.sh: Mode Managed через iwconfig/iw."""
    mode = "unknown"
    try:
        r = subprocess.run(
            ["iwconfig", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            m = re.search(r"Mode:([^\s]+)", r.stdout)
            if m:
                mode = m.group(1)
    except FileNotFoundError:
        pass
    if mode == "Managed":
        print(f"[WiFiAutoConnect] {iface} already in Managed mode", flush=True)
        return
    print(f"[WiFiAutoConnect] Switching {iface} to Managed mode...", flush=True)
    _run(["ip", "link", "set", iface, "down"], timeout=15)
    _run(["iwconfig", iface, "mode", "managed"], timeout=15)
    _run(["iw", "dev", iface, "set", "type", "managed"], timeout=15)
    _run(["ip", "link", "set", iface, "up"], timeout=15)
    time.sleep(2)


def has_ipv4_on_iface(iface: str) -> bool:
    try:
        r = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and "inet " in r.stdout
    except Exception:
        return False


def iw_link_ssid(iface: str) -> Optional[str]:
    """Текущая SSID с интерфейса (iw dev … link), нужна после wpa_supplicant без NM."""
    try:
        r = subprocess.run(
            ["iw", "dev", iface, "link"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        m = re.search(r"SSID:\s*(\S+)", r.stdout)
        return m.group(1) if m else None
    except Exception:
        return None


def nmcli_wifi_connected(iface: str) -> bool:
    """wlan0 + connected, как grep в connect_wifi.sh."""
    try:
        r = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=_nmcli_env(),
        )
        if r.returncode != 0:
            return False
        for line in r.stdout.strip().split("\n"):
            if not line.startswith(f"{iface}:"):
                continue
            parts = line.split(":")
            if len(parts) >= 2 and parts[1].lower() == "connected":
                return True
    except Exception as e:
        print(f"[WiFiAutoConnect] nmcli_wifi_connected error: {e}", flush=True)
    return False


def unblock_wifi():
    """Разблокирует Wi-Fi адаптер если он заблокирован (soft block)."""
    try:
        # Проверяем статус блокировки
        result = subprocess.run(
            ["rfkill", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            wifi_devices = []
            
            # Парсим вывод rfkill list
            current_device = None
            for line in lines:
                line = line.strip()
                # Строка с номером устройства и типом (например: "0: phy0: Wireless LAN")
                if ':' in line and ('Wireless LAN' in line or 'wifi' in line.lower()):
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[0].strip().isdigit():
                        current_device = {
                            'id': parts[0].strip(),
                            'type': parts[1].strip() if len(parts) > 1 else '',
                            'soft_blocked': False,
                            'hard_blocked': False
                        }
                        wifi_devices.append(current_device)
                # Проверяем статус блокировки
                elif current_device:
                    if 'Soft blocked: yes' in line:
                        current_device['soft_blocked'] = True
                    elif 'Hard blocked: yes' in line:
                        current_device['hard_blocked'] = True
            
            # Проверяем, есть ли заблокированные устройства
            blocked_devices = [d for d in wifi_devices if d['soft_blocked']]
            
            if blocked_devices:
                print(f"[WiFiAutoConnect] Found {len(blocked_devices)} soft-blocked WiFi device(s)", flush=True)
                # Разблокируем все заблокированные устройства
                for device in blocked_devices:
                    print(f"[WiFiAutoConnect] Unblocking WiFi device {device['id']} ({device['type']})...", flush=True)
                    unblock_result = subprocess.run(
                        ["rfkill", "unblock", device['id']],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if unblock_result.returncode == 0:
                        print(f"[WiFiAutoConnect] WiFi device {device['id']} unblocked successfully", flush=True)
                    else:
                        print(f"[WiFiAutoConnect] Failed to unblock device {device['id']}: {unblock_result.stderr}", flush=True)
                
                # Также пробуем общую команду для всех Wi-Fi устройств
                unblock_result = subprocess.run(
                    ["rfkill", "unblock", "wifi"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if unblock_result.returncode == 0:
                    print(f"[WiFiAutoConnect] All WiFi devices unblocked", flush=True)
                
                time.sleep(1)  # Даем время адаптеру активироваться
                return True
            else:
                # Адаптер не заблокирован, но все равно пробуем разблокировать для надежности
                unblock_result = subprocess.run(
                    ["rfkill", "unblock", "wifi"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return True
        
        # Альтернативный способ: разблокируем все Wi-Fi устройства
        print(f"[WiFiAutoConnect] Attempting to unblock all WiFi devices...", flush=True)
        unblock_result = subprocess.run(
            ["rfkill", "unblock", "wifi"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if unblock_result.returncode == 0:
            print(f"[WiFiAutoConnect] WiFi adapters unblocked", flush=True)
            time.sleep(1)
            return True
        else:
            print(f"[WiFiAutoConnect] Failed to unblock WiFi: {unblock_result.stderr}", flush=True)
            return False
            
    except FileNotFoundError:
        print(f"[WiFiAutoConnect] rfkill not found, skipping unblock check", flush=True)
        return True
    except Exception as e:
        print(f"[WiFiAutoConnect] Error checking/unblocking WiFi: {e}", flush=True)
        return False


def is_connected_to_ssid(ssid: str):
    """Проверяет, подключен ли нужный интерфейс к указанной SSID (учёт имени профиля NM ≠ SSID)."""
    iface = resolve_wifi_iface()
    if not iface:
        return False
    linked = iw_link_ssid(iface)
    if linked == ssid and has_ipv4_on_iface(iface):
        return True
    if has_ipv4_on_iface(iface) and not shutil.which("nmcli"):
        return linked == ssid if linked else False
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            env=_nmcli_env(),
        )
        if result.returncode != 0:
            return False
        for line in result.stdout.strip().split("\n"):
            if not line.startswith(f"{iface}:"):
                continue
            parts = line.split(":")
            if len(parts) < 4:
                continue
            dev, typ, state, conn = parts[0], parts[1], parts[2], ":".join(parts[3:])
            if typ != "wifi" or state.lower() != "connected":
                continue
            if conn == ssid:
                return True
            if conn and conn != "--":
                conn_result = subprocess.run(
                    [
                        "nmcli",
                        "-t",
                        "-f",
                        "802-11-wireless.ssid",
                        "connection",
                        "show",
                        conn,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=_nmcli_env(),
                )
                if conn_result.returncode == 0 and conn_result.stdout.strip() == ssid:
                    return True
    except Exception as e:
        print(f"[WiFiAutoConnect] Error checking connection: {e}", flush=True)
    return False


def _connect_via_nmcli(ssid: str, password: str, iface: str) -> bool:
    """Шаги 3 connect_wifi.sh: rescan, delete профиля, wifi connect … ifname."""
    print("[WiFiAutoConnect] Using NetworkManager (nmcli)...", flush=True)
    _run(["nmcli", "device", "wifi", "rescan"], timeout=30)
    time.sleep(3)
    _run(["nmcli", "connection", "delete", ssid], timeout=30)
    r = _run(
        [
            "nmcli",
            "device",
            "wifi",
            "connect",
            ssid,
            "password",
            password,
            "ifname",
            iface,
        ],
        timeout=120,
    )
    time.sleep(5)
    if r.returncode == 0 and nmcli_wifi_connected(iface):
        print(f"[WiFiAutoConnect] Connected to {ssid} via nmcli on {iface}", flush=True)
        return True
    err = (r.stderr or r.stdout or "")[:300]
    if err:
        print(f"[WiFiAutoConnect] nmcli connect issue: {err}", flush=True)
    return nmcli_wifi_connected(iface)


def _connect_via_wpa_supplicant(ssid: str, password: str, iface: str, stop_nm: bool) -> bool:
    """Fallback из connect_wifi.sh: managed no, wpa_passphrase, wpa_supplicant, dhclient."""
    print("[WiFiAutoConnect] Trying wpa_supplicant fallback...", flush=True)
    if stop_nm and shutil.which("systemctl"):
        _run(["systemctl", "stop", "NetworkManager"], timeout=60)
    else:
        _run(["nmcli", "device", "set", iface, "managed", "no"], timeout=30)
    wpa_cfg = f"/tmp/wpa_supplicant_{ssid}.conf"
    pr = subprocess.run(
        ["wpa_passphrase", ssid, password],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if pr.returncode != 0 or not pr.stdout:
        print("[WiFiAutoConnect] wpa_passphrase failed", flush=True)
        return False
    tee = subprocess.run(
        _with_sudo(["tee", wpa_cfg]),
        input=pr.stdout,
        text=True,
        timeout=10,
        capture_output=True,
        env=_nmcli_env(),
    )
    if tee.returncode != 0:
        print("[WiFiAutoConnect] Could not write wpa config", flush=True)
        return False
    _run(["killall", "wpa_supplicant"], timeout=15)
    time.sleep(1)
    r = _run(
        [
            "wpa_supplicant",
            "-B",
            "-i",
            iface,
            "-c",
            wpa_cfg,
            "-D",
            "nl80211,wext",
        ],
        timeout=30,
    )
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "")[:200]
        print(f"[WiFiAutoConnect] wpa_supplicant failed: {msg}", flush=True)
    time.sleep(5)
    _run(["dhclient", "-v", iface], timeout=60)
    if has_ipv4_on_iface(iface):
        print(f"[WiFiAutoConnect] Connected via wpa_supplicant on {iface}", flush=True)
        return True
    return False


def connect_to_wifi(ssid: str, password: str):
    """Подключение как в connect_wifi.sh: managed → nmcli (rescan, delete, connect ifname) → wpa."""
    if not unblock_wifi():
        print(
            "[WiFiAutoConnect] Warning: Could not unblock WiFi adapter, but continuing...",
            flush=True,
        )

    iface = resolve_wifi_iface()
    if not iface:
        return False

    print(f"[WiFiAutoConnect] Connecting to {ssid} on {iface}...", flush=True)

    try:
        ensure_managed_mode(iface)

        if shutil.which("nmcli"):
            if _connect_via_nmcli(ssid, password, iface):
                return True
            if _connect_via_wpa_supplicant(ssid, password, iface, stop_nm=False):
                return True
            return False

        print(
            "[WiFiAutoConnect] nmcli not found, using wpa_supplicant only (stopping NM)...",
            flush=True,
        )
        return _connect_via_wpa_supplicant(ssid, password, iface, stop_nm=True)

    except subprocess.TimeoutExpired:
        print(f"[WiFiAutoConnect] Timeout while connecting to {ssid}", flush=True)
        return False
    except Exception as e:
        print(f"[WiFiAutoConnect] Error connecting to {ssid}: {e}", flush=True)
        return False


def run():
    """
    Основная функция сервиса.
    Проверяет подключение, подключается если необходимо, затем уходит в sleep.
    Работает как Docker контейнер: проверяет при запуске, затем спит.
    """
    print(f"[WiFiAutoConnect] Service started", flush=True)
    
    try:
        # Проверяем и разблокируем Wi-Fi адаптер если необходимо
        unblock_wifi()
        
        # Проверяем подключение к интернету
        has_internet = check_internet()
        print(f"[WiFiAutoConnect] Internet connection: {'OK' if has_internet else 'NO'}", flush=True)
        
        # Проверяем подключение к нужной сети
        is_connected = is_connected_to_ssid(WIFI_SSID)
        print(f"[WiFiAutoConnect] Connected to {WIFI_SSID}: {'YES' if is_connected else 'NO'}", flush=True)
        
        # Если нет интернета или не подключены к нужной сети, пытаемся подключиться
        if not has_internet or not is_connected:
            print(f"[WiFiAutoConnect] Attempting to connect to {WIFI_SSID}...", flush=True)
            if connect_to_wifi(WIFI_SSID, WIFI_PASSWORD):
                # Проверяем интернет после подключения
                time.sleep(2)
                has_internet = check_internet()
                print(f"[WiFiAutoConnect] Internet connection after connect: {'OK' if has_internet else 'NO'}", flush=True)
            else:
                print(f"[WiFiAutoConnect] Failed to connect to {WIFI_SSID}", flush=True)
        else:
            print(f"[WiFiAutoConnect] Already connected to {WIFI_SSID} with internet", flush=True)
        
        print(f"[WiFiAutoConnect] Check complete. Going to sleep (like Docker container)...", flush=True)
        
        # Уходим в sleep (как Docker контейнер)
        # Сервис будет перезапущен при необходимости через services_manager
        # Спим бесконечно, периодически проверяя соединение
        check_interval = 3600  # Проверяем каждый час
        while True:
            time.sleep(check_interval)
            # Периодическая проверка
            print(f"[WiFiAutoConnect] Periodic check...", flush=True)
            # Проверяем и разблокируем Wi-Fi адаптер если необходимо
            unblock_wifi()
            has_internet = check_internet()
            is_connected = is_connected_to_ssid(WIFI_SSID)
            if not has_internet or not is_connected:
                print(f"[WiFiAutoConnect] Connection lost. Reconnecting...", flush=True)
                connect_to_wifi(WIFI_SSID, WIFI_PASSWORD)
            else:
                print(f"[WiFiAutoConnect] Connection OK", flush=True)
                
    except KeyboardInterrupt:
        print(f"[WiFiAutoConnect] Service stopped by user", flush=True)
    except Exception as e:
        print(f"[WiFiAutoConnect] Unexpected error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        # Даже при ошибке уходим в sleep, чтобы сервис не падал
        print(f"[WiFiAutoConnect] Going to sleep after error...", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print(f"[WiFiAutoConnect] Service stopped", flush=True)


if __name__ == "__main__":
    run()

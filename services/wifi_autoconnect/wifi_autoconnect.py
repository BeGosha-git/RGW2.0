"""
Сервис для автоматического подключения к Wi-Fi сети BeRobots.
Проверяет подключение при запуске, подключается если необходимо, затем уходит в sleep.
"""
import os
import sys
import time
import subprocess
from pathlib import Path

# Добавляем корневую директорию в путь для импорта модулей проекта
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Импортируем services_manager для обнаружения сервиса
import services_manager

# Имя сервиса для регистрации
SERVICE_NAME = "wifi_autoconnect"

def get_service_name() -> str:
    """Возвращает имя сервиса."""
    return SERVICE_NAME

# Параметры Wi-Fi сети
WIFI_SSID = "BeRobots"
WIFI_PASSWORD = "Unitree0408"


def check_internet():
    """Проверяет наличие интернет-соединения."""
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def get_wifi_device():
    """Получает имя Wi-Fi устройства."""
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5
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
    """Проверяет, подключен ли к указанной SSID."""
    try:
        # Проверяем активные Wi-Fi соединения через device status
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,CONNECTION", "device", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line and ':wifi:' in line:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        connection_name = parts[2]
                        # Проверяем, совпадает ли имя соединения с SSID
                        if connection_name == ssid:
                            return True
                        # Также проверяем через активное соединение
                        if connection_name and connection_name != '--':
                            # Получаем SSID активного соединения
                            conn_result = subprocess.run(
                                ["nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", connection_name],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if conn_result.returncode == 0:
                                active_ssid = conn_result.stdout.strip()
                                if active_ssid == ssid:
                                    return True
    except Exception as e:
        print(f"[WiFiAutoConnect] Error checking connection: {e}", flush=True)
    return False


def connect_to_wifi(ssid: str, password: str):
    """Подключается к Wi-Fi сети."""
    # Сначала проверяем и разблокируем Wi-Fi адаптер если необходимо
    if not unblock_wifi():
        print(f"[WiFiAutoConnect] Warning: Could not unblock WiFi adapter, but continuing...", flush=True)
    
    wifi_device = get_wifi_device()
    if not wifi_device:
        print(f"[WiFiAutoConnect] No WiFi device found", flush=True)
        return False
    
    print(f"[WiFiAutoConnect] Connecting to {ssid}...", flush=True)
    
    try:
        # Проверяем, существует ли уже профиль для этой сети
        result = subprocess.run(
            ["nmcli", "connection", "show", ssid],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # Профиль существует, активируем его
            print(f"[WiFiAutoConnect] Activating existing connection {ssid}...", flush=True)
            result = subprocess.run(
                ["nmcli", "connection", "up", ssid],
                capture_output=True,
                text=True,
                timeout=30
            )
        else:
            # Профиль не существует, создаем новый
            print(f"[WiFiAutoConnect] Creating new connection {ssid}...", flush=True)
            result = subprocess.run(
                [
                    "nmcli", "device", "wifi", "connect", ssid,
                    "password", password
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
        
        if result.returncode == 0:
            print(f"[WiFiAutoConnect] Successfully connected to {ssid}", flush=True)
            # Ждем немного для установления соединения
            time.sleep(3)
            return True
        else:
            error_msg = result.stderr if result.stderr else result.stdout
            print(f"[WiFiAutoConnect] Failed to connect: {error_msg[:200]}", flush=True)
            return False
            
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

"""
Сервис для периодического сканирования сети и сохранения найденных IP адресов.
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any
import network

# Добавляем корневую директорию в путь для импорта network
sys.path.insert(0, str(Path(__file__).parent.parent))

# Путь к файлу для сохранения результатов
IPS_FILE = Path(__file__).parent.parent / "data" / "ips.json"


def ensure_data_dir():
    """Создает директорию data если её нет."""
    ips_file = Path(IPS_FILE)
    ips_file.parent.mkdir(parents=True, exist_ok=True)
    return ips_file


def load_ips() -> Dict[str, Any]:
    """
    Загружает сохраненные IP адреса из файла.
    
    Returns:
        Словарь с данными о найденных IP
    """
    ips_file = ensure_data_dir()
    
    if not ips_file.exists():
        return {
            "last_scan": None,
            "scan_count": 0,
            "ips": []
        }
    
    try:
        with open(ips_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"Error loading ips.json: {str(e)}", flush=True)
        return {
            "last_scan": None,
            "scan_count": 0,
            "ips": []
        }


def save_ips(ips: List[str], scan_timestamp: float):
    """
    Сохраняет найденные IP адреса в файл.
    
    Args:
        ips: Список найденных IP адресов
        scan_timestamp: Временная метка сканирования
    """
    ips_file = ensure_data_dir()
    
    # Загружаем существующие данные
    data = load_ips()
    
    # Обновляем данные - храним только последний скан
    data["last_scan"] = scan_timestamp
    data["scan_count"] = data.get("scan_count", 0) + 1
    data["ips"] = ips
    
    # Удаляем историю, если она есть (больше не храним)
    if "history" in data:
        del data["history"]
    
    try:
        with open(ips_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(ips)} IP(s) to {ips_file}", flush=True)
    except Exception as e:
        print(f"Error saving ips.json: {str(e)}", flush=True)


def scan_network():
    """
    Выполняет сканирование сети и сохраняет результаты.
    """
    try:
        print(f"Starting network scan...", flush=True)
        scan_start = time.time()
        
        # Сканируем сеть
        found_ips = network.find_robots_in_network(port=80, timeout=0.5)
        
        scan_end = time.time()
        scan_duration = scan_end - scan_start
        
        # Сохраняем результаты
        save_ips(found_ips, scan_end)
        
        print(f"Scan completed in {scan_duration:.2f}s. Found {len(found_ips)} IP(s): {found_ips}", flush=True)
        
    except Exception as e:
        print(f"Error during network scan: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()


def run_scanner(scan_interval: int = 20):
    """
    Запускает периодическое сканирование сети.
    
    Args:
        scan_interval: Интервал между сканированиями в секундах
    """
    print(f"Network scanner service started", flush=True)
    print(f"Scan interval: {scan_interval} seconds", flush=True)
    print(f"Results will be saved to: {IPS_FILE}", flush=True)
    
    # Выполняем первое сканирование сразу
    scan_network()
    
    # Затем сканируем каждые scan_interval секунд
    while True:
        try:
            time.sleep(scan_interval)
            scan_network()
        except KeyboardInterrupt:
            print("\nScanner service stopped", flush=True)
            break
        except Exception as e:
            print(f"Error in scanner loop: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            # Продолжаем работу даже при ошибке
            time.sleep(5)


def run():
    """Точка входа для запуска сервиса сканера."""
    run_scanner(scan_interval=20)


if __name__ == '__main__':
    run()

"""
Модуль для сканирования сети и сохранения найденных IP адресов в ips.json.
Используется разово перед обновлением системы.
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Any
import network

# Путь к файлу для сохранения результатов
IPS_FILE = Path(__file__).parent / "data" / "ips.json"


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
    
    Returns:
        True если успешно
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
        return True
        
    except Exception as e:
        print(f"Error during network scan: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    scan_network()

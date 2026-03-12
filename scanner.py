"""
Модуль для сканирования сети и сохранения найденных IP адресов в ips.json.
Используется разово перед обновлением системы.
"""
import time
from typing import List, Dict, Any, Optional
import network
from utils.logger import get_logger
from utils.file_utils import JSONFileManager, ensure_data_dir
from utils.path_utils import get_data_dir

logger = get_logger(__name__)

# Путь к файлу для сохранения результатов
IPS_FILE = get_data_dir() / "ips.json"

# Менеджер для работы с файлом IP адресов
_ips_manager = JSONFileManager(IPS_FILE, {
    "last_scan": None,
    "scan_count": 0,
    "ips": []
})


def load_ips() -> Dict[str, Any]:
    """
    Загружает сохраненные IP адреса из файла.
    
    Returns:
        Словарь с данными о найденных IP
    """
    return _ips_manager.load()


def save_ips(ips: List[str], scan_timestamp: float, network_base: Optional[str] = None):
    """
    Сохраняет найденные IP адреса в файл.
    Удаляет старые IP из той же подсети перед добавлением новых.
    
    Args:
        ips: Список найденных IP адресов
        scan_timestamp: Временная метка сканирования
        network_base: Базовая подсеть (например, "192.168.88" или "192.168.123")
                      Если указана, удаляет старые IP из этой подсети перед добавлением новых
    """
    # Загружаем существующие данные
    data = load_ips()
    existing_ips = data.get("ips", [])
    
    # Если указана подсеть, удаляем старые IP из этой подсети
    if network_base:
        existing_ips = [ip for ip in existing_ips if not ip.startswith(network_base + ".")]
    
    # Объединяем существующие IP (без удаленных) с новыми, убираем дубликаты
    all_ips = list(dict.fromkeys(existing_ips + ips))
    
    # Обновляем данные
    data["last_scan"] = scan_timestamp
    data["scan_count"] = data.get("scan_count", 0) + 1
    data["ips"] = all_ips
    
    # Удаляем историю, если она есть (больше не храним)
    if "history" in data:
        del data["history"]
    
    if _ips_manager.save(data):
        logger.info(f"Saved {len(all_ips)} IP(s) to {IPS_FILE} (added {len(ips)} from subnet {network_base if network_base else 'default'})")
    else:
        logger.error(f"Failed to save IPs to {IPS_FILE}")


def scan_network(port: Optional[int] = None, network_base: Optional[str] = None):
    """
    Выполняет сканирование сети и сохраняет результаты.
    
    Args:
        port: Порт для сканирования (None = из конфигурации, по умолчанию 8080)
        network_base: Базовая подсеть для сканирования (например, "192.168.88" или "192.168.123")
    
    Returns:
        True если успешно
    """
    try:
        if port is None:
            try:
                import services_manager
                port = services_manager.get_scanner_port()
            except Exception:
                port = 8080
        
        scan_start = time.time()
        
        # Уменьшаем таймаут в 1.5 раза (было 0.5, стало 0.333)
        timeout = 0.5 / 1.5
        
        # Сканируем сеть
        found_ips = network.find_robots_in_network(port=port, timeout=timeout, network_base=network_base)
        
        scan_end = time.time()
        scan_duration = scan_end - scan_start
        
        # Сохраняем результаты (объединяем с существующими, удаляя старые из той же подсети)
        save_ips(found_ips, scan_end, network_base=network_base)
        
        network_info = f"subnet {network_base}" if network_base else "default network"
        logger.info(f"Scan completed in {scan_duration:.2f}s on {network_info}. Found {len(found_ips)} IP(s): {found_ips}")
        return True
        
    except Exception as e:
        logger.error(f"Error during network scan: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    scan_network()

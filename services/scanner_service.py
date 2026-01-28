"""
Сервис для периодического сканирования сети и сохранения найденных IP адресов в ips.json.
Использует scanner.py для выполнения сканирования.
"""
import os
import sys
import time
from pathlib import Path

# Добавляем корневую директорию в путь для импорта модулей проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

# Импорты модулей проекта
import services_manager
import status
import scanner


def get_service_name() -> str:
    """
    Возвращает имя сервиса (используется для регистрации в services_manager).
    
    Returns:
        Имя сервиса
    """
    return Path(__file__).stem


def run_service_loop(scan_interval: int = 20):
    """
    Основной цикл работы сервиса сканирования сети.
    
    Args:
        scan_interval: Интервал между сканированиями в секундах
    """
    service_name = get_service_name()
    manager = services_manager.get_services_manager()
    
    print(f"Scanner service started", flush=True)
    print(f"Scan interval: {scan_interval} seconds", flush=True)
    
    # Регистрируем начальные данные в status.py
    status.register_service_data(service_name, {
        "status": "running",
        "started_at": time.time(),
        "scan_interval": scan_interval,
        "scans_count": 0,
        "last_scan_time": None
    })
    
    scans_count = 0
    
    # Выполняем первое сканирование сразу
    try:
        print(f"Performing initial network scan...", flush=True)
        scanner.scan_network()
        scans_count += 1
        status.register_service_data(service_name, {
            "status": "running",
            "started_at": status.get_service_data(service_name).get("started_at", time.time()) if status.get_service_data(service_name) else time.time(),
            "scan_interval": scan_interval,
            "scans_count": scans_count,
            "last_scan_time": time.time()
        })
    except Exception as e:
        print(f"Error during initial scan: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
    
    # Затем сканируем каждые scan_interval секунд
    while True:
        try:
            # Проверяем статус сервиса через services_manager
            service_info = manager.get_service(service_name)
            service_status = service_info.get("status", "ON")
            
            if service_status == "OFF":
                print(f"Scanner service is OFF. Stopping...", flush=True)
                status.unregister_service_data(service_name)
                break
            elif service_status == "SLEEP":
                # В режиме SLEEP сервис не выполняет работу, но остается активным
                time.sleep(scan_interval)
                continue
            
            # Ждем перед следующим сканированием
            time.sleep(scan_interval)
            
            # Выполняем сканирование
            print(f"Performing network scan...", flush=True)
            scanner.scan_network()
            scans_count += 1
            
            # Обновляем данные в status.py
            status.register_service_data(service_name, {
                "status": "running",
                "started_at": status.get_service_data(service_name).get("started_at", time.time()) if status.get_service_data(service_name) else time.time(),
                "scan_interval": scan_interval,
                "scans_count": scans_count,
                "last_scan_time": time.time()
            })
            
        except KeyboardInterrupt:
            print(f"\nScanner service stopped by user", flush=True)
            status.unregister_service_data(service_name)
            break
        except Exception as e:
            print(f"Error in scanner service: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            
            # Обновляем данные об ошибке
            status.register_service_data(service_name, {
                "status": "error",
                "error": str(e),
                "last_error_time": time.time(),
                "scans_count": scans_count
            })
            
            # Продолжаем работу даже при ошибке
            time.sleep(5)


def run():
    """
    Точка входа для запуска сервиса.
    Эта функция вызывается run.py для запуска сервиса.
    """
    # Получаем параметры сервиса из services_manager
    service_name = get_service_name()
    manager = services_manager.get_services_manager()
    service_info = manager.get_service(service_name)
    params = manager.get_service_parameters(service_name)
    
    # Получаем интервал из параметров или используем значение по умолчанию
    scan_interval = params.get("scan_interval", 20)
    
    # Запускаем основной цикл
    run_service_loop(scan_interval=scan_interval)


def main():
    """
    Альтернативная точка входа (если функция run() не используется).
    """
    run()


if __name__ == '__main__':
    # Для прямого запуска сервиса (не через run.py)
    run()

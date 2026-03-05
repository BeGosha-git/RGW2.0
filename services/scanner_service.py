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


def run_service_loop(scan_interval: int = 20, scan_port: int = 8080):
    """
    Основной цикл работы сервиса сканирования сети.
    КРИТИЧНО: Сервис не должен падать, все ошибки обрабатываются.
    
    Args:
        scan_interval: Интервал между сканированиями в секундах
        scan_port: Порт для сканирования
    """
    service_name = get_service_name()
    
    try:
        manager = services_manager.get_services_manager()
    except Exception as e:
        print(f"Scanner service: Error getting services_manager: {e}, retrying...", flush=True)
        time.sleep(5)
        try:
            manager = services_manager.get_services_manager()
        except Exception:
            print(f"Scanner service: Failed to get services_manager, exiting", flush=True)
            return
    
    print(f"Scanner service started", flush=True)
    print(f"Scan interval: {scan_interval} seconds, port: {scan_port}", flush=True)
    
    # Регистрируем начальные данные в status.py
    try:
        status.register_service_data(service_name, {
            "status": "running",
            "started_at": time.time(),
            "scan_interval": scan_interval,
            "scans_count": 0,
            "last_scan_time": None
        })
    except Exception as e:
        print(f"Scanner service: Error registering initial status: {e}", flush=True)
    
    scans_count = 0
    # Подсети для чередования
    subnets = ["192.168.88", "192.168.123"]
    subnet_counter = 0  # Индекс текущей подсети
    
    # Выполняем первое сканирование сразу (начинаем с первой подсети)
    try:
        current_subnet = subnets[subnet_counter]
        print(f"Performing initial network scan on subnet {current_subnet} (port {scan_port})...", flush=True)
        scanner.scan_network(port=scan_port, network_base=current_subnet)
        scans_count += 1
        subnet_counter = (subnet_counter + 1) % 2  # Переключаем на следующую подсеть

        try:
            status.register_service_data(service_name, {
                "status": "running",
                "started_at": time.time(),
                "scan_interval": scan_interval,
                "scans_count": scans_count,
                "last_scan_time": time.time()
            })
        except Exception:
            pass
    except RuntimeError as e:
        # Обрабатываем ошибку завершения интерпретатора
        if "cannot schedule new futures" in str(e) or "interpreter shutdown" in str(e):
            print(f"Scanner service stopping: interpreter is shutting down", flush=True)
            try:
                status.unregister_service_data(service_name)
            except Exception:
                pass
            return
        print(f"Error during initial scan: {str(e)}", flush=True)
    except Exception as e:
        print(f"Error during initial scan: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
    
    # Затем сканируем каждые scan_interval секунд
    while True:
        try:
            # Проверяем статус сервиса через services_manager
            try:
                service_info = manager.get_service(service_name)
                service_status = service_info.get("status", "ON")
            except Exception as e:
                print(f"Scanner service: Error getting service status: {e}, continuing...", flush=True)
                service_status = "ON"  # По умолчанию продолжаем работу
            
            if service_status == "OFF":
                print(f"Scanner service is OFF. Stopping...", flush=True)
                try:
                    status.unregister_service_data(service_name)
                except Exception:
                    pass
                break
            elif service_status == "SLEEP":
                # В режиме SLEEP сервис не выполняет работу, но остается активным
                time.sleep(scan_interval)
                continue
            
            # Ждем перед следующим сканированием
            time.sleep(scan_interval)
            
            # Выполняем сканирование (чередуем подсети)
            try:
                current_subnet = subnets[subnet_counter]
                print(f"Performing network scan on subnet {current_subnet} (port {scan_port})...", flush=True)
                scanner.scan_network(port=scan_port, network_base=current_subnet)
                scans_count += 1
                # Переключаем на следующую подсеть для следующего сканирования
                subnet_counter = (subnet_counter + 1) % 2

                if subnet_counter > 100:
                    subnet_counter = 0
                
                # Обновляем данные в status.py
                try:
                    status.register_service_data(service_name, {
                        "status": "running",
                        "started_at": time.time(),
                        "scan_interval": scan_interval,
                        "scans_count": scans_count,
                        "last_scan_time": time.time()
                    })
                except Exception as e:
                    print(f"Scanner service: Error updating status: {e}", flush=True)
            except RuntimeError as e:
                # Обрабатываем ошибку завершения интерпретатора
                if "cannot schedule new futures" in str(e) or "interpreter shutdown" in str(e):
                    print(f"Scanner service stopping: interpreter is shutting down", flush=True)
                    try:
                        status.unregister_service_data(service_name)
                    except Exception:
                        pass
                    break
                # Другие RuntimeError - логируем и продолжаем
                print(f"Error in scanner.scan_network(): {str(e)}", flush=True)
                time.sleep(5)
            except Exception as e:
                print(f"Error during network scan: {str(e)}", flush=True)
                import traceback
                traceback.print_exc()
                
                # Обновляем данные об ошибке
                try:
                    status.register_service_data(service_name, {
                        "status": "error",
                        "error": str(e),
                        "last_error_time": time.time(),
                        "scans_count": scans_count
                    })
                except Exception:
                    pass
                
                # Продолжаем работу даже при ошибке
                time.sleep(5)
            
        except KeyboardInterrupt:
            print(f"\nScanner service stopped by user", flush=True)
            try:
                status.unregister_service_data(service_name)
            except Exception:
                pass
            break
        except RuntimeError as e:
            # Обрабатываем ошибку завершения интерпретатора
            if "cannot schedule new futures" in str(e) or "interpreter shutdown" in str(e):
                print(f"Scanner service stopping: interpreter is shutting down", flush=True)
                try:
                    status.unregister_service_data(service_name)
                except Exception:
                    pass
                break
            # Другие RuntimeError - логируем и продолжаем
            print(f"RuntimeError in scanner service: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            time.sleep(5)
        except Exception as e:
            # КРИТИЧНО: Любая другая ошибка - логируем, но НЕ ПАДАЕМ
            print(f"CRITICAL ERROR in scanner service: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            
            try:
                status.register_service_data(service_name, {
                    "status": "error",
                    "error": str(e),
                    "last_error_time": time.time(),
                    "scans_count": scans_count
                })
            except Exception:
                pass
            
            # Продолжаем работу даже при критической ошибке
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
    
    # Получаем параметры из конфигурации
    scan_interval = params.get("scan_interval", 20)
    scan_port = params.get("port", 8080)
    
    # Запускаем основной цикл
    run_service_loop(scan_interval=scan_interval, scan_port=scan_port)


def main():
    """
    Альтернативная точка входа (если функция run() не используется).
    """
    run()


if __name__ == '__main__':
    # Для прямого запуска сервиса (не через run.py)
    run()

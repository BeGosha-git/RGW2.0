"""
Пример сервиса для RGW 2.0.
Этот файл служит шаблоном для создания новых сервисов.

Структура сервиса:
1. Импорты и настройки
2. Функции сервиса
3. Функция run() - точка входа для запуска сервиса
4. Блок if __name__ == '__main__' для прямого запуска

Сервисы должны:
- Иметь функцию run() или main() для запуска
- Регистрировать свои данные в status.py через register_service_data()
- Использовать services_manager для проверки статуса (ON/OFF/SLEEP)
- Обрабатывать ошибки и логировать их
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


def get_service_name() -> str:
    """
    Возвращает имя сервиса (используется для регистрации в services_manager).
    
    Returns:
        Имя сервиса
    """
    # Имя сервиса обычно соответствует имени файла без расширения
    return Path(__file__).stem


def run_service_loop(interval: int = 10):
    """
    Основной цикл работы сервиса.
    
    Args:
        interval: Интервал между итерациями в секундах
    """
    service_name = get_service_name()
    manager = services_manager.get_services_manager()
    
    print(f"Service {service_name} started", flush=True)
    
    # Регистрируем начальные данные в status.py
    status.register_service_data(service_name, {
        "status": "running",
        "started_at": time.time(),
        "iterations": 0
    })
    
    iteration_count = 0
    
    while True:
        try:
            # Проверяем статус сервиса через services_manager
            service_info = manager.get_service(service_name)
            service_status = service_info.get("status", "ON")
            
            if service_status == "OFF":
                print(f"Service {service_name} is OFF. Stopping...", flush=True)
                status.unregister_service_data(service_name)
                break
            elif service_status == "SLEEP":
                # В режиме SLEEP сервис не выполняет работу, но остается активным
                time.sleep(interval)
                continue
            
            # Основная логика сервиса здесь
            iteration_count += 1
            
            # Пример: выполнение работы
            print(f"Service {service_name} iteration {iteration_count}", flush=True)
            
            # Обновляем данные в status.py
            status.register_service_data(service_name, {
                "status": "running",
                "started_at": status.get_service_data(service_name).get("started_at", time.time()) if status.get_service_data(service_name) else time.time(),
                "iterations": iteration_count,
                "last_iteration": time.time()
            })
            
            # Ждем перед следующей итерацией
            time.sleep(interval)
            
        except KeyboardInterrupt:
            print(f"\nService {service_name} stopped by user", flush=True)
            status.unregister_service_data(service_name)
            break
        except Exception as e:
            print(f"Error in service {service_name}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            
            # Обновляем данные об ошибке
            status.register_service_data(service_name, {
                "status": "error",
                "error": str(e),
                "last_error_time": time.time()
            })
            
            # Продолжаем работу даже при ошибке
            time.sleep(1)


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
    interval = params.get("interval", 10)
    
    # Запускаем основной цикл
    run_service_loop(interval=interval)


def main():
    """
    Альтернативная точка входа (если функция run() не используется).
    """
    run()


if __name__ == '__main__':
    # Для прямого запуска сервиса (не через run.py)
    run()

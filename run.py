"""
Модуль для запуска всех .py файлов в папке /services.
Использует services_manager для проверки статусов сервисов.
"""
import os
import sys
import importlib.util
import threading
import time
from pathlib import Path
from typing import List, Dict
import services_manager

# Отключаем буферизацию для корректного вывода в Docker
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

# Устанавливаем PYTHONUNBUFFERED если не установлен
if 'PYTHONUNBUFFERED' not in os.environ:
    os.environ['PYTHONUNBUFFERED'] = '1'

# Принудительно отключаем буферизацию
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)


class ServiceRunner:
    """Класс для запуска сервисов из папки services."""
    
    def __init__(self):
        """Инициализация запуска сервисов."""
        self.services: List[Dict] = []
        self.threads: List[threading.Thread] = []
        self.service_files: List[str] = []  # Список файлов сервисов для перезапуска
        self.running = False
        self.manager = services_manager.get_services_manager()
    
    def find_services(self, services_dir: str = "services", api_dir: str = "api") -> List[str]:
        """
        Находит все .py файлы в папке services и api/api.py.
        
        Args:
            services_dir: Путь к папке services
            api_dir: Путь к папке api
            
        Returns:
            Список путей к .py файлам сервисов
        """
        service_files = []
        
        # Ищем сервисы в папке services
        if os.path.exists(services_dir):
            for root, dirs, files in os.walk(services_dir):
                # Пропускаем служебные директории
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                # Пропускаем файлы в __pycache__ папках
                if '__pycache__' in root:
                    continue
                
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        # Пропускаем служебные файлы, которые не являются сервисами
                        if file == 'init_settings.py':
                            continue
                        # Клиент удалённого стола — только вручную (окно только при запуске клиента)
                        if file.endswith('_client.py'):
                            continue
                        filepath = os.path.join(root, file)
                        # Сервер RD в подпапке remote_desktop не грузим (есть отдельный сервис remote_desktop_server)
                        if file.endswith('_server.py'):
                            fp = Path(filepath)
                            if fp.parent.name != fp.stem:
                                continue
                        service_files.append(filepath)
        
        # НЕ добавляем api/api.py, так как API теперь интегрирован в web.py
        # api/api.py больше не нужен как отдельный сервис
        
        return service_files
    
    def load_service(self, filepath: str) -> bool:
        """
        Загружает и запускает сервис из файла.
        
        Args:
            filepath: Путь к файлу сервиса
            
        Returns:
            True если успешно загружен
        """
        try:
            # Получаем имя сервиса из пути
            # Для файлов в подпапках (например, services/web/web.py) берем имя папки
            filepath_obj = Path(filepath)
            
            # Пропускаем служебные файлы, которые не являются сервисами
            if filepath_obj.name == "init_settings.py":
                print(f"Skipping utility file: {filepath}", flush=True)
                return False
            
            if filepath_obj.parent.name == "services" or filepath_obj.parent.parent.name == "services":
                # Специальный случай: docker_service.py в windows_docker
                if filepath_obj.name == "docker_service.py" and filepath_obj.parent.name == "windows_docker":
                    service_name = "docker_service"
                # Если файл в services/web/, берем имя папки
                elif filepath_obj.parent.name != "services":
                    service_name = filepath_obj.parent.name  # services/web/web.py -> web
                else:
                    service_name = filepath_obj.stem  # services/scanner.py -> scanner
            else:
                service_name = os.path.splitext(os.path.basename(filepath))[0]
            
            # Проверяем статус сервиса
            if not self.manager.is_service_enabled(service_name):
                print(f"Service {service_name} is disabled. Skipping...", flush=True)
                return False
            
            # Получаем параметры сервиса
            params = self.manager.get_service_parameters(service_name)
            
            # Обновляем зависимости на основе анализа импортов
            self.manager.update_service_dependencies_from_file(service_name, filepath)
            
            # Получаем уникальное имя модуля из пути
            # Для api/api.py используем 'api_service' чтобы избежать конфликта с пакетом api
            if 'api' in filepath and filepath.endswith('api.py'):
                module_name = 'api_service'
            else:
                module_name = service_name
            
            # Загружаем модуль
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                print(f"Failed to load spec for {filepath}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Ищем функцию run или main для запуска
            run_func = None
            if hasattr(module, 'run'):
                run_func = module.run
            elif hasattr(module, 'main'):
                run_func = module.main
            elif hasattr(module, '__call__'):
                run_func = module
            
            if run_func:
                def service_wrapper():
                    try:
                        print(f"Starting service: {filepath}", flush=True)
                        sys.stdout.flush()
                        sys.stderr.flush()
                        run_func()
                    except Exception as e:
                        print(f"Error in service {filepath}: {str(e)}", flush=True)
                        import traceback
                        traceback.print_exc()
                        sys.stdout.flush()
                        sys.stderr.flush()
                
                thread = threading.Thread(target=service_wrapper, daemon=False)
                thread.start()
                self.threads.append(thread)
                
                self.services.append({
                    "filepath": filepath,
                    "module": module,
                    "thread": thread,
                    "status": "running",
                    "service_name": service_name
                })
                
                print(f"Service {filepath} started", flush=True)
                sys.stdout.flush()
                return True
            else:
                print(f"No run/main function found in {filepath}")
                return False
                
        except Exception as e:
            print(f"Error loading service {filepath}: {str(e)}")
            return False
    
    def run_all_services(self):
        """Запускает все найденные сервисы."""
        self.running = True
        print("Discovering services...", flush=True)
        service_files = self.find_services()
        
        if not service_files:
            print("No services found. Waiting indefinitely...", flush=True)
            # Если сервисов нет, просто ждем бесконечно, чтобы контейнер не падал
            try:
                while True:
                    time.sleep(60)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                pass
            return
        
        # Сохраняем service_files как атрибут для использования при перезапуске
        self.service_files = service_files
        
        print(f"Found {len(service_files)} service(s)", flush=True)
        for sf in service_files:
            print(f"  - {sf}", flush=True)
        
        self.running = True
        
        # Загружаем и запускаем каждый сервис
        for service_file in service_files:
            self.load_service(service_file)
            time.sleep(0.5)  # Небольшая задержка между запусками
        
        print(f"Started {len(self.services)} service(s)", flush=True)
        
        if len(self.services) == 0:
            print("No services started. Waiting indefinitely...", flush=True)
            try:
                while True:
                    time.sleep(60)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                pass
            return
        
        # Даем сервисам время запуститься перед первой проверкой
        print("Waiting 5 seconds for services to initialize...", flush=True)
        time.sleep(5)
        
        # Проверяем, что сервисы действительно запустились
        alive_threads = [t for t in self.threads if t.is_alive()]
        print(f"After initialization: {len(alive_threads)}/{len(self.threads)} threads alive", flush=True)
        
        if len(alive_threads) == 0:
            print("ERROR: All service threads died immediately after start!", flush=True)
            print("Waiting indefinitely to prevent container exit...", flush=True)
            try:
                while True:
                    time.sleep(60)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                pass
            return
        
        # Переменная для отслеживания времени последней проверки сервисов
        last_service_check = time.time()
        service_check_interval = 60  # Проверяем каждую минуту
        
        # Ждем завершения всех потоков
        print("Entering main service loop...", flush=True)
        try:
            while self.running:
                # Проверяем новые сервисы каждую минуту
                current_time = time.time()
                if current_time - last_service_check >= service_check_interval:
                    print("Checking for new services...", flush=True)
                    self.manager.refresh_services()
                    
                    # Проверяем, есть ли новые сервисы, которые нужно запустить
                    discovered_services = self.manager.discover_services()
                    current_service_names = {s.get("service_name") for s in self.services if s.get("service_name")}
                    
                    for service_name in discovered_services:
                        if service_name not in current_service_names:
                            # Ищем файл сервиса
                            service_file = None
                            services_dir = Path("services")
                            if services_dir.exists():
                                for item in services_dir.iterdir():
                                    if item.is_file() and item.suffix == '.py' and item.stem == service_name:
                                        service_file = str(item)
                                        break
                                    elif item.is_dir() and item.name == service_name:
                                        main_file = item / "main.py"
                                        name_file = item / f"{item.name}.py"
                                        if main_file.exists():
                                            service_file = str(main_file)
                                            break
                                        if name_file.exists():
                                            service_file = str(name_file)
                                            break
                            
                            if service_file and self.manager.is_service_enabled(service_name):
                                print(f"Found new service: {service_name}. Starting...", flush=True)
                                self.load_service(service_file)
                    
                    last_service_check = current_time
                
                # Проверяем, что потоки еще живы
                alive_threads = [t for t in self.threads if t.is_alive()]
                dead_threads = [t for t in self.threads if not t.is_alive()]
                
                if dead_threads:
                    print(f"Warning: {len(dead_threads)} service thread(s) stopped", flush=True)
                    for i, thread in enumerate(dead_threads):
                        service_info = self.services[i] if i < len(self.services) else None
                        service_name = service_info.get("service_name", "unknown") if service_info else "unknown"
                        print(f"  - Thread for service '{service_name}' is dead", flush=True)
                
                if not alive_threads and len(self.services) > 0:
                    print("All services stopped unexpectedly", flush=True)
                    sys.stdout.flush()
                    
                    # Проверяем, есть ли сервисы со статусом SLEEP
                    # Если все сервисы в SLEEP, не перезапускаем
                    all_sleep = True
                    for service_info in self.services:
                        service_name = service_info.get("service_name")
                        if service_name:
                            service_status = self.manager.get_service(service_name).get("status")
                            if service_status != "SLEEP":
                                all_sleep = False
                                break
                    
                    if all_sleep:
                        print("All services are in SLEEP status. Not restarting.", flush=True)
                        sys.stdout.flush()
                        break
                    
                    # Перезапускаем сервисы если они упали (только те, что не в SLEEP)
                    print("Restarting services...", flush=True)
                    sys.stdout.flush()
                    self.threads = []
                    self.services = []
                    # Используем сохраненный список service_files
                    for service_file in getattr(self, 'service_files', []):
                        self.load_service(service_file)
                        time.sleep(0.5)
                    if not self.threads:
                        print("Failed to restart services. Exiting.", flush=True)
                        sys.stdout.flush()
                        break
                elif len(alive_threads) > 0:
                    # Сервисы работают, просто ждем
                    print(f"Services running: {len(alive_threads)}/{len(self.threads)} threads alive", flush=True)
                else:
                    # Нет запущенных сервисов и нет сервисов для запуска
                    if len(self.services) == 0:
                        print("No services to run. Waiting indefinitely...", flush=True)
                        sys.stdout.flush()
                        # Ждем бесконечно, чтобы контейнер не падал
                        try:
                            while True:
                                time.sleep(60)
                                sys.stdout.flush()
                        except KeyboardInterrupt:
                            break
                        break
                    else:
                        # Есть сервисы, но все потоки мертвы - это проблема
                        print(f"ERROR: All {len(self.services)} service(s) stopped but services list is not empty!", flush=True)
                        print("This should not happen. Waiting indefinitely to prevent container exit...", flush=True)
                        try:
                            while True:
                                time.sleep(60)
                                sys.stdout.flush()
                        except KeyboardInterrupt:
                            break
                        break
                # Проверяем состояние сервисов каждую минуту
                time.sleep(60)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print("\nStopping services...", flush=True)
            sys.stdout.flush()
            self.stop_all_services()
        except Exception as e:
            print(f"Error in service runner: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
    
    def stop_all_services(self):
        """Останавливает все сервисы."""
        self.running = False
        print("Waiting for services to stop...")
        
        # Ждем завершения потоков
        for thread in self.threads:
            thread.join(timeout=5)
        
        print("All services stopped")


def run_services():
    """Запускает все сервисы из папки services."""
    try:
        runner = ServiceRunner()
        runner.run_all_services()
    except Exception as e:
        print(f"Fatal error in run_services: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        # Не завершаем работу, а ждем бесконечно чтобы контейнер не падал
        print("Waiting indefinitely after fatal error to prevent container exit...", flush=True)
        try:
            while True:
                time.sleep(60)
                sys.stdout.flush()
        except KeyboardInterrupt:
            pass
        raise


if __name__ == '__main__':
    run_services()

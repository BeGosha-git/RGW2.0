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

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

if 'PYTHONUNBUFFERED' not in os.environ:
    os.environ['PYTHONUNBUFFERED'] = '1'

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

venv_path = Path("venv").resolve()
if venv_path.exists():
    venv_python = venv_path / "bin" / "python3"
    if not venv_python.exists():
        venv_python = venv_path / "bin" / "python"
    
    if venv_python.exists():
        venv_python_resolved = venv_python.resolve()
        current_python = Path(sys.executable).resolve()
        
        try:
            venv_same = venv_python_resolved.samefile(current_python)
        except (OSError, ValueError):
            venv_same = (str(venv_python_resolved) == str(current_python))
        
        if not venv_same:
            print(f"[ServiceRunner] WARNING: Not using venv Python! Current: {current_python}, Expected: {venv_python_resolved}", flush=True)
            print(f"[ServiceRunner] Services may fail due to missing dependencies in system Python", flush=True)
        else:
            print(f"[ServiceRunner] Using venv Python: {venv_python_resolved}", flush=True)
        
        if 'VIRTUAL_ENV' not in os.environ:
            os.environ['VIRTUAL_ENV'] = str(venv_path)
        
        venv_lib = venv_path / 'lib'
        venv_lib64 = venv_path / 'lib64'
        
        ld_library_path = os.environ.get('LD_LIBRARY_PATH', '')
        paths_to_add = []
        
        if venv_lib.exists() and str(venv_lib) not in ld_library_path:
            paths_to_add.append(str(venv_lib))
        
        if venv_lib64.exists() and str(venv_lib64) not in ld_library_path:
            paths_to_add.append(str(venv_lib64))
        
        if paths_to_add:
            new_ld_path = ':'.join(paths_to_add)
            os.environ['LD_LIBRARY_PATH'] = f"{new_ld_path}:{ld_library_path}" if ld_library_path else new_ld_path
            print(f"[ServiceRunner] Added venv lib paths to LD_LIBRARY_PATH: {paths_to_add}", flush=True)


class ServiceRunner:
    """Класс для запуска сервисов из папки services."""
    
    def __init__(self):
        """Инициализация запуска сервисов."""
        self.services: List[Dict] = []
        self.threads: List[threading.Thread] = []
        self.service_files: List[str] = []
        self.running = False
        self.manager = services_manager.get_services_manager()
    
    def find_services(self, services_dir: str = "services", api_dir: str = "api") -> List[str]:
        """
        Находит все .py файлы в папке services.
        
        Args:
            services_dir: Путь к папке services
            api_dir: Путь к папке api (не используется, оставлено для обратной совместимости)
            
        Returns:
            Список путей к .py файлам сервисов
        """
        service_files = []
        
        if os.path.exists(services_dir):
            for root, dirs, files in os.walk(services_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                if '__pycache__' in root:
                    continue
                
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        if file == 'init_settings.py':
                            continue
                        if file.endswith('_client.py'):
                            continue
                        if 'unitree_sdk2py' in root:
                            continue
                        if file == 'unitree_legged_const.py':
                            continue
                        if file == 'dependencies.py':
                            continue
                        if file == 'unitree_motor_control.py' and 'unitree_motor_control' in root:
                            continue
                        if file == 'protocol.py':
                            continue
                        if file == 'example_service.py':
                            continue
                        filepath = os.path.join(root, file)
                        service_files.append(filepath)
        
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
            filepath_obj = Path(filepath)
            
            if filepath_obj.name == "init_settings.py":
                print(f"Skipping utility file: {filepath}", flush=True)
                return False
            
            if 'unitree_sdk2py' in str(filepath_obj):
                return False
            
            if filepath_obj.name == 'unitree_legged_const.py':
                return False
            
            if filepath_obj.name == 'dependencies.py':
                return False
            
            if filepath_obj.name == 'unitree_motor_control.py' and 'unitree_motor_control' in str(filepath_obj.parent):
                return False
            
            if filepath_obj.name == 'protocol.py':
                return False
            
            if filepath_obj.name == 'example_service.py':
                return False
            
            if filepath_obj.parent.name == "services" or filepath_obj.parent.parent.name == "services":
                if filepath_obj.name == "docker_service.py" and filepath_obj.parent.name == "windows_docker":
                    service_name = "docker_service"
                elif filepath_obj.parent.name != "services":
                    service_name = filepath_obj.parent.name
                else:
                    service_name = filepath_obj.stem
            else:
                service_name = os.path.splitext(os.path.basename(filepath))[0]
            
            if not self.manager.is_service_enabled(service_name):
                print(f"Service {service_name} is disabled. Skipping...", flush=True)
                service_info = self.manager.get_service(service_name)
                current_status = service_info.get("status", "OFF")
                if current_status != "OFF":
                    self.manager.update_service_status(service_name, "OFF")
                return False
            
            params = self.manager.get_service_parameters(service_name)
            self.manager.update_service_dependencies_from_file(service_name, filepath)
            
            service_info = self.manager.get_service(service_name)
            enabled = service_info.get("parameters", {}).get("enabled", True)
            current_status = service_info.get("status", "OFF")
            expected_status = "ON" if enabled else "OFF"
            
            if current_status != expected_status:
                self.manager.update_service_status(service_name, expected_status)
                print(f"[ServiceRunner] Synchronized status for {service_name}: {current_status} -> {expected_status} (enabled={enabled})", flush=True)
            
            module_name = service_name
            
            print(f"[ServiceRunner] Loading service {service_name} from {filepath}", flush=True)
            print(f"[ServiceRunner] Using Python: {sys.executable}", flush=True)
            print(f"[ServiceRunner] VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', 'not set')}", flush=True)
            
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                print(f"Failed to load spec for {filepath}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
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
                        print(f"[ServiceRunner] Starting service: {filepath}", flush=True)
                        print(f"[ServiceRunner] Service Python: {sys.executable}", flush=True)
                        print(f"[ServiceRunner] Service VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', 'not set')}", flush=True)
                        sys.stdout.flush()
                        sys.stderr.flush()
                        run_func()
                    except Exception as e:
                        print(f"[ServiceRunner] Error in service {filepath}: {str(e)}", flush=True)
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
            try:
                while True:
                    time.sleep(60)
                    sys.stdout.flush()
            except KeyboardInterrupt:
                pass
            return
        
        self.service_files = service_files
        
        print(f"Found {len(service_files)} service(s)", flush=True)
        for sf in service_files:
            print(f"  - {sf}", flush=True)
        
        self.running = True
        
        for service_file in service_files:
            self.load_service(service_file)
            time.sleep(0.5)
        
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
        
        print("Waiting 5 seconds for services to initialize...", flush=True)
        time.sleep(5)
        
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
        
        last_service_check = time.time()
        service_check_interval = 60
        last_motor_check = time.time()
        motor_check_interval = 5
        
        print("Entering main service loop...", flush=True)
        try:
            while self.running:
                current_time = time.time()
                
                if current_time - last_motor_check >= motor_check_interval:
                    try:
                        motor_service_info = self.manager.get_service("unitree_motor_control")
                        motor_status = motor_service_info.get("status", "OFF") if motor_service_info else "OFF"
                        motor_enabled = motor_service_info.get("parameters", {}).get("enabled", True) if motor_service_info else True
                        
                        if motor_status == "OFF":
                            motor_was_loaded = False
                            motor_thread_alive = False
                            
                            for i, service_info in enumerate(self.services):
                                if service_info.get("service_name") == "unitree_motor_control":
                                    motor_was_loaded = True
                                    if i < len(self.threads):
                                        motor_thread_alive = self.threads[i].is_alive()
                                    break
                            
                            if motor_was_loaded and not motor_thread_alive:
                                if motor_enabled:
                                    print("Motor service was running but stopped unexpectedly. Shutting down main.py...", flush=True)
                                    sys.stdout.flush()
                                    sys.stderr.flush()
                                    self.running = False
                                    break
                                else:
                                    print("Motor service stopped and is disabled via API. This is expected.", flush=True)
                            elif not motor_was_loaded and not motor_enabled:
                                pass
                    except Exception as e:
                        print(f"Warning: Could not check motor service status: {e}", flush=True)
                    
                    last_motor_check = current_time
                
                if current_time - last_service_check >= service_check_interval:
                    print("Checking for new services...", flush=True)
                    self.manager.refresh_services()
                    
                    discovered_services = self.manager.discover_services()
                    current_service_names = {s.get("service_name") for s in self.services if s.get("service_name")}
                    
                    for service_name in discovered_services:
                        if service_name not in current_service_names:
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
                    
                    print("Restarting services...", flush=True)
                    sys.stdout.flush()
                    self.threads = []
                    self.services = []
                    for service_file in getattr(self, 'service_files', []):
                        self.load_service(service_file)
                        time.sleep(0.5)
                    if not self.threads:
                        print("Failed to restart services. Exiting.", flush=True)
                        sys.stdout.flush()
                        break
                elif len(alive_threads) > 0:
                    print(f"Services running: {len(alive_threads)}/{len(self.threads)} threads alive", flush=True)
                else:
                    if len(self.services) == 0:
                        print("No services to run. Waiting indefinitely...", flush=True)
                        sys.stdout.flush()
                        try:
                            while True:
                                time.sleep(60)
                                sys.stdout.flush()
                        except KeyboardInterrupt:
                            break
                        break
                    else:
                        print(f"ERROR: All {len(self.services)} service(s) stopped but services list is not empty!", flush=True)
                        print("This should not happen. Waiting indefinitely to prevent container exit...", flush=True)
                        try:
                            while True:
                                time.sleep(60)
                                sys.stdout.flush()
                        except KeyboardInterrupt:
                            break
                        break
                time.sleep(60)
                sys.stdout.flush()
        except KeyboardInterrupt:
            print("\nStopping services...", flush=True)
            sys.stdout.flush()
            self.stop_all_services()
        except SystemExit:
            raise
        except Exception as e:
            print(f"Error in service runner: {str(e)}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
        
        if not self.running:
            print("Service runner stopped. Stopping all services...", flush=True)
            sys.stdout.flush()
            sys.stderr.flush()
            self.stop_all_services()
            print("Exiting...", flush=True)
            sys.exit(0)
    
    def stop_all_services(self):
        """Останавливает все сервисы."""
        self.running = False
        print("Waiting for services to stop...")
        
        try:
            motor_service_status = self.manager.get_service("unitree_motor_control")
            if motor_service_status.get("status") == "ON":
                print("CRITICAL: Motor service is active. Skipping forced shutdown for safety.", flush=True)
                print("Motor service will continue running. Use API to shutdown (requires 3 consecutive OFF requests).", flush=True)
                services_to_stop = [s for s in self.services if s.get("service_name") != "unitree_motor_control"]
                threads_to_stop = [t for i, t in enumerate(self.threads) if i < len(self.services) and self.services[i].get("service_name") != "unitree_motor_control"]
                
                for thread in threads_to_stop:
                    thread.join(timeout=5)
                print(f"Stopped {len(threads_to_stop)} service(s) (motor service excluded)", flush=True)
                return
        except Exception as e:
            print(f"Warning: Could not check motor service status: {e}", flush=True)
        
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

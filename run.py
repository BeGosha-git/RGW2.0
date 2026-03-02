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
            pass
        
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
        Находит все .py файлы в папке services и api.
        
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
        
        # Ищем сервисы в папке api
        if os.path.exists(api_dir):
            for root, dirs, files in os.walk(api_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                if '__pycache__' in root:
                    continue
                
                for file in files:
                    if file.endswith('.py') and file != '__init__.py':
                        if file.endswith('_client.py'):
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
            elif filepath_obj.parent.name == "api":
                service_name = "api"
            else:
                service_name = os.path.splitext(os.path.basename(filepath))[0]
            
            if not self.manager.is_service_enabled(service_name):
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
            
            module_name = service_name
            
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
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
                        run_func()
                    except Exception:
                        pass
                
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
                
                return True
            else:
                return False
                
        except Exception:
            return False
    
    def run_all_services(self):
        """Запускает все найденные сервисы."""
        self.running = True
        print("Discovering services...", flush=True)
        service_files = self.find_services()
        
        if not service_files:
            print("No service files found. Waiting...", flush=True)
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
            return
        
        self.service_files = service_files
        self.running = True
        
        print(f"Found {len(service_files)} service file(s), starting...", flush=True)
        for service_file in service_files:
            self.load_service(service_file)
            time.sleep(0.5)
        
        if len(self.services) == 0:
            print("No services started (all disabled?). Waiting...", flush=True)
            try:
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                pass
            return
        
        time.sleep(5)
        
        alive_threads = [t for t in self.threads if t.is_alive()]
        
        if len(alive_threads) == 0:
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
                                    self.running = False
                                    break
                            elif not motor_was_loaded and not motor_enabled:
                                pass
                    except Exception:
                        pass
                    
                    last_motor_check = current_time
                
                if current_time - last_service_check >= service_check_interval:
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
                                self.load_service(service_file)
                    
                    last_service_check = current_time
                
                alive_threads = [t for t in self.threads if t.is_alive()]
                dead_threads = [t for t in self.threads if not t.is_alive()]
                
                if not alive_threads and len(self.services) > 0:
                    all_sleep = True
                    for service_info in self.services:
                        service_name = service_info.get("service_name")
                        if service_name:
                            service_status = self.manager.get_service(service_name).get("status")
                            if service_status != "SLEEP":
                                all_sleep = False
                                break
                    
                    if all_sleep:
                        break
                    
                    self.threads = []
                    self.services = []
                    for service_file in getattr(self, 'service_files', []):
                        self.load_service(service_file)
                        time.sleep(0.5)
                    if not self.threads:
                        break
                elif len(self.services) == 0:
                    try:
                        while True:
                            time.sleep(60)
                    except KeyboardInterrupt:
                        break
                    break
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop_all_services()
        except SystemExit:
            raise
        except Exception:
            pass
        
        if not self.running:
            self.stop_all_services()
            self.cleanup_ports()
            sys.exit(0)
    
    def stop_all_services(self):
        """Останавливает все сервисы."""
        self.running = False
        
        try:
            motor_service_status = self.manager.get_service("unitree_motor_control")
            if motor_service_status.get("status") == "ON":
                threads_to_stop = [t for i, t in enumerate(self.threads) if i < len(self.services) and self.services[i].get("service_name") != "unitree_motor_control"]
                for thread in threads_to_stop:
                    thread.join(timeout=5)
                return
        except Exception:
            pass
        
        for thread in self.threads:
            thread.join(timeout=5)
        
        self.cleanup_ports()
    
    def cleanup_ports(self):
        """Освобождает порты, используемые сервисами."""
        try:
            import subprocess
            
            ports_to_clean = set()
            
            web_service = self.manager.get_service("web")
            if web_service:
                web_params = self.manager.get_service_parameters("web")
                web_port = web_params.get("port", 8080)
                ports_to_clean.add(web_port)
            
            api_service = self.manager.get_service("api")
            if api_service:
                api_params = self.manager.get_service_parameters("api")
                api_port = api_params.get("port", 5000)
                ports_to_clean.add(api_port)
            
            scanner_service = self.manager.get_service("scanner_service")
            if scanner_service:
                scanner_params = self.manager.get_service_parameters("scanner_service")
                scanner_port = scanner_params.get("port", 8080)
                ports_to_clean.add(scanner_port)
            
            for port in ports_to_clean:
                try:
                    subprocess.run(["fuser", "-k", f"{port}/tcp"], 
                                 capture_output=True, timeout=2, stderr=subprocess.DEVNULL)
                except Exception:
                    try:
                        result = subprocess.run(["lsof", "-ti", f":{port}"], 
                                               capture_output=True, timeout=2, text=True)
                        if result.returncode == 0 and result.stdout.strip():
                            pids = result.stdout.strip().split('\n')
                            for pid in pids:
                                try:
                                    subprocess.run(["kill", "-9", pid], 
                                                 capture_output=True, timeout=1, stderr=subprocess.DEVNULL)
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            pass


def run_services():
    """Запускает все сервисы из папки services."""
        print("TESTTESTTESTTESTTESTTESTTESTTEST")
    try:
        runner = ServiceRunner()
        runner.run_all_services()
    except Exception:
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass
        raise


if __name__ == '__main__':
    run_services()

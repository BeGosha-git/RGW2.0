"""
API модуль для передачи и приёма данных с других роботов.
"""
import network
import requests
from typing import Dict, Any, Optional, List


def _get_default_api_port() -> int:
    """Получает дефолтный порт API из конфигурации."""
    try:
        import services_manager
        return services_manager.get_api_port()
    except Exception:
        return 5000


class NetworkAPI:
    """API для сетевого взаимодействия с другими роботами."""
    
    def __init__(self):
        """Инициализация сетевого API."""
        # Используем таймаут 3 секунды для быстрых проверок статуса и health
        self.client = network.NetworkClient(timeout=3)
        # Отдельный клиент с увеличенным таймаутом для выполнения команд (5 минут)
        self.command_client = network.NetworkClient(timeout=60)
    
    def get_actual_version(self, robot_ips: List[str] = None, port: Optional[int] = None) -> Dict[str, Any]:
        """
        Получает самую актуальную версию от других роботов.
        
        Args:
            robot_ips: Список IP адресов роботов для проверки (если None, ищет автоматически)
            port: Порт для подключения (None = из конфигурации, по умолчанию 5000)
            
        Returns:
            Информация о самой актуальной версии и IP откуда её получить
        """
        try:
            if port is None:
                port = _get_default_api_port()
            
            if robot_ips is None:
                # Автоматический поиск роботов в сети
                robot_ips = network.find_robots_in_network(port=port)
            
            latest_version = None
            latest_version_info = None
            source_ip = None
            
            for ip in robot_ips:
                try:
                    base_url = f"http://{ip}:{port}"
                    robot_info = self.client.get_robot_info(base_url)
                    
                    if robot_info and robot_info.get("success"):
                        version_data = robot_info.get("version", {})
                        version_str = version_data.get("version", "0.00.00")
                        
                        # Сравниваем версии
                        if latest_version is None or self._compare_versions(version_str, latest_version) > 0:
                            latest_version = version_str
                            latest_version_info = version_data
                            source_ip = ip
                except Exception as e:
                    print(f"Error checking robot {ip}: {str(e)}")
                    continue
            
            if latest_version_info and source_ip:
                return {
                    "success": True,
                    "version": latest_version_info,
                    "source_ip": source_ip,
                    "source_url": f"http://{source_ip}:{port}"
                }
            else:
                return {
                    "success": False,
                    "message": "No robots found or no version information available"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting actual version: {str(e)}"
            }
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        Сравнивает две версии.
        
        Args:
            v1: Первая версия (например, "1.00.01")
            v2: Вторая версия
            
        Returns:
            1 если v1 > v2, -1 если v1 < v2, 0 если равны
        """
        try:
            parts1 = [int(x) for x in v1.split('.')]
            parts2 = [int(x) for x in v2.split('.')]
            
            for i in range(max(len(parts1), len(parts2))):
                p1 = parts1[i] if i < len(parts1) else 0
                p2 = parts2[i] if i < len(parts2) else 0
                
                if p1 > p2:
                    return 1
                elif p1 < p2:
                    return -1
            
            return 0
        except Exception:
            return 0
    
    def send_data(self, target_ip: str, endpoint: str, data: Dict, port: Optional[int] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Отправляет данные другому роботу.
        
        Args:
            target_ip: IP адрес целевого робота
            endpoint: Конечная точка API (например, '/api/robot/execute', '/status', '/health')
            data: Данные для отправки
            port: Порт для подключения (None = из конфигурации, по умолчанию 5000)
            timeout: Таймаут в секундах (None = использовать дефолтный, для команд обновления рекомендуется 300)
        
        Returns:
            Результат отправки с полной структурой ответа
        """
        try:
            if port is None:
                port = _get_default_api_port()
            base_url = f"http://{target_ip}:{port}"
            
            # Нормализуем endpoint: убираем начальный слэш и проверяем формат
            endpoint = endpoint.lstrip('/')
            
            # Определяем, нужен ли увеличенный таймаут (для команд выполнения)
            use_long_timeout = endpoint in ['robot/execute', 'api/robot/execute'] or (timeout is not None and timeout > 30)
            
            # Выбираем клиент в зависимости от типа запроса
            if use_long_timeout or timeout:
                # Для команд выполнения используем клиент с увеличенным таймаутом
                client_to_use = self.command_client if timeout is None else network.NetworkClient(timeout=timeout)
            else:
                # Для быстрых запросов используем обычный клиент
                client_to_use = self.client
            
            # Для GET endpoints используем get_from_robot
            if endpoint in ['status', 'health'] or endpoint == 'api/status':
                if endpoint == 'api/status':
                    endpoint = 'status'
                response = client_to_use.get_from_robot(base_url, endpoint)
            else:
                # Для POST endpoints используем send_data_to_robot
                # Убираем 'api/' префикс если есть, так как send_data_to_robot добавляет /api/
                if endpoint.startswith('api/'):
                    clean_endpoint = endpoint[4:]  # Убираем 'api/'
                else:
                    clean_endpoint = endpoint
                response = client_to_use.send_data_to_robot(base_url, clean_endpoint, data)
            
            # Проверяем ответ более надежно
            if response is None:
                return {
                    "success": False,
                    "message": f"No response from {target_ip}",
                    "target_ip": target_ip,
                    "endpoint": endpoint
                }
            
            # Если ответ уже содержит success, возвращаем его как есть
            if isinstance(response, dict) and "success" in response:
                return {
                    "success": True,
                    "response": response
                }
            
            # Иначе оборачиваем в стандартный формат
            return {
                "success": True,
                "response": response
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": f"Timeout connecting to {target_ip}:{port}",
                "target_ip": target_ip,
                "endpoint": endpoint
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": f"Connection error to {target_ip}:{port}",
                "target_ip": target_ip,
                "endpoint": endpoint
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error sending data: {str(e)}",
                "target_ip": target_ip,
                "endpoint": endpoint
            }
    
    def receive_data(self, source_ip: str, endpoint: str, port: Optional[int] = None) -> Dict[str, Any]:
        """
        Получает данные от другого робота.
        
        Args:
            source_ip: IP адрес робота-источника
            endpoint: Конечная точка API
            port: Порт для подключения (None = из конфигурации, по умолчанию 5000)
            
        Returns:
            Полученные данные
        """
        try:
            if port is None:
                port = _get_default_api_port()
            base_url = f"http://{source_ip}:{port}"
            url = f"{base_url}/api/{endpoint}"
            response = self.client.get(url)
            
            if response:
                return {
                    "success": True,
                    "data": response
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to receive data from {source_ip}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error receiving data: {str(e)}"
            }
    
    def download_file_from_robot(self, source_ip: str, filepath: str, 
                                  local_path: str, port: Optional[int] = None) -> Dict[str, Any]:
        """
        Скачивает файл с другого робота.
        
        Args:
            source_ip: IP адрес робота-источника
            filepath: Путь к файлу на роботе
            local_path: Локальный путь для сохранения
            port: Порт для подключения (None = из конфигурации, по умолчанию 5000)
            
        Returns:
            Результат операции
        """
        try:
            if port is None:
                port = _get_default_api_port()
            url = f"http://{source_ip}:{port}/api/files/download?path={filepath}"
            success = self.client.download_file(url, local_path)
            
            if success:
                return {
                    "success": True,
                    "message": f"File downloaded successfully to {local_path}",
                    "local_path": local_path
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to download file from {source_ip}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error downloading file: {str(e)}"
            }
    
    def find_robots(self, port: Optional[int] = None) -> Dict[str, Any]:
        """
        Ищет роботов в сети.
        
        Args:
            port: Порт для подключения к роботам (None = из конфигурации веб-сервера, по умолчанию 8080)
        
        Returns:
            Список найденных роботов
        """
        try:
            if port is None:
                try:
                    import services_manager
                    port = services_manager.get_web_port()
                except Exception:
                    port = 8080
            robots = network.find_robots_in_network(port=port)
            robot_info_list = []
            
            for ip in robots:
                try:
                    base_url = f"http://{ip}:{port}"
                    info = self.client.get_robot_info(base_url)
                    if info:
                        robot_info_list.append({
                            "ip": ip,
                            "info": info
                        })
                except Exception:
                    robot_info_list.append({
                        "ip": ip,
                        "info": None
                    })
            
            return {
                "success": True,
                "robots": robot_info_list,
                "count": len(robot_info_list)
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error finding robots: {str(e)}"
            }

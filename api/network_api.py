"""
API модуль для передачи и приёма данных с других роботов.
"""
import network
from typing import Dict, Any, Optional, List


class NetworkAPI:
    """API для сетевого взаимодействия с другими роботами."""
    
    def __init__(self):
        """Инициализация сетевого API."""
        # Используем таймаут 3 секунды для быстрых проверок статуса и health
        self.client = network.NetworkClient(timeout=3)
    
    def get_actual_version(self, robot_ips: List[str] = None) -> Dict[str, Any]:
        """
        Получает самую актуальную версию от других роботов.
        
        Args:
            robot_ips: Список IP адресов роботов для проверки (если None, ищет автоматически)
            
        Returns:
            Информация о самой актуальной версии и IP откуда её получить
        """
        try:
            if robot_ips is None:
                # Автоматический поиск роботов в сети
                robot_ips = network.find_robots_in_network()
            
            latest_version = None
            latest_version_info = None
            source_ip = None
            
            for ip in robot_ips:
                try:
                    base_url = f"http://{ip}"
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
                    "source_url": f"http://{source_ip}"
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
    
    def send_data(self, target_ip: str, endpoint: str, data: Dict) -> Dict[str, Any]:
        """
        Отправляет данные другому роботу.
        
        Args:
            target_ip: IP адрес целевого робота
            endpoint: Конечная точка API (например, '/status' или '/health')
            data: Данные для отправки
            
        Returns:
            Результат отправки
        """
        try:
            base_url = f"http://{target_ip}"
            # Для GET endpoints используем get_from_robot
            if endpoint in ['/status', 'status', '/health', 'health']:
                response = self.client.get_from_robot(base_url, endpoint)
            else:
                # Для POST endpoints используем send_data_to_robot
                # Убираем /api/ из endpoint если есть, так как send_data_to_robot добавляет его
                clean_endpoint = endpoint.replace('/api/', '') if endpoint.startswith('/api/') else endpoint
                response = self.client.send_data_to_robot(base_url, clean_endpoint, data)
            
            if response:
                return {
                    "success": True,
                    "response": response
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to get data from {target_ip}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting data: {str(e)}"
            }
    
    def receive_data(self, source_ip: str, endpoint: str) -> Dict[str, Any]:
        """
        Получает данные от другого робота.
        
        Args:
            source_ip: IP адрес робота-источника
            endpoint: Конечная точка API
            
        Returns:
            Полученные данные
        """
        try:
            base_url = f"http://{source_ip}"
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
                                  local_path: str) -> Dict[str, Any]:
        """
        Скачивает файл с другого робота.
        
        Args:
            source_ip: IP адрес робота-источника
            filepath: Путь к файлу на роботе
            local_path: Локальный путь для сохранения
            
        Returns:
            Результат операции
        """
        try:
            url = f"http://{source_ip}/api/files/download?path={filepath}"
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
    
    def find_robots(self) -> Dict[str, Any]:
        """
        Ищет роботов в сети.
        
        Returns:
            Список найденных роботов
        """
        try:
            robots = network.find_robots_in_network()
            robot_info_list = []
            
            for ip in robots:
                try:
                    base_url = f"http://{ip}"
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

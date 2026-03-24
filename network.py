"""
Модуль для связи с другими роботами и серверами через сеть.
"""
import threading
import requests
import socket
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin
import concurrent.futures
from utils.logger import get_logger

logger = get_logger(__name__)


class NetworkClient:
    """Класс для сетевого взаимодействия с другими роботами и серверами."""
    
    def __init__(self, timeout: int = 5):
        """
        Инициализация сетевого клиента.
        
        Args:
            timeout: Таймаут запросов в секундах (по умолчанию 5 для быстрых ответов)
        """
        self.timeout = timeout
        # Session не thread-safe: при параллельных /api/network/send из разных потоков веб-сервера
        # нужна отдельная Session на поток, иначе исходящие запросы выполняются по сути последовательно.
        self._tls = threading.local()

    def _session(self) -> requests.Session:
        s = getattr(self._tls, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                'Content-Type': 'application/json',
                'User-Agent': 'RGW-Robot/2.0'
            })
            self._tls.session = s
        return s
    
    def get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Выполняет GET запрос.
        
        Args:
            url: URL для запроса
            params: Параметры запроса
            
        Returns:
            Ответ в виде словаря или None при ошибке
        """
        try:
            response = self._session().get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.debug(f"GET request error to {url}: {e}")
            return None
    
    def post(self, url: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Выполняет POST запрос.
        
        Args:
            url: URL для запроса
            data: Данные для отправки
            
        Returns:
            Ответ в виде словаря или None при ошибке
        """
        try:
            response = self._session().post(
                url, 
                json=data, 
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.debug(f"POST request error to {url}: {e}")
            return None
    
    def put(self, url: str, data: Optional[Dict] = None) -> Optional[bytes]:
        """
        Выполняет PUT запрос (для загрузки файлов).
        
        Args:
            url: URL для запроса
            data: Данные для отправки (bytes)
            
        Returns:
            Ответ в виде bytes или None при ошибке
        """
        try:
            response = self._session().put(url, data=data, timeout=self.timeout * 2)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            logger.debug(f"PUT request error to {url}: {e}")
            return None
    
    def download_file(self, url: str, filepath: str) -> bool:
        """
        Скачивает файл по URL.
        
        Args:
            url: URL файла
            filepath: Путь для сохранения файла
            
        Returns:
            True если успешно, False иначе
        """
        try:
            response = self._session().get(url, stream=True, timeout=self.timeout * 2)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Download error from {url}: {e}")
            return False
    
    def upload_file(self, url: str, filepath: str) -> bool:
        """
        Загружает файл по URL.
        
        Args:
            url: URL для загрузки
            filepath: Путь к файлу для загрузки
            
        Returns:
            True если успешно, False иначе
        """
        try:
            with open(filepath, 'rb') as f:
                response = self._session().put(url, data=f, timeout=self.timeout * 2)
                response.raise_for_status()
            return True
        except (requests.exceptions.RequestException, IOError) as e:
            logger.error(f"Upload error to {url}: {e}")
            return False
    
    def check_connection(self, host: str, port: int = 80) -> bool:
        """
        Проверяет доступность хоста и порта.
        
        Args:
            host: IP адрес или домен
            port: Порт для проверки
            
        Returns:
            True если доступен, False иначе
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception as e:
            # Не логируем каждую ошибку, чтобы не засорять вывод
            return False
    
    def get_robot_info(self, base_url: str) -> Optional[Dict]:
        """
        Получает информацию о роботе по базовому URL.
        
        Args:
            base_url: Базовый URL робота (например, http://192.168.1.100)
            
        Returns:
            Информация о роботе или None
        """
        url = urljoin(base_url, '/api/status')
        return self.get(url)
    
    def send_data_to_robot(self, base_url: str, endpoint: str, data: Dict) -> Optional[Dict]:
        """
        Отправляет данные роботу.
        
        Args:
            base_url: Базовый URL робота
            endpoint: Конечная точка API (без начального /api, например '/status' или 'status')
            data: Данные для отправки
        
        Returns:
            Ответ робота или None
        """
        # Убираем начальный слэш из endpoint если есть
        endpoint = endpoint.lstrip('/')
        # Убираем /api из endpoint если есть (чтобы избежать дублирования)
        if endpoint.startswith('api/'):
            endpoint = endpoint[4:]
        url = urljoin(base_url, f'/api/{endpoint}')
        return self.post(url, data)
    
    def get_from_robot(self, base_url: str, endpoint: str) -> Optional[Dict]:
        """
        Получает данные от робота через GET запрос.
        
        Args:
            base_url: Базовый URL робота
            endpoint: Конечная точка API (например '/status' или '/health')
        
        Returns:
            Ответ робота или None
        """
        # Убираем начальный слэш из endpoint если есть
        endpoint = endpoint.lstrip('/')
        # Для /health используем прямой путь, для остальных добавляем /api
        if endpoint == 'health':
            url = urljoin(base_url, '/health')
        else:
            # Убираем /api из endpoint если есть (чтобы избежать дублирования)
            if endpoint.startswith('api/'):
                endpoint = endpoint[4:]
            url = urljoin(base_url, f'/api/{endpoint}')
        return self.get(url)


def get_local_network_base() -> str:
    """
    Определяет базовый адрес локальной сети.
    
    Returns:
        Базовый адрес сети (например, "192.168.1")
    """
    try:
        # Подключаемся к внешнему адресу для определения локального IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Не отправляем данные, просто определяем локальный адрес
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # Извлекаем базовый адрес сети (первые 3 октета)
        ip_parts = local_ip.split('.')
        if len(ip_parts) == 4:
            return '.'.join(ip_parts[:3])
    except Exception as e:
        logger.warning(f"Error determining local network: {e}")
    
    # Fallback на стандартную подсеть
    return "192.168.1"


def find_robots_in_network(network_base: Optional[str] = None, 
                           port: Optional[int] = None,
                           timeout: float = 0.5) -> List[str]:
    """
    Ищет роботов в локальной сети.
    
    Args:
        network_base: Базовый адрес сети (например, "192.168.1"). 
                     Если None, определяется автоматически.
        port: Порт для проверки (None = из конфигурации веб-сервера, по умолчанию 8080)
        timeout: Таймаут проверки каждого адреса
        
    Returns:
        Список IP адресов доступных роботов
    """
    if port is None:
        try:
            import services_manager
            port = services_manager.get_web_port()
        except Exception:
            port = 8080
    
    # Автоматически определяем подсеть если не указана
    if network_base is None:
        network_base = get_local_network_base()
    
    found_robots = []
    check_client = NetworkClient(timeout=max(2, int(timeout * 3)))
    
    logger.info(f"Scanning network {network_base}.0/24 (0-255) on port {port}...")
    
    def check_ip(ip_address):
        try:
            if not check_client.check_connection(ip_address, port):
                return None
            
            base_url = f"http://{ip_address}:{port}"
            try:
                robot_info = check_client.get_robot_info(base_url)
                if robot_info and isinstance(robot_info, dict) and robot_info.get("success") is not False:
                    logger.debug(f"Found robot at {ip_address}:{port}")
                    return ip_address
            except Exception:
                pass
            
            try:
                health_info = check_client.get_from_robot(base_url, "health")
                if health_info and isinstance(health_info, dict):
                    logger.debug(f"Found robot at {ip_address}:{port} (via /health)")
                    return ip_address
            except Exception:
                pass
        except Exception:
            pass
        return None
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            ip_addresses = [f"{network_base}.{i}" for i in range(0, 256)]
            results = list(executor.map(check_ip, ip_addresses))
            found_robots = [ip for ip in results if ip is not None]
        
        logger.info(f"Scan complete. Found {len(found_robots)} robot(s).")
        return found_robots
    except RuntimeError as e:
        # Обрабатываем ошибку "cannot schedule new futures after interpreter shutdown"
        if "cannot schedule new futures" in str(e) or "interpreter shutdown" in str(e):
            logger.warning("Network scan interrupted: interpreter is shutting down")
            return []
        raise
    except Exception as e:
        logger.error(f"Error during network scan: {e}", exc_info=True)
        return []

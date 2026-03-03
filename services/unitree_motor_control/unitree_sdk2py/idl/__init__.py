# Опциональный импорт default (может отсутствовать)
try:
from .default import *
except ImportError:
    pass

# Импортируем только существующие модули
_available_modules = []
for module_name in ['builtin_interfaces', 'geometry_msgs', 'sensor_msgs', 'std_msgs', 'unitree_go', 'unitree_api', 'unitree_hg']:
    try:
        __import__(f'.{module_name}', __name__, fromlist=[module_name])
        _available_modules.append(module_name)
    except ImportError:
        pass

__all__ = _available_modules

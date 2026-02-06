"""
API модуль для управления моторами Unitree.
"""
from flask import Flask, request, jsonify
from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Добавляем путь к корню проекта
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from services.unitree_motor_control.unitree_motor_control import get_controller
    CONTROLLER_AVAILABLE = True
except ImportError as e:
    CONTROLLER_AVAILABLE = False
    get_controller = None
    # Для отладки можно раскомментировать:
    # print(f"[UnitreeMotorAPI] Import error: {e}", flush=True)


class UnitreeMotorAPI:
    """API для управления моторами Unitree."""
    
    @staticmethod
    def set_motor_angle(motor_index: int, angle: float, velocity: float = 0.0) -> Dict[str, Any]:
        """
        Устанавливает угол для одного мотора.
        
        Args:
            motor_index: Индекс мотора (0-19)
            angle: Целевой угол в радианах
            velocity: Скорость перехода (рад/с), 0 = мгновенный переход
            
        Returns:
            Результат операции
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            controller.set_motor_angle(motor_index, angle, velocity)
            return {
                "success": True,
                "message": f"Motor {motor_index} angle set to {angle} rad",
                "motor_index": motor_index,
                "angle": angle,
                "velocity": velocity
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error setting motor angle: {str(e)}"
            }
    
    @staticmethod
    def set_motor_angles(angles: Dict[int, float], velocity: float = 0.0, source: str = "api", interpolation: float = 0.0) -> Dict[str, Any]:
        """
        Устанавливает углы для нескольких моторов.
        Поддерживает частичные обновления - можно указать только нужные моторы.
        
        Args:
            angles: Словарь {motor_index: angle} - только те моторы, которые нужно обновить
            velocity: Скорость перехода (рад/с), используется только если interpolation > 0
            source: Источник команды ("api", "neural_network", "manual")
            interpolation: Скорость интерполяции (рад/с). 0 = прямое управление углом без интерполяции
            
        Returns:
            Результат операции
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            controller.set_motor_angles(angles, velocity, source, interpolation)
            return {
                "success": True,
                "message": f"Set angles for {len(angles)} motors",
                "motors_updated": list(angles.keys()),
                "angles": angles,
                "velocity": velocity,
                "interpolation": interpolation,
                "source": source
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error setting motor angles: {str(e)}"
            }
    
    @staticmethod
    def get_motor_angles() -> Dict[str, Any]:
        """
        Получает текущие углы всех моторов.
        
        Returns:
            Текущие углы моторов
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            angles = controller.get_motor_angles()
            target_angles = controller.get_target_angles()
            return {
                "success": True,
                "current_angles": angles,
                "target_angles": target_angles
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting motor angles: {str(e)}"
            }
    
    @staticmethod
    def set_motor_angles_from_neural_network(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Устанавливает углы моторов из данных нейронной сети.
        
        Ожидаемый формат данных:
        {
            "angles": [angle0, angle1, ..., angle19] или {"0": angle0, "1": angle1, ...}
            "velocity": float (опционально, скорость перехода)
        }
        
        Args:
            data: Данные от нейронной сети
            
        Returns:
            Результат операции
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            angles_data = data.get("angles", [])
            velocity = data.get("velocity", 0.0)
            
            # Преобразуем данные в словарь {motor_index: angle}
            angles_dict = {}
            
            if isinstance(angles_data, list):
                # Список углов [angle0, angle1, ...]
                for i, angle in enumerate(angles_data):
                    if i < 20:  # H1 имеет 20 моторов
                        angles_dict[i] = float(angle)
            elif isinstance(angles_data, dict):
                # Словарь {"0": angle0, "1": angle1, ...} или {0: angle0, 1: angle1, ...}
                for key, angle in angles_data.items():
                    try:
                        motor_index = int(key)
                        if 0 <= motor_index < 20:
                            angles_dict[motor_index] = float(angle)
                    except (ValueError, TypeError):
                        continue
            
            if not angles_dict:
                return {
                    "success": False,
                    "message": "No valid angles provided"
                }
            
            # Используем источник "neural_network" для автоматической высокой скорости
            controller.set_motor_angles(angles_dict, velocity, source="neural_network")
            
            return {
                "success": True,
                "message": f"Set angles for {len(angles_dict)} motors from neural network",
                "motors_count": len(angles_dict),
                "motors_updated": list(angles_dict.keys()),
                "velocity": velocity if velocity > 0 else "auto (neural network default)"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error setting angles from neural network: {str(e)}"
            }
    
    @staticmethod
    def get_controller_config() -> Dict[str, Any]:
        """
        Получает конфигурацию контроллера (скорости, параметры сглаживания).
        
        Returns:
            Конфигурация контроллера
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            return {
                "success": True,
                "neural_network_velocity": controller.neural_network_velocity,
                "smoothing_factor": controller.smoothing_factor,
                "control_dt": controller.control_dt
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error getting controller config: {str(e)}"
            }
    
    @staticmethod
    def set_controller_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Устанавливает конфигурацию контроллера.
        
        Args:
            config: Словарь с параметрами {"neural_network_velocity": float, "smoothing_factor": float}
            
        Returns:
            Результат операции
        """
        if not CONTROLLER_AVAILABLE:
            return {
                "success": False,
                "message": "Unitree motor controller not available"
            }
        
        controller = get_controller()
        if not controller:
            return {
                "success": False,
                "message": "Motor controller not initialized"
            }
        
        try:
            if "neural_network_velocity" in config:
                controller.set_neural_network_velocity(float(config["neural_network_velocity"]))
            
            if "smoothing_factor" in config:
                controller.set_smoothing_factor(float(config["smoothing_factor"]))
            
            return {
                "success": True,
                "message": "Controller config updated",
                "config": {
                    "neural_network_velocity": controller.neural_network_velocity,
                    "smoothing_factor": controller.smoothing_factor
                }
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error setting controller config: {str(e)}"
            }

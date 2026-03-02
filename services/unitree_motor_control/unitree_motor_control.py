"""
Сервис управления моторами Unitree робота.
Переключает робота в real mode, берет контроль над всеми моторами
и предоставляет API для установки углов с плавными переходами.
"""
import os
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import deque

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.unitree_motor_control.dependencies import setup_dependencies, setup_cyclonedds_environment

setup_cyclonedds_environment()

import os
venv_path = None
if 'VIRTUAL_ENV' in os.environ:
    venv_path = os.environ['VIRTUAL_ENV']
elif sys.executable and '/bin/' in sys.executable:
    venv_path = sys.executable.rsplit('/bin/', 1)[0]
    if not os.path.exists(os.path.join(venv_path, 'lib')):
        venv_path = None

if venv_path:
    venv_lib = os.path.join(venv_path, 'lib')
    venv_lib64 = os.path.join(venv_path, 'lib64')
    
    ld_library_path = os.environ.get('LD_LIBRARY_PATH', '')
    paths_to_add = []
    
    if os.path.exists(venv_lib):
        if venv_lib not in ld_library_path:
            paths_to_add.append(venv_lib)
    
    if os.path.exists(venv_lib64) and venv_lib64 not in ld_library_path:
        paths_to_add.append(venv_lib64)
    
    if paths_to_add:
        new_ld_path = ':'.join(paths_to_add)
        os.environ['LD_LIBRARY_PATH'] = f"{new_ld_path}:{ld_library_path}" if ld_library_path else new_ld_path
        print(f"[UnitreeMotorControl] Added venv lib paths to LD_LIBRARY_PATH: {paths_to_add}", flush=True)

NUMPY_AVAILABLE, CYCLONEDDS_AVAILABLE = setup_dependencies()

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    class np:
        @staticmethod
        def sign(x):
            return 1 if x > 0 else (-1 if x < 0 else 0)
        
        @staticmethod
        def clip(x, min_val, max_val):
            return max(min_val, min(max_val, x))

SERVICE_DIR = Path(__file__).resolve().parent
LOCAL_SDK_PATH = SERVICE_DIR / "unitree_sdk2py"
if LOCAL_SDK_PATH.exists() and str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

H1_CONST_PATH = SERVICE_DIR / "unitree_legged_const.py"

SDK_AVAILABLE = False
MotionSwitcherClient = None

try:
    from unitree_sdk2py.core.channel import ChannelPublisher, ChannelSubscriber, ChannelFactoryInitialize
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowCmd_, LowState_
    from unitree_sdk2py.utils.crc import CRC
    from unitree_sdk2py.utils.thread import RecurrentThread
    import unitree_legged_const as h1
    
    try:
        import cyclonedds
        cyclonedds_location = Path(cyclonedds.__file__).parent
    except:
        pass
    
    try:
        from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
    except ImportError:
        MotionSwitcherClient = type('MotionSwitcherClient', (), {
            'SetTimeout': lambda self, x: None,
            'Init': lambda self: None,
            'CheckMode': lambda self: (False, None),
            'ReleaseMode': lambda self: None
        })
    
    SDK_AVAILABLE = True
except ImportError as e:
    SDK_AVAILABLE = False
    LowCmd_ = type('LowCmd_', (), {})
    LowState_ = type('LowState_', (), {})
    CRC = type('CRC', (), {'Crc': lambda self, x: 0})
    RecurrentThread = type('RecurrentThread', (), {'Start': lambda self: None, 'Wait': lambda self, timeout: None})
    MotionSwitcherClient = type('MotionSwitcherClient', (), {'SetTimeout': lambda self, x: None, 'Init': lambda self: None, 'CheckMode': lambda self: (False, None), 'ReleaseMode': lambda self: None})
    h1 = type('h1', (), {'PosStopF': 2.146e9, 'VelStopF': 16000.0})()
except Exception as e:
    SDK_AVAILABLE = False
    LowCmd_ = type('LowCmd_', (), {})
    LowState_ = type('LowState_', (), {})
    CRC = type('CRC', (), {'Crc': lambda self, x: 0})
    RecurrentThread = type('RecurrentThread', (), {'Start': lambda self: None, 'Wait': lambda self, timeout: None})
    MotionSwitcherClient = type('MotionSwitcherClient', (), {'SetTimeout': lambda self, x: None, 'Init': lambda self: None, 'CheckMode': lambda self: (False, None), 'ReleaseMode': lambda self: None})
    h1 = type('h1', (), {'PosStopF': 2.146e9, 'VelStopF': 16000.0})()

import services_manager
import status

H1_NUM_MOTOR = 20

class H1JointIndex:
    kRightHipRoll = 0
    kRightHipPitch = 1
    kRightKnee = 2
    kLeftHipRoll = 3
    kLeftHipPitch = 4
    kLeftKnee = 5
    kWaistYaw = 6
    kLeftHipYaw = 7
    kRightHipYaw = 8
    kNotUsedJoint = 9
    kLeftAnkle = 10
    kRightAnkle = 11
    kRightShoulderPitch = 12
    kRightShoulderRoll = 13
    kRightShoulderYaw = 14
    kRightElbow = 15
    kLeftShoulderPitch = 16
    kLeftShoulderRoll = 17
    kLeftShoulderYaw = 18
    kLeftElbow = 19

MOTOR_LIMITS = {
    H1JointIndex.kRightHipYaw: (-0.33, 0.33),
    H1JointIndex.kRightHipRoll: (-0.33, 0.33),
    H1JointIndex.kRightHipPitch: (-3.04, 2.43),
    H1JointIndex.kRightKnee: (-0.16, 1.95),
    H1JointIndex.kRightAnkle: (-0.77, 0.42),
    H1JointIndex.kLeftHipYaw: (-0.33, 0.33),
    H1JointIndex.kLeftHipRoll: (-0.33, 0.33),
    H1JointIndex.kLeftHipPitch: (-3.04, 2.43),
    H1JointIndex.kLeftKnee: (-0.16, 1.95),
    H1JointIndex.kLeftAnkle: (-0.77, 0.42),
    H1JointIndex.kWaistYaw: (-2.25, 2.25),
    H1JointIndex.kRightShoulderPitch: (-2.77, 2.77),
    H1JointIndex.kRightShoulderRoll: (-3.01, 0.24),
    H1JointIndex.kRightShoulderYaw: (-4.35, 1.2),
    H1JointIndex.kRightElbow: (-1.15, 2.51),
    H1JointIndex.kLeftShoulderPitch: (-2.77, 2.77),
    H1JointIndex.kLeftShoulderRoll: (-0.24, 3.01),
    H1JointIndex.kLeftShoulderYaw: (-1.2, 4.35),
    H1JointIndex.kLeftElbow: (-1.15, 2.51),
}

SERVICE_NAME = "unitree_motor_control"


class MotorController:
    """Класс для управления моторами с плавными переходами."""
    
    def __init__(self):
        self.control_dt = 0.01
        self.low_cmd = None
        self.low_state = None
        self.crc = None
        self.lowcmd_publisher = None
        self.lowstate_subscriber = None
        self.msc = None
        self.control_thread = None
        
        self.kp_low = 100.0
        self.kp_high = 300.0
        self.kd_low = 3.0
        self.kd_high = 8.0
        
        self.target_angles = {}
        self.current_angles = {}
        self.angle_velocities = {}
        self.initial_positions = None
        
        self.command_queue = {}
        self.command_sources = {}
        
        self.neural_network_velocity = 10.0
        self.smoothing_factor = 0.3
        
        self.lock = threading.Lock()
        self.initialized = False
        self.running = False
    
    def is_weak_motor(self, motor_index: int) -> bool:
        """Проверяет, является ли мотор слабым (для рук и лодыжек)."""
        return motor_index in {
            H1JointIndex.kLeftAnkle,
            H1JointIndex.kRightAnkle,
            H1JointIndex.kRightShoulderPitch,
            H1JointIndex.kRightShoulderRoll,
            H1JointIndex.kRightShoulderYaw,
            H1JointIndex.kRightElbow,
            H1JointIndex.kLeftShoulderPitch,
            H1JointIndex.kLeftShoulderRoll,
            H1JointIndex.kLeftShoulderYaw,
            H1JointIndex.kLeftElbow,
        }
    
    def init(self, domain_id: int = 1, network_interface: str = "lo"):
        """Инициализирует подключение к роботу."""
        print(f"[UnitreeMotorControl] init() called with domain_id={domain_id}, network_interface={network_interface}", flush=True)
        print(f"[UnitreeMotorControl] Python: {sys.executable}", flush=True)
        print(f"[UnitreeMotorControl] LD_LIBRARY_PATH: {os.environ.get('LD_LIBRARY_PATH', 'not set')}", flush=True)
        
        if not SDK_AVAILABLE:
            raise RuntimeError("Unitree SDK not available")
        
        print(f"[UnitreeMotorControl] SDK is available, initializing ChannelFactory...", flush=True)
        print(f"[UnitreeMotorControl] Domain ID: {domain_id}, Network Interface: {network_interface}", flush=True)
        
        try:
            print(f"[UnitreeMotorControl] Calling ChannelFactoryInitialize...", flush=True)
            ChannelFactoryInitialize(domain_id, network_interface)
            print(f"[UnitreeMotorControl] ChannelFactory initialized successfully", flush=True)
        except Exception as e:
            print(f"[UnitreeMotorControl] ERROR: ChannelFactoryInitialize failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise
        
        if MotionSwitcherClient and hasattr(MotionSwitcherClient, '__call__'):
            try:
                self.msc = MotionSwitcherClient()
                self.msc.SetTimeout(5.0)
                self.msc.Init()
                
                status, result = self.msc.CheckMode()
                if status == 0 and result:
                    mode_name = result.get('name', 'unknown')
                    if mode_name:
                        release_code, _ = self.msc.ReleaseMode()
                        if release_code == 0:
                            time.sleep(1.0)
            except Exception as e:
                self.msc = None
        else:
            self.msc = None
        
        print(f"[UnitreeMotorControl] Creating LowCmd_ structure...", flush=True)
        try:
            from unitree_sdk2py.idl.default import unitree_go_msg_dds__LowCmd_
            print(f"[UnitreeMotorControl] Using default factory for LowCmd_...", flush=True)
            self.low_cmd = unitree_go_msg_dds__LowCmd_()
            self.low_cmd.head[0] = 0xFE
            self.low_cmd.head[1] = 0xEF
            self.low_cmd.level_flag = 0xFF
            print(f"[UnitreeMotorControl] LowCmd_ created successfully using default factory", flush=True)
        except Exception as e:
            print(f"[UnitreeMotorControl] Default factory failed: {e}, using manual creation...", flush=True)
            import traceback
            traceback.print_exc()
            from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorCmd_, BmsCmd_
            print(f"[UnitreeMotorControl] Creating MotorCmd_ and BmsCmd_...", flush=True)
            motor_cmds = [MotorCmd_(mode=0, q=0.0, dq=0.0, tau=0.0, kp=0.0, kd=0.0, reserve=[0, 0, 0]) for _ in range(20)]
            print(f"[UnitreeMotorControl] Created {len(motor_cmds)} MotorCmd_ instances", flush=True)
            bms_cmd = BmsCmd_(off=0, reserve=[0, 0, 0])
            print(f"[UnitreeMotorControl] Creating LowCmd_ manually...", flush=True)
            self.low_cmd = LowCmd_(
                head=[0xFE, 0xEF],
                level_flag=0xFF,
                frame_reserve=0,
                sn=[0, 0],
                version=[0, 0],
                bandwidth=0,
                motor_cmd=motor_cmds,
                bms_cmd=bms_cmd,
                wireless_remote=[0] * 40,
                led=[0] * 12,
                fan=[0, 0],
                gpio=0,
                reserve=0,
                crc=0
            )
            print(f"[UnitreeMotorControl] LowCmd_ created successfully manually", flush=True)
        
        print(f"[UnitreeMotorControl] Creating CRC instance...", flush=True)
        self.crc = CRC()
        print(f"[UnitreeMotorControl] Creating channel publisher...", flush=True)
        self.lowcmd_publisher = ChannelPublisher("rt/lowcmd", LowCmd_)
        print(f"[UnitreeMotorControl] Initializing channel publisher...", flush=True)
        self.lowcmd_publisher.Init()
        print(f"[UnitreeMotorControl] Creating channel subscriber...", flush=True)
        self.lowstate_subscriber = ChannelSubscriber("rt/lowstate", LowState_)
        print(f"[UnitreeMotorControl] Initializing channel subscriber...", flush=True)
        self.lowstate_subscriber.Init(self.low_state_handler, 10)
        print(f"[UnitreeMotorControl] Channels initialized successfully", flush=True)
        
        time.sleep(2.0)
        
        timeout = 30.0
        start_time = time.time()
        check_interval = 2.0
        last_check = start_time
        use_read_method = False
        
        while self.low_state is None and (time.time() - start_time) < timeout:
            current_time = time.time()
            if current_time - last_check >= check_interval:
                elapsed = current_time - start_time
                last_check = current_time
                
                if elapsed > 10.0 and not use_read_method:
                    use_read_method = True
                    try:
                        msg = self.lowstate_subscriber.Read(timeout=2.0)
                        if msg:
                            self.low_state_handler(msg)
                            break
                    except Exception:
                        pass
            
            time.sleep(0.1)
        
        if self.low_state is None:
            error_msg = (
                f"Failed to receive robot state after {timeout}s. "
                f"Check: 1) Robot/simulator is powered on and running, 2) Network interface '{network_interface}' is correct, "
                f"3) Domain ID {domain_id} matches robot/simulator configuration, 4) For simulator: verify it's publishing on rt/lowstate"
            )
            print(f"[UnitreeMotorControl] ERROR: {error_msg}", flush=True)
            raise RuntimeError(error_msg)
        
        self.initial_positions = [self.low_state.motor_state[i].q for i in range(H1_NUM_MOTOR)]
        with self.lock:
            for i in range(H1_NUM_MOTOR):
                self.current_angles[i] = self.initial_positions[i]
                self.target_angles[i] = self.initial_positions[i]
                self.angle_velocities[i] = 0.0
        
        self.init_low_cmd()
        
        self.initialized = True
    
    def init_low_cmd(self):
        """Инициализирует команды низкого уровня."""
        self.low_cmd.head[0] = 0xFE
        self.low_cmd.head[1] = 0xEF
        self.low_cmd.level_flag = 0xFF
        self.low_cmd.gpio = 0
        
        with self.lock:
            for i in range(H1_NUM_MOTOR):
                if self.is_weak_motor(i):
                    self.low_cmd.motor_cmd[i].mode = 0x01
                    self.low_cmd.motor_cmd[i].kp = self.kp_low
                    self.low_cmd.motor_cmd[i].kd = self.kd_low
                else:
                    self.low_cmd.motor_cmd[i].mode = 0x0A
                    self.low_cmd.motor_cmd[i].kp = self.kp_high
                    self.low_cmd.motor_cmd[i].kd = self.kd_high
                
                initial_angle = self.initial_positions[i] if self.initial_positions and i < len(self.initial_positions) else 0.0
                self.low_cmd.motor_cmd[i].q = initial_angle
                self.low_cmd.motor_cmd[i].dq = 0.0
                self.low_cmd.motor_cmd[i].tau = 0.0
    
    def low_state_handler(self, msg: LowState_):
        """Обработчик состояния робота."""
        if msg is None:
            return
        
        try:
            self.low_state = msg
            
            if msg and hasattr(msg, 'motor_state'):
                with self.lock:
                    for i in range(min(H1_NUM_MOTOR, len(msg.motor_state))):
                        if hasattr(msg.motor_state[i], 'q'):
                            self.current_angles[i] = msg.motor_state[i].q
        except Exception:
            pass
    
    def start_control(self):
        """Запускает поток управления."""
        if not self.initialized:
            raise RuntimeError("Controller not initialized")
        
        if self.running:
            return
        
        print(f"[UnitreeMotorControl] Starting control loop...", flush=True)
        self.running = True
        
        try:
            self.control_thread = RecurrentThread(
                interval=self.control_dt,
                target=self.control_loop,
                name="motor_control"
            )
            self.control_thread.Start()
            print(f"[UnitreeMotorControl] Control loop started successfully", flush=True)
        except Exception as e:
            print(f"[UnitreeMotorControl] ERROR starting control loop: {e}", flush=True)
            import traceback
            traceback.print_exc()
            self.running = False
            raise
    
    def stop_control(self):
        """Останавливает поток управления."""
        if not self.running:
            return
        
        self.running = False
        if self.control_thread:
            self.control_thread.Wait(timeout=1.0)
    
    def control_loop(self):
        """Основной цикл управления моторами. КРИТИЧНО: Не должен падать ни при каких обстоятельствах."""
        if not self.low_state or not self.initialized or not self.running:
            return
        
        try:
            if not self.low_cmd or not self.initial_positions or not self.lowcmd_publisher or not self.crc:
                return
            
            with self.lock:
                if self.low_state and hasattr(self.low_state, 'motor_state'):
                    try:
                        motor_state_len = len(self.low_state.motor_state) if hasattr(self.low_state, 'motor_state') else 0
                        for i in range(min(H1_NUM_MOTOR, motor_state_len)):
                            if hasattr(self.low_state.motor_state[i], 'q'):
                                self.current_angles[i] = self.low_state.motor_state[i].q
                    except Exception as e:
                        print(f"[UnitreeMotorControl] Error reading motor_state: {e}", flush=True)
                    
                for i in range(H1_NUM_MOTOR):
                    try:
                        if not hasattr(self.low_cmd, 'motor_cmd') or i >= len(self.low_cmd.motor_cmd):
                            continue
                        
                        if self.is_weak_motor(i):
                            self.low_cmd.motor_cmd[i].mode = 0x01
                            self.low_cmd.motor_cmd[i].kp = self.kp_low
                            self.low_cmd.motor_cmd[i].kd = self.kd_low
                        else:
                            self.low_cmd.motor_cmd[i].mode = 0x0A
                            self.low_cmd.motor_cmd[i].kp = self.kp_high
                            self.low_cmd.motor_cmd[i].kd = self.kd_high
                        
                        if i not in self.current_angles:
                            if self.initial_positions and i < len(self.initial_positions):
                                self.current_angles[i] = self.initial_positions[i]
                            else:
                                self.current_angles[i] = 0.0
                        
                        current_angle = self.current_angles[i]
                        
                        if i not in self.target_angles:
                            new_angle = current_angle
                            dq = 0.0
                        else:
                            target_angle = self.target_angles[i]
                            velocity = self.angle_velocities.get(i, 0.0)
                            
                            delta = target_angle - current_angle
                            
                            if abs(delta) > 0.01:
                                if velocity > 0:
                                    max_delta = velocity * self.control_dt
                                    
                                    if abs(delta) <= max_delta:
                                        new_angle = target_angle
                                        dq = delta / self.control_dt
                                    else:
                                        new_angle = current_angle + np.sign(delta) * max_delta
                                        dq = velocity * np.sign(delta)
                                else:
                                    new_angle = target_angle
                                    dq = delta / self.control_dt if abs(delta) > 0.01 else 0.0
                            else:
                                new_angle = target_angle
                                dq = 0.0
                        
                        if i in MOTOR_LIMITS:
                            min_limit, max_limit = MOTOR_LIMITS[i]
                            new_angle = max(min_limit, min(max_limit, new_angle))
                        
                        self.low_cmd.motor_cmd[i].q = new_angle
                        self.low_cmd.motor_cmd[i].dq = dq
                        self.low_cmd.motor_cmd[i].tau = 0.0
                    except Exception:
                        continue
            
            try:
                if self.low_cmd and self.crc and self.lowcmd_publisher:
                    try:
                        self.low_cmd.crc = self.crc.Crc(self.low_cmd)
                    except Exception as crc_e:
                        print(f"[UnitreeMotorControl] Error computing CRC: {crc_e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        return
                    
                    try:
                        if not hasattr(self.lowcmd_publisher, '__inited') or not self.lowcmd_publisher.__inited:
                            return
                        
                        self.lowcmd_publisher.Write(self.low_cmd, timeout=0.1)
                    except Exception as write_e:
                        print(f"[UnitreeMotorControl] Error writing to publisher: {write_e}", flush=True)
                        import traceback
                        traceback.print_exc()
            except Exception as e:
                print(f"[UnitreeMotorControl] Error in control_loop write section: {e}", flush=True)
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"[UnitreeMotorControl] CRITICAL: Error in control_loop: {e}", flush=True)
    
    def set_motor_angle(self, motor_index: int, angle: float, velocity: float = 0.0, source: str = "api"):
        """
        Устанавливает целевой угол для мотора.
        
        Args:
            motor_index: Индекс мотора (0-19)
            angle: Целевой угол в радианах
            velocity: Максимальная скорость перехода (рад/с). 0 = мгновенный переход
            source: Источник команды ("api", "neural_network", "manual", etc.)
        """
        if not self.initialized:
            raise RuntimeError("Controller not initialized. Robot may not be connected.")
        
        if motor_index < 0 or motor_index >= H1_NUM_MOTOR:
            raise ValueError(f"Invalid motor index: {motor_index}")
        
        if motor_index in MOTOR_LIMITS:
            min_limit, max_limit = MOTOR_LIMITS[motor_index]
            angle = max(min_limit, min(max_limit, angle))
        
        try:
            current_time = time.time()
            
            with self.lock:
                effective_velocity = max(0.0, min(100.0, velocity)) if velocity > 0 else (
                    self.neural_network_velocity if source == "neural_network" else 0.0
                )
                
                self.command_queue[motor_index] = (angle, effective_velocity, current_time, source)
                self.target_angles[motor_index] = angle
                self.angle_velocities[motor_index] = effective_velocity
                self.command_sources[motor_index] = source
        except Exception as e:
            raise
    
    def set_motor_angles(self, angles: Dict[int, float], velocity: float = 0.0, source: str = "api", interpolation: float = 0.0):
        """
        Устанавливает целевые углы для нескольких моторов.
        Поддерживает частичные обновления - обновляются только указанные моторы.
        
        Args:
            angles: Словарь {motor_index: angle} - только те моторы, которые нужно обновить
            velocity: Максимальная скорость перехода (рад/с), используется только если interpolation > 0
            source: Источник команды ("api", "neural_network", "manual", etc.)
            interpolation: Скорость интерполяции (рад/с). 0 = прямое управление углом без интерполяции
        """
        if not self.initialized:
            raise RuntimeError("Controller not initialized. Robot may not be connected.")
        
        current_time = time.time()
        
        with self.lock:
            for motor_index, angle in angles.items():
                if 0 <= motor_index < H1_NUM_MOTOR:
                    if motor_index in MOTOR_LIMITS:
                        min_limit, max_limit = MOTOR_LIMITS[motor_index]
                        angle = max(min_limit, min(max_limit, angle))
                    
                    if interpolation > 0:
                        effective_velocity = max(0.0, min(100.0, interpolation))
                    else:
                        effective_velocity = 0.0
                    
                    self.command_queue[motor_index] = (angle, effective_velocity, current_time, source)
                    self.target_angles[motor_index] = angle
                    self.angle_velocities[motor_index] = effective_velocity
                    self.command_sources[motor_index] = source
    
    def get_motor_angles(self) -> Dict[int, float]:
        """Получает текущие углы всех моторов."""
        if not self.initialized:
            raise RuntimeError("Controller not initialized. Robot may not be connected.")
        
        try:
            with self.lock:
                return dict(self.current_angles)
        except Exception:
            return {}
    
    def get_target_angles(self) -> Dict[int, float]:
        """Получает целевые углы всех моторов."""
        if not self.initialized:
            raise RuntimeError("Controller not initialized. Robot may not be connected.")
        
        try:
            with self.lock:
                return dict(self.target_angles)
        except Exception:
            return {}
    
    def get_command_sources(self) -> Dict[int, str]:
        """Получает источники команд для каждого мотора."""
        with self.lock:
            return dict(self.command_sources)
    
    def set_neural_network_velocity(self, velocity: float):
        """Устанавливает скорость по умолчанию для команд от нейросети."""
        self.neural_network_velocity = max(0.0, velocity)
    
    def set_smoothing_factor(self, factor: float):
        """Устанавливает фактор сглаживания (0-1, меньше = плавнее)."""
        self.smoothing_factor = np.clip(factor, 0.0, 1.0)
    
    def release_mode(self):
        """Освобождает режим управления."""
        if self.msc and hasattr(self.msc, 'ReleaseMode'):
            try:
                self.msc.ReleaseMode()
            except Exception:
                pass
    
    def reinitialize_controller(self, domain_id: int = None, network_interface: str = None):
        """
        Переинициализирует контроллер с новыми параметрами.
        
        Args:
            domain_id: ID домена для DDS (если None, используется текущий)
            network_interface: Имя сетевого интерфейса (если None, используется текущий)
        """
        if not SDK_AVAILABLE:
            raise RuntimeError("Unitree SDK not available")
        
        was_running = self.running
        if was_running:
            self.stop_control()
        
        try:
            if domain_id is None or network_interface is None:
                import services_manager
                manager = services_manager.get_services_manager()
                params = manager.get_service_parameters("unitree_motor_control")
                if domain_id is None:
                    domain_id = params.get("id", 1)
                if network_interface is None:
                    network_interface = params.get("network", "lo")
            
            self.initialized = False
            self.init(domain_id=domain_id, network_interface=network_interface)
            
            if was_running:
                self.start_control()
        except Exception as e:
            self.initialized = False
            raise


_controller: Optional[MotorController] = None


def get_controller() -> Optional[MotorController]:
    """Получает глобальный экземпляр контроллера."""
    return _controller


def run():
    """
    Основная функция запуска сервиса.
    КРИТИЧНО: Этот сервис управляет реальным роботом и НЕ ДОЛЖЕН ПАДАТЬ ни при каких обстоятельствах.
    Все ошибки обрабатываются, сервис продолжает работу даже при критических ошибках.
    
    Примечание: Обработчики сигналов не регистрируются здесь, так как сервис запускается в отдельном потоке.
    Сигналы обрабатываются в main.py (главный поток). Завершение сервиса происходит через проверку статуса.
    """
    global _controller
    
    service_name = SERVICE_NAME
    manager = services_manager.get_services_manager()
    
    print(f"[{service_name}] Starting service...", flush=True)
    
    # Получаем параметры сервиса
    try:
        service_info = manager.get_service(service_name)
        params = manager.get_service_parameters(service_name)
    except Exception as e:
        print(f"[{service_name}] Error getting service parameters: {e}, using defaults", flush=True)
        params = {}
    
    # Параметры конфигурации
    domain_id = params.get("id", 1)
    network_interface = params.get("network", "lo")
    
    # Проверяем доступность SDK
    if not SDK_AVAILABLE:
        print(f"[{service_name}] ERROR: Unitree SDK not available. Please install it.", flush=True)
        try:
            status.register_service_data(service_name, {
                "status": "error",
                "error": "Unitree SDK not available",
                "initialized": False
            })
        except Exception:
            pass
        # Продолжаем работать, но без контроллера
        _controller = None
    else:
        _controller = None
    
    # Флаг для отслеживания попыток переподключения
    reconnect_interval = 10.0  # Попытка переподключения каждые 10 секунд
    last_reconnect_attempt = 0.0
    initialization_error = None
    
    shutdown_request_count = 0
    last_shutdown_request_time = 0.0
    shutdown_request_timeout = 5.0
    auto_reset_time = 0.0
    
    try:
        while True:
            current_time = time.time()
            
            try:
                service_info = manager.get_service(service_name)
                service_status = service_info.get("status", "ON")
                if service_status == "OFF":
                    print(f"[{service_name}] Status check: OFF detected", flush=True)
            except Exception as e:
                print(f"[{service_name}] Error getting service status: {e}, continuing...", flush=True)
                service_status = "ON"
            
            if service_status == "OFF":
                time_since_last = current_time - last_shutdown_request_time if last_shutdown_request_time > 0 else shutdown_request_timeout + 1
                
                if time_since_last > shutdown_request_timeout:
                    if shutdown_request_count > 0:
                        print(f"[{service_name}] Shutdown counter reset due to timeout ({time_since_last:.1f}s > {shutdown_request_timeout}s)", flush=True)
                    shutdown_request_count = 0
                
                shutdown_request_count += 1
                last_shutdown_request_time = current_time
                
                print(f"[{service_name}] Shutdown request #{shutdown_request_count}/3 received (timeout: {shutdown_request_timeout}s)", flush=True)
                
                if shutdown_request_count < 3:
                    print(f"[{service_name}] CRITICAL: Shutdown requires 3 consecutive requests within {shutdown_request_timeout}s. Current: {shutdown_request_count}/3", flush=True)
                    try:
                        auto_reset_time = current_time
                        manager.update_service_status(service_name, "ON")
                        print(f"[{service_name}] Status reset to ON for safety. Waiting for next request...", flush=True)
                    except Exception as e:
                        print(f"[{service_name}] Error resetting status: {e}", flush=True)
                    time.sleep(0.1)
                    continue
                else:
                    print(f"[{service_name}] 3 shutdown requests received within timeout. Shutting down...", flush=True)
                    break
            elif service_status == "ON":
                if shutdown_request_count > 0:
                    time_since_last = current_time - last_shutdown_request_time
                    if current_time - auto_reset_time < 2.0:
                        pass
                    elif time_since_last > shutdown_request_timeout:
                        print(f"[{service_name}] Shutdown counter reset due to timeout (no requests for {time_since_last:.1f}s)", flush=True)
                        shutdown_request_count = 0
                    else:
                        pass
                else:
                    if last_shutdown_request_time > 0 and current_time - last_shutdown_request_time > shutdown_request_timeout:
                        shutdown_request_count = 0
            elif service_status == "SLEEP":
                time.sleep(1)
                continue
            
            if _controller is None or not _controller.initialized:
                if current_time - last_reconnect_attempt >= reconnect_interval:
                    last_reconnect_attempt = current_time
                    
                    if not SDK_AVAILABLE:
                        status.register_service_data(service_name, {
                            "status": "error",
                            "error": "Unitree SDK not available",
                            "initialized": False
                        })
                        time.sleep(1)
                        continue
                    
                    try:
                        print(f"[{service_name}] Attempting to initialize controller...", flush=True)
                        
                        if _controller is not None:
                            try:
                                _controller.stop_control()
                                _controller.release_mode()
                            except:
                                pass
                            _controller = None
                        
                        _controller = MotorController()
                        _controller.init(domain_id=domain_id, network_interface=network_interface)
                        _controller.start_control()
                        
                        initialization_error = None
                        print(f"[{service_name}] Controller initialized successfully", flush=True)
                        
                    except Exception as e:
                        initialization_error = str(e)
                        print(f"[{service_name}] Initialization failed: {e}", flush=True)
                        if _controller:
                            try:
                                _controller.stop_control()
                                _controller.release_mode()
                            except:
                                pass
                            _controller = None
                
                status.register_service_data(service_name, {
                    "status": "error" if initialization_error else "connecting",
                    "error": initialization_error or "Robot not connected",
                    "initialized": False,
                    "domain_id": domain_id,
                    "network_interface": network_interface,
                    "reconnect_interval": reconnect_interval
                })
                
                time.sleep(0.1)
                continue
            
            try:
                current_angles = _controller.get_motor_angles()
                target_angles = _controller.get_target_angles()
                
                try:
                    status.register_service_data(service_name, {
                        "status": "running",
                        "initialized": True,
                        "domain_id": domain_id,
                        "network_interface": network_interface,
                        "current_angles": current_angles,
                        "target_angles": target_angles,
                        "motor_count": H1_NUM_MOTOR
                    })
                except Exception as e:
                    print(f"[{service_name}] Error registering status: {e}", flush=True)
            except Exception as e:
                print(f"[{service_name}] Error getting motor data: {e}", flush=True)
                try:
                    _controller.initialized = False
                except Exception:
                    pass
            
            time.sleep(0.1)
    
    except KeyboardInterrupt:
        print(f"\n[{service_name}] Stopped by user (KeyboardInterrupt)", flush=True)
    except Exception as e:
        print(f"[{service_name}] CRITICAL ERROR in main loop: {e}", flush=True)
        import traceback
        traceback.print_exc()
        try:
            status.register_service_data(service_name, {
                "status": "error",
                "error": str(e),
                "initialized": False
            })
        except Exception:
            pass
        time.sleep(5)
    finally:
        if _controller:
            try:
                _controller.stop_control()
                _controller.release_mode()
            except Exception as e:
                print(f"[{service_name}] Error during cleanup: {e}", flush=True)
        _controller = None
        try:
            status.unregister_service_data(service_name)
        except Exception:
            pass
        print(f"[{service_name}] Service stopped", flush=True)


if __name__ == '__main__':
    run()

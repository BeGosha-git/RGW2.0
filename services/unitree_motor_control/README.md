# Сервис управления моторами Unitree

Сервис для управления моторами робота Unitree H1. Переключает робота в real mode, берет контроль над всеми моторами и предоставляет API для установки углов с плавными переходами.

## Функциональность

- Переключение робота в real mode через Motion Switcher
- Полный контроль над всеми 20 моторами H1
- Плавные переходы к целевым углам с настраиваемой скоростью
- REST API для управления моторами
- Поддержка приема данных от нейронной сети
- Настройки domain_id и network interface

## Настройки

В веб-интерфейсе RGW → Сервисы → unitree_motor_control:

- **id** (domain_id) - ID домена для DDS (по умолчанию: 0)
- **network** - Имя сетевого интерфейса (по умолчанию: "lo")

## API Эндпоинты

### POST /api/unitree_motor/set_angle
Устанавливает угол для одного мотора.

**Тело запроса:**
```json
{
  "motor_index": 0,
  "angle": 0.5,
  "velocity": 1.0
}
```

**Параметры:**
- `motor_index` (int, 0-19) - Индекс мотора
- `angle` (float) - Целевой угол в радианах
- `velocity` (float, опционально) - Скорость перехода в рад/с (0 = мгновенный переход)

### POST /api/unitree_motor/set_angles
Устанавливает углы для нескольких моторов.

**Тело запроса:**
```json
{
  "angles": {
    "0": 0.5,
    "1": 0.3,
    "2": 0.2
  },
  "velocity": 1.0
}
```

**Параметры:**
- `angles` (dict) - Словарь {motor_index: angle}
- `velocity` (float, опционально) - Скорость перехода в рад/с

### GET /api/unitree_motor/get_angles
Получает текущие и целевые углы всех моторов.

**Ответ:**
```json
{
  "success": true,
  "current_angles": {
    "0": 0.5,
    "1": 0.3,
    ...
  },
  "target_angles": {
    "0": 0.5,
    "1": 0.3,
    ...
  }
}
```

### POST /api/unitree_motor/neural_network
Устанавливает углы моторов из данных нейронной сети.

**Тело запроса (вариант 1 - список):**
```json
{
  "angles": [0.5, 0.3, 0.2, ...],
  "velocity": 1.0
}
```

**Тело запроса (вариант 2 - словарь):**
```json
{
  "angles": {
    "0": 0.5,
    "1": 0.3,
    "2": 0.2
  },
  "velocity": 1.0
}
```

**Параметры:**
- `angles` (list или dict) - Углы для всех или выбранных моторов
- `velocity` (float, опционально) - Скорость перехода в рад/с

## Индексы моторов H1

- 0: Right Hip Roll
- 1: Right Hip Pitch
- 2: Right Knee
- 3: Left Hip Roll
- 4: Left Hip Pitch
- 5: Left Knee
- 6: Waist Yaw
- 7: Left Hip Yaw
- 8: Right Hip Yaw
- 9: Not Used Joint
- 10: Left Ankle
- 11: Right Ankle
- 12: Right Shoulder Pitch
- 13: Right Shoulder Roll
- 14: Right Shoulder Yaw
- 15: Right Elbow
- 16: Left Shoulder Pitch
- 17: Left Shoulder Roll
- 18: Left Shoulder Yaw
- 19: Left Elbow

## Требования

- Unitree SDK2 Python (`/home/g100/unitree_sdk2_python`)
- Робот Unitree H1 в сети
- Правильно настроенный network interface

## Интеграция с нейронной сетью

Сервис поддерживает прием данных от нейронной сети через эндпоинт `/api/unitree_motor/neural_network`. 

### Особенности для нейросетей:

1. **Частичные обновления**: Можно отправлять углы только для выбранных моторов
2. **Смешивание потоков**: Система автоматически смешивает команды от разных источников (последняя команда имеет приоритет)
3. **Быстрые плавные переходы**: По умолчанию используется высокая скорость (10 рад/с) с экспоненциальным сглаживанием
4. **Автоматическая скорость**: Если скорость не указана, используется оптимальная скорость для нейросетей

### Примеры использования:

**Полное обновление (все 20 моторов):**
```python
import requests

angles = [0.5, 0.3, 0.2, ...]  # 20 углов
response = requests.post(
    'http://localhost:5000/api/unitree_motor/neural_network',
    json={
        'angles': angles,
        'velocity': 10.0  # рад/с (опционально, по умолчанию 10.0)
    }
)
```

**Частичное обновление (только выбранные моторы):**
```python
# Обновляем только моторы правого плеча
response = requests.post(
    'http://localhost:5000/api/unitree_motor/neural_network',
    json={
        'angles': {
            '12': 0.5,  # Right Shoulder Pitch
            '13': 0.3,  # Right Shoulder Roll
            '14': 0.2,  # Right Shoulder Yaw
            '15': 1.0   # Right Elbow
        },
        'velocity': 8.0  # рад/с
    }
)
```

**Или через обычный API с указанием источника:**
```python
response = requests.post(
    'http://localhost:5000/api/unitree_motor/set_angles',
    json={
        'angles': {'0': 0.5, '1': 0.3},  # Только нужные моторы
        'velocity': 10.0,
        'source': 'neural_network'  # Автоматически использует высокую скорость
    }
)
```

### Настройка параметров для нейросетей:

```python
# Получить текущую конфигурацию
config = requests.get('http://localhost:5000/api/unitree_motor/config').json()

# Установить скорость по умолчанию для нейросетей
requests.post(
    'http://localhost:5000/api/unitree_motor/config',
    json={
        'neural_network_velocity': 12.0,  # рад/с
        'smoothing_factor': 0.3  # 0-1, меньше = плавнее
    }
)
```

### Смешивание потоков:

Система автоматически обрабатывает одновременные команды от разных источников:
- Последняя команда для каждого мотора имеет приоритет
- Команды от разных источников не конфликтуют
- Каждый мотор может управляться независимо

## Логирование

Сервис выводит логи в формате:
```
[UnitreeMotorControl] <сообщение>
```

Основные события:
- Инициализация и подключение к роботу
- Переключение в real mode
- Ошибки подключения или управления
- Статус работы контроллера

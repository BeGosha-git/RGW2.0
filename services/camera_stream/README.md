# Camera Stream Service

Сервис для захвата видео с камер (RealSense и USB камеры) и трансляции через UDP и HTTP MJPEG.

## Возможности

- Автоматическое обнаружение USB камер через OpenCV
- Поддержка Intel RealSense камер (D435i, D435, и др.)
- Трансляция видео через HTTP MJPEG поток
- Отправка видео через UDP (опционально)
- REST API для управления потоками

## Установка зависимостей

```bash
pip install opencv-python pyrealsense2
```

Или используйте requirements.txt проекта:
```bash
pip install -r requirements.txt
```

## API Endpoints

### GET /api/cameras/list
Возвращает список всех доступных камер.

**Ответ:**
```json
{
  "success": true,
  "cameras": [
    {
      "id": "usb_0",
      "type": "usb",
      "name": "USB Camera 0",
      "device_path": "/dev/video0",
      "index": 0,
      "width": 640,
      "height": 480,
      "available": true
    },
    {
      "id": "realsense_0",
      "type": "realsense",
      "name": "RealSense D435i",
      "serial": "251843060650",
      "index": 0,
      "available": true
    }
  ],
  "count": 2
}
```

### GET /api/cameras/{camera_id}/mjpeg
Возвращает MJPEG поток с указанной камеры. Поток автоматически запускается если еще не запущен.

**Пример:**
```
http://localhost:5000/api/cameras/usb_0/mjpeg
http://localhost:5000/api/cameras/realsense_0/mjpeg
```

### POST /api/cameras/{camera_id}/start
Запускает поток с камеры.

**Тело запроса (опционально):**
```json
{
  "udp_port": 5005
}
```

### POST /api/cameras/{camera_id}/stop
Останавливает поток с камеры.

### GET /api/cameras/streams
Возвращает информацию о всех активных потоках.

## Использование в веб-интерфейсе

В веб-интерфейсе (RobotsPage) локальные камеры автоматически отображаются в режиме "Просмотр" (view mode). Камеры запускаются автоматически при открытии страницы.

## Структура сервиса

- `camera_stream.py` - основной файл сервиса
- `__init__.py` - инициализация модуля

## Запуск

Сервис автоматически запускается через `run.py` при старте системы, если он включен в `services.json`.

Для ручного запуска:
```bash
python services/camera_stream/camera_stream.py
```

## Примечания

- Сервис работает с опциональными зависимостями - если OpenCV или RealSense не установлены, соответствующие функции будут недоступны
- RealSense камеры требуют установки драйверов и библиотек Intel RealSense SDK
- USB камеры доступны через V4L2 (Video4Linux2)

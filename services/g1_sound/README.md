# Сервис звука для Unitree G1

Сервис воспроизведения звука на роботе Unitree G1 через DDS-топик `rt/audio_data`
(тип `unitree_go.msg.dds_.AudioData_`).

## Функциональность

- Воспроизведение коротких тонов-подсказок (beep, success, error, ding, attention, alert)
- Воспроизведение WAV-файлов из `data/sounds`
- Синтез речи (TTS) при наличии `espeak-ng`/`espeak` в системе
- Воспроизведение переданного по API аудио (16-бит PCM или WAV)
- Загрузка WAV-файлов на робота в `data/sounds`
- Остановка текущего воспроизведения
- Фоновый сервис, регистрирующий статус в `status.py`/`services_manager`

## Архитектура

Вся работа с нативным Unitree SDK / CycloneDDS выполняется **в отдельном
subprocess** (через `api/g1_sound_cli.py`), чтобы сбой нативной DDS-библиотеки
не мог уронить основной процесс `rgw2`. Это повторяет принятую в проекте схему
для G1-модулей (arm actions, loco, telemetry).

```
REST API (api/routes/sound.py)
   └── api/robot.py (RobotAPI)
         └── api/g1_sound_cli.py  (subprocess, DDS publish)
               └── unitree_sdk2py  (rt/audio_data, AudioData_)
```

## Настройки

В веб-интерфейсе RGW → Сервисы → g1_sound:

- **network** — имя сетевого интерфейса DDS (по умолчанию: `eth0`)
- **id** — domain_id DDS (по умолчанию: 0)
- **sample_rate** — частота дискретизации PCM (по умолчанию: 16000)

Если `network`/`id` не заданы, значения берутся из сервиса `unitree_motor_control`.

## API Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/robot/g1/sound/info` | Статус, список тонов и файлов |
| GET | `/api/robot/g1/sound/tones` | Список доступных тонов |
| GET | `/api/robot/g1/sound/files` | Список WAV-файлов |
| POST | `/api/robot/g1/sound/play/tone` | `{"name": "beep"}` — тон |
| POST | `/api/robot/g1/sound/play/file` | `{"filename": "hello.wav"}` — файл |
| POST | `/api/robot/g1/sound/play/speak` | `{"text": "Привет!"}` — TTS |
| POST | `/api/robot/g1/sound/play/pcm` | base64 PCM или WAV |
| POST | `/api/robot/g1/sound/upload` | Загрузка WAV (multipart) |
| POST | `/api/robot/g1/sound/stop` | Остановить воспроизведение |

### Пример: воспроизведение тона

```bash
curl -X POST http://<робот>:5000/api/robot/g1/sound/play/tone \
  -H 'Content-Type: application/json' \
  -d '{"name": "beep"}'
```

### Пример: синтез речи

```bash
curl -X POST http://<робот>:5000/api/robot/g1/sound/play/speak \
  -H 'Content-Type: application/json' \
  -d '{"text": "Привет! Я робот G1."}'
```

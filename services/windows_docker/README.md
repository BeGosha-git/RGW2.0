# Windows Docker Service

Эта папка содержит все файлы, связанные с Docker для Windows.

## Файлы

- `Dockerfile` - Docker образ для роботов
- `docker-compose.yaml` - Конфигурация Docker Compose для запуска 6 роботов

## Использование

Docker Compose запускается автоматически через `main.py` при обнаружении Windows системы.

Для ручного запуска:
```bash
cd services/windows_docker
docker-compose up -d --build
```

Для остановки:
```bash
cd services/windows_docker
docker-compose down
```

## Структура

- `context: ../..` - контекст сборки (корень проекта)
- `dockerfile: services/windows_docker/Dockerfile` - путь к Dockerfile относительно context
- `volumes: ../../:/app` - монтирование корня проекта в контейнер

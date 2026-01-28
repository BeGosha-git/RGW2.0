FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей (минимальный набор)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements.txt и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всех файлов проекта
COPY . .

# Создание необходимых директорий
RUN mkdir -p services/web/build data

# Установка переменных окружения из docker-compose если нужно
ARG ROBOT_ID=0001
ARG ROBOT_TYPE=PC
ARG ROBOT_GROUP=white
ARG VERSION_PRIORITY=STABLE

ENV ROBOT_ID=${ROBOT_ID}
ENV ROBOT_TYPE=${ROBOT_TYPE}
ENV ROBOT_GROUP=${ROBOT_GROUP}
ENV VERSION_PRIORITY=${VERSION_PRIORITY}

# Скрипт init_settings.py будет скопирован вместе с остальными файлами

EXPOSE 5000 80

# Обновляем settings.json при запуске контейнера, затем запускаем main.py
# Используем unbuffered Python для корректного вывода логов
# Устанавливаем переменную окружения для определения Docker
ENV DOCKER_CONTAINER=true
ENV PYTHONUNBUFFERED=1

CMD python /app/init_settings.py && python -u /app/main.py

FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

COPY requirements.txt .

# Устанавливаем Python пакеты
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

# Копируем исходный код проекта
COPY . .

# Делаем скрипт запуска исполняемым
RUN chmod +x /app/entrypoint.sh

# Устанавливаем переменные окружения
ENV SERVER_HOST=0.0.0.0
ENV SERVER_PORT=8000
ENV N8N_FILES_DIR=/app/data
ENV BROWSER_HEADLESS=true
ENV PYTHONPATH=/app

# Создаем директорию для данных
RUN mkdir -p /app/data

# Открываем порт
EXPOSE 8000

# Используем скрипт входа
ENTRYPOINT ["/app/entrypoint.sh"]

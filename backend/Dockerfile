FROM python:3.12-slim

# Системные зависимости (нужны для psycopg2, asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Сначала копируем только зависимости — слой кешируется если requirements не менялся
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Папка для медиафайлов + права + исполняемый entrypoint
RUN mkdir -p /app/media \
    && chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]

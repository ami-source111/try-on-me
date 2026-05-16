#!/bin/bash
# Деплой на Hetzner: git pull + пересборка + перезапуск
# Запускать из папки try-on-me/ на сервере
set -e

echo "🔄 Pulling latest code..."
git pull origin main

echo "🐳 Rebuilding and restarting containers..."
docker compose pull          # обновить postgres/nginx образы если вышли новые
docker compose up -d --build # пересобрать app и запустить всё

echo "⏳ Waiting for app to be healthy..."
sleep 5
docker compose ps

echo "✅ Done! Logs:"
docker compose logs app --tail=20

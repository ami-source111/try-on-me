# Try on Me — контекст проекта

## Что это

Сервис виртуальной примерки одежды. MVP для питча ритейлерам.

Пользователь устанавливает Chrome-расширение, заходит на сайт магазина — рядом с крупными картинками одежды (≥300×300px) появляется кнопка «Try on me». После нажатия AI генерирует короткое видео: пользователь в этой одежде.

**Цель MVP** — показать работающий прототип ритейлерам. Ритейлер ставит расширение, заходит на свой сайт — видит продукт в действии.

---

## Текущий статус (май 2026)

| Этап | Содержание | Статус |
|---|---|---|
| 1 | Backend: FastAPI + PostgreSQL + Docker | ✅ Готово, задеплоено |
| 2 | Сессии без авторизации (cookie/UUID) | ✅ Готово |
| 3 | AI-пайплайн: cat-vton + LTX Video | ✅ Работает end-to-end |
| 4 | Chrome-расширение | ⏳ Следующий этап |
| 5 | Интеграция и тесты | ⏳ |
| 6 | Подготовка демо | ⏳ |

**Пайплайн проверен** — статус `done`, видео генерируется (~3 мин). Тест 16.05.2026.

---

## Сервер (Hetzner)

- **IP**: 116.203.138.149
- **Домен**: amirov.mooo.com (A-запись настроена, HTTPS не настроен)
- **OS**: Ubuntu 22
- **Проект**: `/opt/try-on-me-new/`
- **Nginx**: системный (не Docker), конфиг: `/etc/nginx/sites-available/tryon`
- **Media volume**: `/var/lib/docker/volumes/try-on-me-new_media_data/_data/`
- **Docker**: `docker compose` из `/opt/try-on-me-new/`

### Ключевые команды на сервере

```bash
cd /opt/try-on-me-new
docker compose ps                        # статус контейнеров
docker compose logs app --tail=30        # логи приложения
docker compose up -d --build             # пересборка и запуск
docker compose exec app python -c "..."  # выполнить Python в контейнере

# Проверить API
curl http://116.203.138.149/health

# Тест полного пайплайна
SESSION=$(curl -s -X POST http://116.203.138.149/sessions/photo \
  -F "file=@/usr/share/pixmaps/debian-logo.png" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
JOB=$(curl -s -X POST http://116.203.138.149/tryon \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"$SESSION\", \"clothing_image_url\": \"http://116.203.138.149/media/test-shirt.jpg\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
watch -n 20 "curl -s http://116.203.138.149/tryon/$JOB | python3 -m json.tool"
```

### Конфигурация сервера

```bash
# /etc/nginx/sites-available/tryon — ключевое:
# proxy_pass http://127.0.0.1:8765;
# alias /var/lib/docker/volumes/try-on-me-new_media_data/_data/;

# После изменений nginx:
nginx -t && systemctl reload nginx

# Docker daemon DNS (нужен для внешних запросов из контейнера):
# /etc/docker/daemon.json → {"dns": ["8.8.8.8", "1.1.1.1"]}
```

---

## Архитектура

```
Chrome Extension  →  Backend API (FastAPI)  →  fal.ai (AI)
                            ↕
                    PostgreSQL + /app/media
```

### Компоненты

| Компонент | Технология |
|---|---|
| Backend API | Python 3.12 + FastAPI |
| База данных | PostgreSQL 16 (Docker) |
| Хранилище медиа | Локальный диск `/app/media` → nginx |
| AI | fal.ai: cat-vton + ltx-video |
| Хостинг | Hetzner VPS + Docker Compose |
| Nginx | Системный (не в Docker) |

---

## AI-пайплайн

### Модели

| Шаг | Модель | Цена | Параметры |
|---|---|---|---|
| 1 — Try-on | `fal-ai/cat-vton` | ~$0.03 | `human_image_url`, `garment_image_url`, `cloth_type: "upper"` |
| 2 — Видео | `fal-ai/ltx-video` | $0.02 | `image_url`, `prompt` |

**Промпт для видео:**
```
A person wearing the outfit, slowly rotating 360 degrees on a white
cyclorama studio background, smooth motion, professional studio lighting
```

**Важно:** одежду скачиваем сами (контейнер), загружаем в fal.ai storage — fal.ai не всегда может достучаться до внешних CDN.

### Статусы job

`pending` → `processing_tryon` → `processing_video` → `done` / `failed`

---

## API эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Healthcheck |
| POST | `/sessions/photo` | Загрузить фото, получить session_id |
| GET | `/sessions/me?session_id=UUID` | Проверить сессию |
| POST | `/tryon` | `{session_id, clothing_image_url}` → `{job_id}` |
| GET | `/tryon/{job_id}` | Статус и video_url |

**Документация:** http://116.203.138.149/docs

---

## Схема БД

### `users`
- `id` (UUID PK) — это и есть session_id
- `photo_url` (TEXT) — путь к фото в /app/media/photos/
- `created_at`, `updated_at`

### `tryon_jobs`
- `id` (UUID PK)
- `user_id` (FK → users.id)
- `clothing_image_url` — исходный URL с сайта магазина
- `tryon_image_url` — результат шага 1 (URL fal.ai)
- `video_url` — результат шага 2 (локальный URL /media/videos/...)
- `status` — pending/processing_tryon/processing_video/done/failed
- `error_message`
- `created_at`, `completed_at`

---

## Переменные среды (backend/.env)

```env
DATABASE_URL=postgresql://tryonme:PASS@db:5432/tryonme
DB_PASSWORD=...                # в корневом .env для docker-compose
FAL_KEY=...                    # fal.ai API key (формат: uuid:hex)
MEDIA_PATH=/app/media
MEDIA_URL=http://116.203.138.149/media
BACKEND_URL=http://116.203.138.149
```

---

## Структура проекта

```
try-on-me/
├── context.md                  ← этот файл
├── docker-compose.yml          ← app + db, порт 8765, dns 8.8.8.8
├── nginx/
│   └── nginx.conf              ← шаблон (на сервере отдельный файл)
└── backend/
    ├── Dockerfile
    ├── entrypoint.sh           ← alembic upgrade head → uvicorn
    ├── requirements.txt
    ├── .env.example
    ├── alembic/
    │   └── versions/
    │       ├── 001_initial.py
    │       └── 002_simplify_users.py
    └── app/
        ├── main.py             ← FastAPI app, CORS
        ├── config.py           ← pydantic-settings
        ├── database.py         ← async SQLAlchemy
        ├── models/
        │   ├── user.py
        │   └── tryon_job.py
        ├── api/
        │   ├── health.py
        │   ├── sessions.py     ← POST /sessions/photo, GET /sessions/me
        │   └── tryon.py        ← POST /tryon, GET /tryon/{id}
        └── services/
            ├── storage.py      ← локальный файловый storage
            └── pipeline.py     ← AI-пайплайн (cat-vton + ltx-video)
```

---

## GitHub

- **Репо**: https://github.com/ami-source111/try-on-me
- **Структура**: файлы в корне (не вложенные)
- **Git root на сервере**: `/opt/try-on-me-new/`

### Деплой на сервер

```bash
cd /opt/try-on-me-new
git pull
docker compose up -d --build
```

---

## Известные особенности и решения

| Проблема | Решение |
|---|---|
| Docker не резолвит внешние домены | `/etc/docker/daemon.json` → dns 8.8.8.8; docker compose dns: [8.8.8.8, 1.1.1.1] |
| Nginx не читает media volume | `chmod o+x` по всей цепочке до `_data/` |
| Port 8000 зависает после краша | `fuser -k 8000/tcp` или смена порта (сейчас 8765) |
| git root был в home dir | Пересоздали .git в try-on-me/, force push |
| Два FAL_KEY в .env | Дублирующая строка с кириллицей — удалить |
| Alembic блокирует async event loop | Вынесли в `entrypoint.sh` ДО uvicorn |

---

## Следующий этап: Chrome Extension

### Что нужно реализовать

**Файлы:**
- `manifest.json` (MV3)
- `content.js` — инжекция кнопки на img ≥ 300×300
- `popup.html` / `popup.js` — 4 состояния
- `background.js` — polling каждые 5 сек

**Состояния попапа:**
1. Не авторизован → кнопка «Загрузить фото»
2. Загрузка фото → spinner
3. Примерка в процессе → spinner + "~60 сек"
4. Готово → видеоплеер

**Auth flow:**
- Пользователь загружает фото через попап (`POST /sessions/photo`)
- Получает `session_id`, сохраняет в `chrome.storage.local`
- При нажатии «Try on me» → `POST /tryon` с session_id

**API base URL:** `http://116.203.138.149` (до настройки HTTPS/домена)

### Ключевые моменты

- `MutationObserver` для SPA-сайтов
- Кнопка инжектируется как оверлей поверх `<img>`
- Polling через `background.js` → `chrome.runtime.sendMessage` → обновление попапа
- CORS в FastAPI уже настроен (`allow_origins=["*"]`)

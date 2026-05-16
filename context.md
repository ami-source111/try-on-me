# Try on Me — контекст проекта

## Что это

Сервис виртуальной примерки одежды. MVP для питча ритейлерам.

Пользователь устанавливает Chrome-расширение, заходит на любой сайт одежды — рядом с крупными картинками появляется кнопка «Try on me 👗». После нажатия генерируется 3-секундное видео: пользователь в этой одежде медленно поворачивается на белом фоне.

## Цель MVP

Показать работающий прототип ритейлерам. Ритейлер ставит расширение, заходит на свой сайт и видит продукт в действии прямо на своих карточках товаров. Без изменений на стороне сайта.

---

## Архитектура

```
Chrome Extension  →  Backend API (FastAPI)  →  fal.ai (AI)
      ↕                      ↕
 Пользователь          Telegram Bot + R2
```

### Компоненты

| Компонент | Технология | Назначение |
|---|---|---|
| Chrome Extension | MV3, Vanilla JS | Инжекция кнопки, показ видео в попапе |
| Backend API | Python 3.12 + FastAPI | Оркестрация, БД, запуск AI |
| Telegram Bot | python-telegram-bot v20 | Авторизация, фото пользователя, доставка видео |
| AI | fal.ai SDK | Виртуальная примерка + генерация видео |
| База данных | PostgreSQL + SQLAlchemy async | Пользователи, задачи |
| Хранилище | Cloudflare R2 | Фото пользователей, готовые видео |
| Хостинг | Railway | Backend + PostgreSQL |

---

## AI-пайплайн (fal.ai)

**Модели (дешёвые, для MVP):**

| Шаг | Модель | Цена | Назначение |
|---|---|---|---|
| 1 — Try-on | `fal-ai/cat-vton` | ~$0.02–0.03 | Статичное фото пользователя в одежде |
| 2 — Видео | `fal-ai/wan/v2.1/1.3b/image-to-video` | ~$0.03–0.05 | 3-секундное видео с поворотом |

**Промпт для видео:**
```
A person wearing the outfit, slowly rotating 360 degrees on a white cyclorama background, studio lighting, smooth motion, 3 seconds
```

**Итого за одну примерку: ~$0.05–0.08**

При необходимости (для финального демо) заменить на платные модели:
- `fashn/tryon` вместо cat-vton
- `fal-ai/kling-video/v1.6/standard/image-to-video` вместо wan

---

## Ключевые решения

### Chrome Extension
- Manifest V3
- Кнопка инжектируется рядом с `<img>` с `naturalWidth ≥ 300` и `naturalHeight ≥ 300`
- MutationObserver — работает с SPA и динамическим контентом
- Попап показывает 4 состояния: не авторизован / ожидание / загрузка / видео готово
- Polling бэкенда каждые 5 секунд через background service worker

### Авторизация
- Только через Telegram-бот — никаких отдельных логинов
- Пользователь пишет `/start` → загружает фото → бот генерирует auth_token (UUID, живёт 1 час)
- Расширение открывает deep link → бэкенд отдаёт `user_id` → расширение сохраняет в `chrome.storage`
- Фото загружается один раз, обновляется командой `/photo`

### Доставка результата
- **Одновременно**: видео показывается в попапе расширения И приходит в Telegram-бот
- Polling: расширение опрашивает `GET /tryon/{job_id}` каждые 5 сек

### Валидация фото
- **Не делаем в MVP** — пропускаем любое присланное фото

### История примерок
- Сохраняются в БД (таблица `tryon_jobs`), видео хранится в R2
- В MVP нет UI для истории — просто хранится

---

## User Flow

### Онбординг (первый раз)
1. Установить расширение Chrome
2. В попапе — нажать «Войти через Telegram»
3. В боте: `/start` → прислать фото в полный рост
4. В боте: нажать «Подключить к расширению» → расширение авторизовано

### Примерка
1. Зайти на сайт магазина одежды
2. Кнопка «Try on me 👗» появляется рядом с крупными картинками
3. Нажать кнопку → в попапе спиннер «~60 сек»
4. Видео приходит в Telegram + показывается в попапе

---

## API эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Healthcheck для Railway |
| POST | `/webhook/telegram` | Webhook от Telegram |
| GET | `/auth/connect?token=XXX` | Расширение обменивает токен на user_id |
| POST | `/tryon` | Запустить примерку `{user_id, clothing_image_url}` |
| GET | `/tryon/{job_id}` | Статус и результат задачи |

---

## Схема БД

### `users`
| Поле | Тип |
|---|---|
| id | UUID PK |
| telegram_user_id | BIGINT UNIQUE |
| telegram_username | VARCHAR(64) |
| photo_url | TEXT |
| auth_token | UUID |
| auth_token_expires_at | TIMESTAMP |
| created_at / updated_at | TIMESTAMP |

### `tryon_jobs`
| Поле | Тип |
|---|---|
| id | UUID PK |
| user_id | UUID FK |
| clothing_image_url | TEXT |
| tryon_image_url | TEXT |
| video_url | TEXT |
| status | VARCHAR(32): pending / processing_tryon / processing_video / done / failed |
| error_message | TEXT |
| created_at / completed_at | TIMESTAMP |

---

## Переменные среды

```env
DATABASE_URL=postgresql://user:password@host:5432/tryonme
FAL_KEY=...
TG_BOT_TOKEN=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=try-on-me
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
BACKEND_URL=https://your-app.railway.app
```

---

## Скоуп MVP (что делаем)

- [x] Chrome Extension: инжекция кнопки, попап, auth flow
- [x] Telegram Bot: авторизация, загрузка фото, доставка видео
- [x] FastAPI Backend: все эндпоинты
- [x] AI Pipeline: cat-vton → wan/1.3b video
- [x] R2 хранилище
- [x] Railway деплой

## За скоупом MVP (не делаем)

- Валидация фото пользователя
- История примерок с UI
- Chrome Web Store публикация
- Биллинг и SaaS
- Мобильная версия
- White-label для ритейлеров

---

## Этапы разработки

| Этап | Содержание | Дней |
|---|---|---|
| 1 | Бэкенд: скелет, БД, деплой, стабы API | 2 |
| 2 | Telegram-бот: auth, фото, R2 | 2 |
| 3 | AI-пайплайн: fal.ai интеграция | 2 |
| 4 | Chrome Extension | 3 |
| 5 | Сквозная интеграция и тесты | 2 |
| 6 | Подготовка демо | 1 |

**Итого: ~12 рабочих дней**

---

## Полезные ссылки

- fal.ai cat-vton: https://fal.ai/models/fal-ai/cat-vton
- fal.ai wan video: https://fal.ai/models/fal-ai/wan/v2.1/1.3b/image-to-video
- fal.ai Python SDK: https://github.com/fal-ai/fal/tree/main/projects/fal-client
- python-telegram-bot: https://docs.python-telegram-bot.org/
- Railway: https://railway.app
- Cloudflare R2: https://developers.cloudflare.com/r2/

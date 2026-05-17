"""Local filesystem storage helpers.

Файлы хранятся в MEDIA_PATH (внутри Docker — /app/media).
Отдаются nginx напрямую из той же папки (volume media_data).
Публичный URL = MEDIA_URL + "/" + key.
"""
import uuid
from pathlib import Path

import httpx

from app.config import settings


def _ensure(subdir: str) -> Path:
    """Создать подпапку в media_path если не существует."""
    p = Path(settings.media_path) / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


def upload_bytes(data: bytes, key: str) -> str:
    """
    Сохранить байты по относительному пути key внутри media_path.
    Возвращает публичный URL.
    """
    dest = Path(settings.media_path) / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"{settings.media_url.rstrip('/')}/{key}"


def upload_image(data: bytes, prefix: str = "photos") -> str:
    """Сохранить изображение, вернуть публичный URL."""
    key = f"{prefix}/{uuid.uuid4()}.jpg"
    return upload_bytes(data, key)


def upload_video(data: bytes) -> str:
    """Сохранить видео, вернуть публичный URL."""
    key = f"videos/{uuid.uuid4()}.mp4"
    return upload_bytes(data, key)


async def download_url(url: str, timeout: float = 60.0, retries: int = 3) -> bytes:
    """Скачать файл по URL (async), с retry при таймауте."""
    import asyncio
    import logging
    logger = logging.getLogger(__name__)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exc = e
            logger.warning(f"download_url timeout (attempt {attempt}/{retries}): {url}")
            if attempt < retries:
                await asyncio.sleep(3 * attempt)
    raise last_exc

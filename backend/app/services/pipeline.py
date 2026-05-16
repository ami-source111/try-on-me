"""
AI-пайплайн: виртуальная примерка + генерация видео через fal.ai

Шаг 1: fal-ai/cat-vton      — фото пользователя в одежде (~20–30 сек)
Шаг 2: fal-ai/wan/v2.1/1.3b/image-to-video — 5-секундное видео (~30–60 сек)

Запускается в фоне (FastAPI BackgroundTasks) после создания TryonJob.
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fal_client
import httpx

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tryon_job import JobStatus, TryonJob
from app.models.user import User
from app.services.storage import upload_video, download_url

logger = logging.getLogger(__name__)

VIDEO_PROMPT = (
    "A person wearing the outfit, slowly rotating 360 degrees on a white "
    "cyclorama studio background, smooth motion, professional studio lighting, "
    "clean background, fashion photography style"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _set_status(job_id: str, status: str, **fields):
    """Обновить статус и поля job в БД."""
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TryonJob).where(TryonJob.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if not job:
            return
        job.status = status
        for k, v in fields.items():
            setattr(job, k, v)
        if status in (JobStatus.DONE, JobStatus.FAILED):
            job.completed_at = datetime.now(timezone.utc)
        await db.commit()


async def _upload_bytes_to_fal(data: bytes, suffix: str = ".jpg") -> str:
    """Загрузить байты во временный файл и отправить в fal.ai storage."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        url = await fal_client.upload_file_async(tmp)
        return url
    finally:
        os.unlink(tmp)



def _local_photo_bytes(photo_url: str) -> bytes:
    """
    Прочитать фото пользователя с диска.
    photo_url вида http://host/media/photos/xxx.jpg → media_path/photos/xxx.jpg
    """
    # Берём относительный путь после /media/
    if "/media/" in photo_url:
        rel = photo_url.split("/media/", 1)[1]
    else:
        rel = Path(photo_url).name
    full_path = Path(settings.media_path) / rel
    if not full_path.exists():
        raise FileNotFoundError(f"User photo not found on disk: {full_path}")
    return full_path.read_bytes()


# ── Пайплайн ─────────────────────────────────────────────────────────────────

async def run_pipeline(job_id: str):
    """
    Запустить полный пайплайн для job_id.
    Вызывается из BackgroundTasks после создания TryonJob.
    """
    logger.info(f"[{job_id}] Pipeline started")

    # Загрузить данные из БД
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(
            select(TryonJob).where(TryonJob.id == uuid.UUID(job_id))
        )
        job = job_result.scalar_one_or_none()
        if not job:
            logger.error(f"[{job_id}] Job not found")
            return

        user_result = await db.execute(
            select(User).where(User.id == job.user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.photo_url:
            await _set_status(job_id, JobStatus.FAILED, error_message="User photo not found")
            return

        clothing_url = job.clothing_image_url
        photo_url = user.photo_url

    try:
        # ── Шаг 1: виртуальная примерка (cat-vton) ───────────────────────────
        await _set_status(job_id, JobStatus.PROCESSING_TRYON)
        logger.info(f"[{job_id}] Step 1: uploading user photo to fal.ai")

        # Загружаем только фото пользователя — одежду fal.ai скачивает сам по URL
        photo_bytes = _local_photo_bytes(photo_url)
        person_fal_url = await _upload_bytes_to_fal(photo_bytes, ".jpg")

        logger.info(f"[{job_id}] Step 1: running cat-vton (garment_url={clothing_url})")
        tryon_result = await fal_client.run_async(
            "fal-ai/cat-vton",
            arguments={
                "human_image_url": person_fal_url,
                "garment_image_url": clothing_url,   # fal.ai скачивает сам
                "cloth_type": "upper_body",
            },
        )
        tryon_image_url = tryon_result["image"]["url"]
        logger.info(f"[{job_id}] Try-on image ready: {tryon_image_url}")

        # ── Шаг 2: генерация видео (wan 1.3b) ────────────────────────────────
        await _set_status(
            job_id, JobStatus.PROCESSING_VIDEO, tryon_image_url=tryon_image_url
        )
        logger.info(f"[{job_id}] Step 2: running wan video")

        video_result = await fal_client.run_async(
            "fal-ai/wan/v2.1/1.3b/image-to-video",
            arguments={
                "image_url": tryon_image_url,
                "prompt": VIDEO_PROMPT,
                "num_frames": 49,           # ~5 сек при 10 fps (минимум модели)
                "frames_per_second": 10,
                "resolution": "480p",       # дешевле чем 720p
                "num_inference_steps": 30,
            },
        )
        video_fal_url = video_result["video"]["url"]
        logger.info(f"[{job_id}] Video ready: {video_fal_url}")

        # ── Сохранить видео локально ──────────────────────────────────────────
        video_bytes = await download_url(video_fal_url, timeout=60.0)
        local_video_url = upload_video(video_bytes)

        await _set_status(job_id, JobStatus.DONE, video_url=local_video_url)
        logger.info(f"[{job_id}] Pipeline complete → {local_video_url}")

    except Exception as e:
        msg = str(e)
        logger.error(f"[{job_id}] Pipeline failed: {msg}", exc_info=True)
        await _set_status(job_id, JobStatus.FAILED, error_message=msg)



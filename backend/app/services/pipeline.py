"""
AI-пайплайн: виртуальная примерка + генерация видео через fal.ai

Шаг 1: fal-ai/nano-banana-pro/edit  — фото пользователя в одежде (~30–60 сек)
Шаг 2: fal-ai/ltx-2.3/image-to-video/fast — видео 6 сек (~60–90 сек, $0.02)

ВАЖНО: суффикс /edit обязателен для nano-banana — без него работает как text-to-image
       и игнорирует загруженные картинки!

Запускается в фоне (FastAPI BackgroundTasks) после создания TryonJob.
"""
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fal_client

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.tryon_job import JobStatus, TryonJob
from app.models.user import User
from app.services.storage import download_url, upload_video

logger = logging.getLogger(__name__)

TRYON_PROMPT = (
    "Use the person from IMAGE 1 as the identity reference and the outfit from IMAGE 2 as the clothing reference. "
    "Create a realistic full-body fashion try-on image where the person from IMAGE 1 is wearing the exact outfit from IMAGE 2. "
    "Preserve the person's face, facial features, hairstyle, body shape, height proportions, skin tone, age, and natural appearance as accurately as possible. "
    "The final pose should be neutral, relaxed, and suitable for an online clothing fitting preview: standing upright, facing the camera, arms naturally positioned slightly away from the body or relaxed along the sides. "
    "If the clothing reference has hands in pockets, crossed arms, hidden sleeves, cropped parts, folds, or occluded areas, intelligently reconstruct the missing parts of the garment so the outfit looks complete, natural, and physically plausible. "
    "Transfer the clothing accurately: keep the same fabric, color, texture, seams, collar, sleeves, buttons, zipper, pockets, length, silhouette, fit, wrinkles, drape, and overall style from IMAGE 2. "
    "The clothing should conform naturally to the body of the person from IMAGE 1 without changing their body type. "
    "Use clean studio lighting, neutral background, realistic shadows, high-resolution commercial fashion photography style. "
    "The result should look like a real person trying on the outfit, not a face swap, not a mannequin, not AI-generated. "
    "Important constraints: "
    "Do not change the person's identity. "
    "Do not beautify or stylize the face. "
    "Do not alter skin color or body proportions. "
    "Do not copy the pose from IMAGE 2 if it hides the outfit. "
    "Do not distort hands, face, legs, or clothing edges. "
    "Do not invent a different outfit. "
    "Do not add accessories unless they are clearly part of the outfit in IMAGE 2. "
    "Keep the final image realistic, natural, and usable for an e-commerce virtual fitting preview."
)

TRYON_NEGATIVE_PROMPT = (
    "different person, different face, different skin tone, face swap, mannequin, "
    "cartoon, deformed, ugly, distorted hands, distorted face, distorted legs, "
    "body modification, stylized, beautified, AI-generated look, extra accessories"
)

VIDEO_PROMPT = (
    "Use the uploaded image as the reference. Create a simple, realistic clothing showcase video "
    "on a pure white seamless studio background. "
    "The person stands centered in frame and performs a slow, smooth full 360-degree turn while "
    "making tiny natural steps in place. The movement must start and end in exactly the same "
    "front-facing position, with the same stance and body alignment, so the video can loop seamlessly. "
    "Keep the person's identity, face, hairstyle, body shape, and the outfit exactly the same as in "
    "the reference image. Preserve the clothing accurately, including fit, length, color, fabric "
    "behavior, shoes, and accessories. "
    "Camera: static full-body shot, straight-on, eye-level, centered composition. "
    "Background: pure white studio background, clean and minimal, with soft subtle studio shadows only. "
    "Motion: very simple and minimal, slow smooth 360-degree rotation, tiny steps in place, minimal "
    "arm movement, realistic fabric movement. "
    "Style: photorealistic, clean e-commerce studio presentation, neutral lighting, high detail. "
    "Important: the motion should be continuous, even, and symmetrical, with no abrupt acceleration "
    "or stop. The ending must align perfectly with the beginning for a seamless loop."
)

VIDEO_NEGATIVE_PROMPT = (
    "no walking toward camera, no posing, no dancing, no dramatic gestures, no background changes, "
    "no extra people, no text, no logos, no camera movement, no face distortion, no body deformation, "
    "no extra limbs, no flicker, no outfit changes"
)

os.environ.setdefault("FAL_KEY", settings.fal_key)


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
    """Загрузить байты в fal.ai storage и вернуть URL."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        url = await fal_client.upload_file_async(tmp)
        return url
    finally:
        os.unlink(tmp)


def _local_photo_bytes(photo_url: str) -> bytes:
    """Прочитать фото пользователя с диска по его публичному URL."""
    if "/media/" in photo_url:
        rel = photo_url.split("/media/", 1)[1]
    else:
        rel = Path(photo_url).name
    full_path = Path(settings.media_path) / rel
    if not full_path.exists():
        raise FileNotFoundError(f"User photo not found: {full_path}")
    return full_path.read_bytes()


# ── Пайплайн ─────────────────────────────────────────────────────────────────

async def run_pipeline(job_id: str):
    """
    Полный AI-пайплайн для job_id.
    Вызывается из BackgroundTasks после создания TryonJob.
    """
    logger.info(f"[{job_id}] Pipeline started")

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
        import asyncio

        # ── Шаг 1: виртуальная примерка (cat-vton) ───────────────────────────
        await _set_status(job_id, JobStatus.PROCESSING_TRYON)
        logger.info(f"[{job_id}] Uploading images to fal.ai")

        photo_bytes = _local_photo_bytes(photo_url)
        clothing_bytes = await download_url(clothing_url, timeout=30.0)

        person_fal_url, garment_fal_url = await asyncio.gather(
            _upload_bytes_to_fal(photo_bytes, ".jpg"),
            _upload_bytes_to_fal(clothing_bytes, ".jpg"),
        )

        logger.info(f"[{job_id}] Running nano-banana-pro/edit")
        tryon_result = await fal_client.run_async(
            "fal-ai/nano-banana-pro/edit",
            arguments={
                "image_urls": [person_fal_url, garment_fal_url],
                "prompt": TRYON_PROMPT,
                "negative_prompt": TRYON_NEGATIVE_PROMPT,
                "num_inference_steps": 30,
                "guidance_scale": 5,
            },
        )
        tryon_image_url = tryon_result["images"][0]["url"]
        logger.info(f"[{job_id}] Try-on done: {tryon_image_url}")

        # ── Шаг 2: генерация видео (LTX 2.3, 6 сек, ~$0.02) ─────────────────
        await _set_status(
            job_id, JobStatus.PROCESSING_VIDEO, tryon_image_url=tryon_image_url
        )
        logger.info(f"[{job_id}] Running ltx-2.3/image-to-video/fast")

        # Загружаем result try-on в fal.ai storage (гарантирует доступность URL)
        tryon_bytes = await download_url(tryon_image_url, timeout=30.0)
        tryon_fal_url = await _upload_bytes_to_fal(tryon_bytes, ".jpg")

        video_result = await fal_client.run_async(
            "fal-ai/ltx-2.3/image-to-video/fast",
            arguments={
                "image_url": tryon_fal_url,
                "prompt": VIDEO_PROMPT,
                "duration": 6,
                "generate_audio": True,
            },
        )
        video_fal_url = video_result["video"]["url"]
        logger.info(f"[{job_id}] Video done: {video_fal_url}")

        # ── Сохранить видео локально ──────────────────────────────────────────
        video_bytes = await download_url(video_fal_url, timeout=60.0)
        local_video_url = upload_video(video_bytes)

        await _set_status(job_id, JobStatus.DONE, video_url=local_video_url)
        logger.info(f"[{job_id}] Pipeline complete: {local_video_url}")

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline failed: {e}", exc_info=True)
        await _set_status(job_id, JobStatus.FAILED, error_message=str(e))

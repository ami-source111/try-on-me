import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tryon_job import TryonJob, JobStatus
from app.models.user import User

router = APIRouter(tags=["tryon"])


class TryonRequest(BaseModel):
    session_id: str          # UUID из chrome.storage расширения
    clothing_image_url: str  # URL картинки с сайта магазина


class TryonResponse(BaseModel):
    job_id: str
    status: str
    estimated_seconds: int = 60


class TryonStatusResponse(BaseModel):
    job_id: str
    status: str
    video_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


@router.post("/tryon", response_model=TryonResponse)
async def create_tryon(
    request: TryonRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Запустить примерку.
    Вызывается Chrome-расширением при нажатии кнопки «Try on me».
    """
    try:
        sid = uuid.UUID(request.session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id format")

    result = await db.execute(select(User).where(User.id == sid))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Upload your photo first via POST /sessions/photo",
        )
    if not user.photo_url:
        raise HTTPException(
            status_code=400,
            detail="No photo found for this session. Upload via POST /sessions/photo",
        )

    job = TryonJob(
        user_id=user.id,
        clothing_image_url=request.clothing_image_url,
        status=JobStatus.PENDING,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Запустить AI-пайплайн в фоне
    from app.services.pipeline import run_pipeline
    background_tasks.add_task(run_pipeline, str(job.id))

    return TryonResponse(job_id=str(job.id), status=job.status)


@router.get("/tryon/{job_id}", response_model=TryonStatusResponse)
async def get_tryon_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Статус примерки. Расширение опрашивает каждые 5 секунд.

    Статусы:
        pending             — в очереди
        processing_tryon    — шаг 1: cat-vton
        processing_video    — шаг 2: wan video
        done                — готово, video_url содержит ссылку
        failed              — ошибка
    """
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid job_id format")

    result = await db.execute(select(TryonJob).where(TryonJob.id == jid))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return TryonStatusResponse(
        job_id=str(job.id),
        status=job.status,
        video_url=job.video_url,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )

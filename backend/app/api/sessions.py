"""
Сессии без авторизации.

POST /sessions/photo  — загрузить фото, получить session_id
GET  /sessions/me     — проверить сессию и наличие фото
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import storage

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_SIZE_MB = 10


@router.post("/photo")
async def upload_photo(
    file: UploadFile = File(...),
    session_id: str | None = None,          # передать если обновляем фото
    db: AsyncSession = Depends(get_db),
):
    """
    Загрузить фото пользователя.

    - Если session_id не передан — создаётся новая сессия.
    - Если передан — фото обновляется.
    - Возвращает session_id, который расширение сохраняет в chrome.storage.
    """
    # Валидация типа файла
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Use JPEG, PNG or WebP.",
        )

    # Читаем файл и проверяем размер
    data = await file.read()
    if len(data) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {MAX_SIZE_MB}MB.",
        )

    # Найти или создать пользователя
    user = None
    if session_id:
        try:
            sid = uuid.UUID(session_id)
            result = await db.execute(select(User).where(User.id == sid))
            user = result.scalar_one_or_none()
        except ValueError:
            pass  # невалидный UUID — создадим нового

    if not user:
        user = User()
        db.add(user)

    # Сохранить фото
    photo_url = storage.upload_image(data, prefix="photos")
    user.photo_url = photo_url
    await db.commit()
    await db.refresh(user)

    return {
        "session_id": str(user.id),
        "has_photo": True,
        "photo_url": photo_url,
    }


@router.get("/me")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Проверить сессию. Расширение вызывает при старте попапа,
    чтобы понять — авторизован пользователь или нет.
    """
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid session_id format")

    result = await db.execute(select(User).where(User.id == sid))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": str(user.id),
        "has_photo": user.photo_url is not None,
    }

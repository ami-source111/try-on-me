from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.get("/auth/connect")
async def connect_extension(token: str, db: AsyncSession = Depends(get_db)):
    """
    Chrome-расширение вызывает этот эндпоинт после того, как пользователь
    авторизовался через Telegram-бота.

    Параметры:
        token: auth_token из Telegram-бота (UUID, живёт 1 час)

    Возвращает:
        user_id + telegram_username для сохранения в chrome.storage
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).where(
            User.auth_token == token,
            User.auth_token_expires_at > now,
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Token not found or expired. Generate a new one via /connect in the Telegram bot.",
        )

    # Инвалидируем токен сразу после использования
    user.auth_token = None
    user.auth_token_expires_at = None
    await db.commit()

    return {
        "user_id": str(user.id),
        "telegram_username": user.telegram_username,
        "has_photo": user.photo_url is not None,
    }

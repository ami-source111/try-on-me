import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobStatus:
    PENDING = "pending"
    PROCESSING_TRYON = "processing_tryon"   # Шаг 1: cat-vton
    PROCESSING_VIDEO = "processing_video"   # Шаг 2: wan video
    DONE = "done"
    FAILED = "failed"


class TryonJob(Base):
    __tablename__ = "tryon_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )

    # Исходная картинка с сайта магазина
    clothing_image_url: Mapped[str] = mapped_column(nullable=False)

    # Результат шага 1: фото пользователя в одежде (R2 URL)
    tryon_image_url: Mapped[str | None] = mapped_column(nullable=True)

    # Результат шага 2: 3-секундное видео (R2 URL)
    video_url: Mapped[str | None] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), default=JobStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<TryonJob id={self.id} status={self.status}>"

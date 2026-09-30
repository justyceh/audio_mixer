import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.db.base import Base, utcnow
from api.models.enums import MediaSource, MediaType, str_enum


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)
    # Path relative to STORAGE_ROOT, always with forward slashes (e.g. "uploads/<uuid>.mp4").
    storage_path: Mapped[str] = mapped_column(String(512), unique=True)
    media_type: Mapped[MediaType] = mapped_column(str_enum(MediaType, "media_type"), index=True)
    source: Mapped[MediaSource] = mapped_column(str_enum(MediaSource, "media_source"), default=MediaSource.upload)
    format: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(100))
    duration: Mapped[float] = mapped_column(Float)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    audio_codec: Mapped[str | None] = mapped_column(String(64))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    parent_media_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), index=True
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None

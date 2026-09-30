import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.base import Base, utcnow
from api.models.enums import TrackType, str_enum
from api.models.media_asset import MediaAsset


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    tracks: Mapped[list["Track"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Track.order_index",
    )

    @property
    def duration(self) -> float:
        """End time of the last clip on the timeline, in seconds."""
        ends = [c.timeline_start + (c.source_end - c.source_start) for t in self.tracks for c in t.clips]
        return round(max(ends), 3) if ends else 0.0


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (CheckConstraint("volume >= 0 AND volume <= 4", name="volume_range"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    track_type: Mapped[TrackType] = mapped_column(str_enum(TrackType, "track_type"), default=TrackType.other)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="tracks")
    clips: Mapped[list["Clip"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Clip.timeline_start",
    )


class Clip(Base):
    __tablename__ = "clips"
    __table_args__ = (
        CheckConstraint("timeline_start >= 0", name="timeline_start_non_negative"),
        CheckConstraint("source_start >= 0 AND source_end > source_start", name="source_range"),
        CheckConstraint("volume >= 0 AND volume <= 4", name="volume_range"),
        CheckConstraint("fade_in >= 0 AND fade_out >= 0", name="fades_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), index=True)
    # RESTRICT: a media asset used on a timeline can't be deleted out from under a project.
    media_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("media_assets.id", ondelete="RESTRICT"), index=True)
    timeline_start: Mapped[float] = mapped_column(Float, default=0.0)
    source_start: Mapped[float] = mapped_column(Float, default=0.0)
    source_end: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    fade_in: Mapped[float] = mapped_column(Float, default=0.0)
    fade_out: Mapped[float] = mapped_column(Float, default=0.0)

    track: Mapped[Track] = relationship(back_populates="clips")
    media: Mapped[MediaAsset] = relationship(lazy="joined")

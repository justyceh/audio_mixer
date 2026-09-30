import uuid

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from api.models import JobType, MediaSource, MediaType, Transcription
from api.schemas.job import JobOut
from api.schemas.media import MediaImportRequest, MediaList, MediaOut
from api.schemas.transcription import TranscriptionOut
from api.services import media_import, media_service
from api.services.job_queue import get_job_queue
from api.utils.range_response import range_file_response

router = APIRouter(prefix="/api/media", tags=["media"], dependencies=[Depends(get_current_user)])


@router.post("/upload", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
async def upload_media(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an MP3, WAV, MP4, MOV, M4A or WebM file.

    The extension is checked against an allowlist and the content is verified with
    ffprobe. Files are stored under UUID names; the original name is kept as metadata.
    """
    return await media_service.save_upload(db, file)


@router.post("/import", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def import_media(body: MediaImportRequest, db: Session = Depends(get_db)):
    """Import media from a supported site (yt-dlp) in the background.

    Only allowlisted public sources are accepted; DRM-protected, private, paid or
    login-restricted media is refused. Poll the returned job — on completion its
    `output_media_id` is the new media ID.
    """
    url = media_import.check_url(str(body.url))
    return get_job_queue().enqueue(db, JobType.import_, {"url": url})


@router.get("", response_model=MediaList)
def list_media(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    media_type: MediaType | None = None,
    source: MediaSource | None = None,
    db: Session = Depends(get_db),
):
    items, total = media_service.list_media(db, limit=limit, offset=offset, media_type=media_type, source=source)
    return MediaList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{media_id}", response_model=MediaOut)
def get_media(media_id: uuid.UUID, db: Session = Depends(get_db)):
    return media_service.get_media(db, media_id)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(media_id: uuid.UUID, db: Session = Depends(get_db)):
    media_service.delete_media(db, media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{media_id}/stream",
    responses={200: {"description": "Full file"}, 206: {"description": "Partial content"}, 416: {}},
)
def stream_media(
    media_id: uuid.UUID,
    range_header: str | None = Header(default=None, alias="Range"),
    db: Session = Depends(get_db),
):
    """Stream a media file with HTTP Range support (for <audio>/<video> seeking)."""
    asset = media_service.get_media(db, media_id)
    path = media_service.media_file_path(asset)
    return range_file_response(path, asset.mime_type, range_header)


@router.get("/{media_id}/transcriptions", response_model=list[TranscriptionOut])
def list_transcriptions(media_id: uuid.UUID, db: Session = Depends(get_db)):
    media_service.get_media(db, media_id)
    stmt = select(Transcription).where(Transcription.media_id == media_id).order_by(Transcription.created_at.desc())
    return db.scalars(stmt).all()

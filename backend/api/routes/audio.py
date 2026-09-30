import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api.core.exceptions import NotFoundError
from api.deps import get_current_user, get_db
from api.models import JobType, Transcription
from api.schemas.audio import ExtractRequest, IsolateRequest, MixRequest, TranscribeRequest, TrimRequest
from api.schemas.job import JobOut
from api.schemas.media import MediaOut
from api.schemas.transcription import TranscriptionOut
from api.services import audio_extractor, audio_mixer, media_service
from api.services.job_queue import get_job_queue

router = APIRouter(prefix="/api/audio", tags=["audio"], dependencies=[Depends(get_current_user)])


@router.post("/extract", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
def extract_audio(body: ExtractRequest, db: Session = Depends(get_db)):
    """Extract the audio track of a video (or re-encode an audio file) to WAV/MP3.

    The original file is never modified; the result is a new media asset.
    """
    return audio_extractor.extract_audio(db, body.media_id, body.format, body.start_time, body.end_time)


@router.post("/trim", response_model=MediaOut, status_code=status.HTTP_201_CREATED)
def trim_audio(body: TrimRequest, db: Session = Depends(get_db)):
    """Cut [start_time, end_time) out of a media file into a new audio asset."""
    return audio_extractor.trim_audio(db, body.media_id, body.start_time, body.end_time, body.format)


@router.post("/isolate", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def isolate_audio(body: IsolateRequest, db: Session = Depends(get_db)):
    """Separate vocals from accompaniment with Demucs (background job).

    Both stems are always created; the job's `output_media_id` is the stem matching
    `mode`, and `result` contains both IDs. **Note:** Demucs is a music source-separation
    model — voices are separated from background music, but anime sound effects and
    ambience can remain in the vocal stem. It is not a guaranteed clean-dialogue extractor.
    """
    asset = media_service.get_media(db, body.media_id)
    media_service.require_audio(asset)
    return get_job_queue().enqueue(
        db, JobType.isolate, {"media_id": str(asset.id), "mode": body.mode}, input_media_id=asset.id
    )


@router.post("/mix", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def mix_audio(body: MixRequest, db: Session = Depends(get_db)):
    """Mix several clips on a shared timeline (background job).

    Each track can be trimmed (`source_start`/`source_end`), positioned (`start_time`),
    gain-adjusted (`volume`) and faded (`fade_in`/`fade_out`). Clips may overlap.
    """
    payload = body.model_dump(mode="json")
    audio_mixer.resolve_mix_tracks(db, payload["tracks"])  # validate now for immediate feedback
    return get_job_queue().enqueue(db, JobType.mix, payload)


@router.post("/transcribe", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def transcribe_audio(body: TranscribeRequest, db: Session = Depends(get_db)):
    """Transcribe speech with faster-whisper (background job).

    When complete, `result.segments` holds `[{start, end, text}]`, and the transcription
    is saved (see `GET /api/media/{media_id}/transcriptions`).
    """
    asset = media_service.get_media(db, body.media_id)
    media_service.require_audio(asset)
    return get_job_queue().enqueue(
        db, JobType.transcribe, {"media_id": str(asset.id), "language": body.language}, input_media_id=asset.id
    )


@router.get("/transcriptions/{transcription_id}", response_model=TranscriptionOut)
def get_transcription(transcription_id: uuid.UUID, db: Session = Depends(get_db)):
    record = db.get(Transcription, transcription_id)
    if record is None:
        raise NotFoundError(f"Transcription {transcription_id} not found")
    return record

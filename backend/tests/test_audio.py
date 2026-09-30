"""Extraction and trimming — integration tests using the real FFmpeg binary."""

import uuid

import pytest

from api.models import MediaAsset
from api.utils.paths import resolve_storage_path
from tests.helpers import probe_audio_stream, probe_duration


def _path(db, media_id: str):
    return resolve_storage_path(db.get(MediaAsset, uuid.UUID(media_id)).storage_path)


def test_extract_audio_from_video(client, db, uploaded, mp4_file):
    video = uploaded(mp4_file)
    original_bytes = _path(db, video["id"]).read_bytes()

    response = client.post("/api/audio/extract", json={"media_id": video["id"], "format": "wav"})
    assert response.status_code == 201, response.text
    audio = response.json()
    assert audio["media_type"] == "audio"
    assert audio["format"] == "wav"
    assert audio["source"] == "extracted"
    assert audio["parent_media_id"] == video["id"]
    assert audio["duration"] == pytest.approx(3.0, abs=0.1)

    out = _path(db, audio["id"])
    assert out.parent.name == "processed"
    assert probe_audio_stream(out)["codec_name"] == "pcm_s16le"
    assert _path(db, video["id"]).read_bytes() == original_bytes  # original untouched


def test_extract_mp3_with_range(client, db, uploaded, mp4_file):
    video = uploaded(mp4_file)
    response = client.post(
        "/api/audio/extract", json={"media_id": video["id"], "format": "mp3", "start_time": 0.5, "end_time": 2.0}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["format"] == "mp3" and body["mime_type"] == "audio/mpeg"
    assert probe_duration(_path(db, body["id"])) == pytest.approx(1.5, abs=0.1)


def test_trim(client, db, uploaded, wav_file):
    media = uploaded(wav_file)
    response = client.post("/api/audio/trim", json={"media_id": media["id"], "start_time": 0.5, "end_time": 1.75})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "trimmed"
    assert body["duration"] == pytest.approx(1.25, abs=0.02)
    assert probe_duration(_path(db, body["id"])) == pytest.approx(1.25, abs=0.02)


@pytest.mark.parametrize(
    "start,end,code",
    [
        (1.0, 10.0, "invalid_timestamps"),  # end beyond duration
        (5.0, 6.0, "invalid_timestamps"),  # start beyond duration
        (2.0, 1.0, "validation_error"),  # end before start
        (1.0, 1.0, "validation_error"),  # zero length
        (-1.0, 1.0, "validation_error"),  # negative
    ],
)
def test_trim_invalid_timestamps(client, uploaded, wav_file, start, end, code):
    media = uploaded(wav_file)
    response = client.post("/api/audio/trim", json={"media_id": media["id"], "start_time": start, "end_time": end})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_trim_unknown_media(client):
    response = client.post("/api/audio/trim", json={"media_id": str(uuid.uuid4()), "start_time": 0, "end_time": 1})
    assert response.status_code == 404


def test_ffmpeg_failure_is_reported(client, db, uploaded, wav_file):
    media = uploaded(wav_file)
    # Corrupt the stored file after upload: FFmpeg should fail and the API should say so.
    _path(db, media["id"]).write_bytes(b"garbage" * 1000)
    response = client.post("/api/audio/trim", json={"media_id": media["id"], "start_time": 0, "end_time": 1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "media_processing_failed"

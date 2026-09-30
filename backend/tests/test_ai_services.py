"""Voice isolation and transcription with the expensive models mocked out.

The mocks replace only the model inference; the FFmpeg pre/post-processing, storage,
database records and job handling all run for real.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

from api.models import MediaAsset, Transcription
from api.services import transcription, voice_isolation
from api.services.transcription import TranscriptResult
from api.utils.paths import resolve_storage_path
from api.worker import process_next_job


class FakeSeparator:
    name = "fake-separator"

    def separate(self, input_wav: Path, workdir: Path, progress) -> dict[str, Path]:
        stems = {}
        for key, freq in (("vocals", 880), ("instrumental", 110)):
            path = workdir / f"{key}.wav"
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=3",
                 "-ac", "2", str(path)],
                check=True,
            )
            stems[key] = path
        progress(100)
        return stems


class FailingSeparator:
    name = "failing"

    def separate(self, input_wav, workdir, progress):
        from api.core.exceptions import MediaProcessingError

        raise MediaProcessingError("Demucs failed to separate the audio", details="CUDA out of memory")


class FakeTranscriber:
    name = "fake-whisper"

    def transcribe(self, audio_path, language, duration, progress):
        assert audio_path.exists()
        progress(50)
        return TranscriptResult(
            language=language or "ja",
            segments=[{"start": 0.0, "end": 1.2, "text": "Omae wa mou"}, {"start": 1.4, "end": 2.6, "text": "shindeiru"}],
        )


@pytest.mark.parametrize("mode", ["vocals", "instrumental"])
def test_isolation_creates_both_stems(client, db, uploaded, mp4_file, monkeypatch, mode):
    monkeypatch.setattr(voice_isolation, "get_separation_backend", lambda: FakeSeparator())
    source = uploaded(mp4_file)
    response = client.post("/api/audio/isolate", json={"media_id": source["id"], "mode": mode})
    assert response.status_code == 202

    process_next_job()
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed", job["error_message"]
    result = job["result"]
    assert job["output_media_id"] == result[f"{mode}_media_id"]
    assert "sound effects" in result["note"]

    for key in ("vocals_media_id", "instrumental_media_id"):
        asset = db.get(MediaAsset, uuid.UUID(result[key]))
        assert asset.source.value == "isolated"
        assert str(asset.parent_media_id) == source["id"]
        assert resolve_storage_path(asset.storage_path).parent.name == "processed"
    # original preserved
    assert db.get(MediaAsset, uuid.UUID(source["id"])) is not None


def test_isolation_failure(client, uploaded, wav_file, monkeypatch):
    monkeypatch.setattr(voice_isolation, "get_separation_backend", lambda: FailingSeparator())
    source = uploaded(wav_file)
    job_id = client.post("/api/audio/isolate", json={"media_id": source["id"]}).json()["id"]
    process_next_job()
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "Demucs failed" in job["error_message"]


def test_isolation_invalid_mode(client, uploaded, wav_file):
    source = uploaded(wav_file)
    assert client.post("/api/audio/isolate", json={"media_id": source["id"], "mode": "drums"}).status_code == 422


def test_transcription_saved(client, db, uploaded, wav_file, monkeypatch):
    monkeypatch.setattr(transcription, "get_transcriber", lambda: FakeTranscriber())
    source = uploaded(wav_file)
    response = client.post("/api/audio/transcribe", json={"media_id": source["id"], "language": "ja"})
    assert response.status_code == 202
    process_next_job()

    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed", job["error_message"]
    assert job["result"]["segments"][0] == {"start": 0.0, "end": 1.2, "text": "Omae wa mou"}

    saved = client.get(f"/api/media/{source['id']}/transcriptions").json()
    assert len(saved) == 1
    assert saved[0]["text"] == "Omae wa mou shindeiru"
    assert saved[0]["language"] == "ja"
    by_id = client.get(f"/api/audio/transcriptions/{job['result']['transcription_id']}")
    assert by_id.status_code == 200
    assert db.query(Transcription).count() == 1

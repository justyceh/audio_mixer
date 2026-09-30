import uuid

import pytest

from api.core.config import get_settings
from api.models import MediaAsset
from api.utils.paths import resolve_storage_path


def test_upload_wav(uploaded, db, wav_file):
    body = uploaded(wav_file)
    assert body["media_type"] == "audio"
    assert body["format"] == "wav"
    assert body["filename"] == "tone.wav"
    assert body["duration"] == pytest.approx(3.0, abs=0.05)
    assert body["url"] == f"/api/media/{body['id']}/stream"

    asset = db.get(MediaAsset, uuid.UUID(body["id"]))
    assert asset.stored_filename != "tone.wav"
    assert asset.storage_path.startswith("uploads/")
    assert resolve_storage_path(asset.storage_path).is_file()


def test_upload_mp4_is_video_with_audio(uploaded, mp4_file):
    body = uploaded(mp4_file)
    assert body["media_type"] == "video"
    assert body["mime_type"] == "video/mp4"
    assert body["audio_codec"] == "aac"


def test_rejects_unsupported_extension(upload, wav_file):
    response = upload(wav_file, filename="tone.exe")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media"


def test_rejects_non_media_content(upload, tmp_path):
    fake = tmp_path / "fake.mp3"
    fake.write_bytes(b"this is definitely not an mp3 file" * 100)
    response = upload(fake)
    assert response.status_code == 415


def test_rejects_content_extension_mismatch(upload, wav_file):
    # A real WAV renamed to .mp3 must be rejected: content is checked, not just the name.
    response = upload(wav_file, filename="sneaky.mp3")
    assert response.status_code == 415
    assert "does not match" in response.json()["error"]["message"]


def test_rejects_empty_file(upload, tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    assert upload(empty).status_code == 415


def test_rejects_oversized_upload(upload, wav_file, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    response = upload(wav_file)
    assert response.status_code == 413


def test_traversal_filename_is_sanitized(uploaded, db, wav_file):
    body = uploaded(wav_file, filename="../../..\\evil/../../etc/passwd.wav")
    assert "/" not in body["filename"] and "\\" not in body["filename"] and ".." not in body["filename"]
    asset = db.get(MediaAsset, uuid.UUID(body["id"]))
    path = resolve_storage_path(asset.storage_path)
    assert path.parent == get_settings().storage_root / "uploads"


def test_list_get_delete(client, uploaded, wav_file, mp3_file):
    first = uploaded(wav_file)
    uploaded(mp3_file)
    listing = client.get("/api/media").json()
    assert listing["total"] == 2
    assert client.get("/api/media", params={"media_type": "video"}).json()["total"] == 0

    assert client.get(f"/api/media/{first['id']}").json()["id"] == first["id"]
    assert client.delete(f"/api/media/{first['id']}").status_code == 204
    assert client.get(f"/api/media/{first['id']}").status_code == 404
    assert client.get(f"/api/media/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/media/not-a-uuid").status_code == 422


def test_delete_media_in_use_conflicts(client, uploaded, wav_file):
    media = uploaded(wav_file)
    project = client.post("/api/projects", json={"name": "P"}).json()
    track = client.post(f"/api/projects/{project['id']}/tracks", json={"name": "T"}).json()
    client.post(f"/api/tracks/{track['id']}/clips", json={"media_id": media["id"]})
    response = client.delete(f"/api/media/{media['id']}")
    assert response.status_code == 409


def test_stream_supports_ranges(client, uploaded, wav_file):
    media = uploaded(wav_file)
    size = wav_file.stat().st_size
    url = media["url"]

    full = client.get(url)
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert len(full.content) == size

    part = client.get(url, headers={"Range": "bytes=10-99"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 10-99/{size}"
    assert part.content == wav_file.read_bytes()[10:100]

    open_ended = client.get(url, headers={"Range": f"bytes={size - 5}-"})
    assert open_ended.status_code == 206 and len(open_ended.content) == 5

    suffix = client.get(url, headers={"Range": "bytes=-7"})
    assert suffix.status_code == 206 and suffix.content == wav_file.read_bytes()[-7:]

    bad = client.get(url, headers={"Range": f"bytes={size + 10}-"})
    assert bad.status_code == 416
    assert bad.headers["content-range"] == f"bytes */{size}"

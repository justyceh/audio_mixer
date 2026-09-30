import uuid

import pytest

from api.models import MediaAsset
from api.utils.paths import resolve_storage_path
from api.worker import process_next_job
from tests.helpers import probe_duration


@pytest.fixture
def timeline(client, uploaded, wav_file, mp3_file):
    project = client.post("/api/projects", json={"name": "My Remix!"}).json()
    pid = project["id"]
    music = client.post(f"/api/projects/{pid}/tracks", json={"name": "Music", "volume": 0.5}).json()
    voice = client.post(f"/api/projects/{pid}/tracks", json={"name": "Voice"}).json()
    song, line = uploaded(mp3_file), uploaded(wav_file)
    client.post(f"/api/tracks/{music['id']}/clips", json={"media_id": song["id"], "fade_out": 1})
    client.post(
        f"/api/tracks/{voice['id']}/clips",
        json={"media_id": line["id"], "timeline_start": 3, "source_start": 0, "source_end": 2},
    )
    return {"project": project, "music": music, "voice": voice}


@pytest.mark.parametrize("fmt,magic", [("mp3", None), ("wav", b"RIFF")])
def test_export_project(client, db, timeline, fmt, magic):
    response = client.post("/api/exports", json={"project_id": timeline["project"]["id"], "format": fmt})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    assert process_next_job() == uuid.UUID(job_id)
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed", job["error_message"]
    assert job["download_url"] == f"/api/jobs/{job_id}/download"

    asset = db.get(MediaAsset, uuid.UUID(job["output_media_id"]))
    path = resolve_storage_path(asset.storage_path)
    assert path.parent.name == "exports"
    assert probe_duration(path) == pytest.approx(5.0, abs=0.15)  # voice ends at 3 + 2

    download = client.get(job["download_url"])
    assert download.status_code == 200
    assert f"My%20Remix_.{fmt}" in download.headers["content-disposition"]
    if magic:
        assert download.content.startswith(magic)


def test_muted_tracks_are_skipped(client, db, timeline):
    client.patch(f"/api/tracks/{timeline['voice']['id']}", json={"muted": True})
    job_id = client.post("/api/exports", json={"project_id": timeline["project"]["id"], "format": "wav"}).json()["id"]
    process_next_job()
    job = client.get(f"/api/jobs/{job_id}").json()
    path = resolve_storage_path(db.get(MediaAsset, uuid.UUID(job["output_media_id"])).storage_path)
    assert probe_duration(path) == pytest.approx(4.0, abs=0.15)  # music only


def test_export_empty_project_rejected(client):
    project = client.post("/api/projects", json={"name": "Empty"}).json()
    response = client.post("/api/exports", json={"project_id": project["id"]})
    assert response.status_code == 400


def test_export_unknown_project(client):
    assert client.post("/api/exports", json={"project_id": str(uuid.uuid4())}).status_code == 404


def test_export_failure_marks_job_failed(client, db, timeline):
    job_id = client.post("/api/exports", json={"project_id": timeline["project"]["id"]}).json()["id"]
    # Break a source file after the job was accepted.
    for asset in db.query(MediaAsset).all():
        resolve_storage_path(asset.storage_path).write_bytes(b"corrupt")
    process_next_job()
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "failed"
    assert "FFmpeg" in job["error_message"]

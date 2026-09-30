import uuid

import pytest


@pytest.fixture
def project(client):
    response = client.post("/api/projects", json={"name": "Opening Remix"})
    assert response.status_code == 201
    return response.json()


def test_project_crud(client, project):
    assert project["tracks"] == [] and project["duration"] == 0

    listing = client.get("/api/projects").json()
    assert listing["total"] == 1 and listing["items"][0]["name"] == "Opening Remix"

    renamed = client.patch(f"/api/projects/{project['id']}", json={"name": "Renamed"}).json()
    assert renamed["name"] == "Renamed"
    assert renamed["updated_at"] >= project["updated_at"]

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_project_validation(client):
    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    assert client.get(f"/api/projects/{uuid.uuid4()}").status_code == 404


def test_tracks_and_clips_full_project(client, project, uploaded, wav_file, mp3_file):
    pid = project["id"]
    dialogue = client.post(f"/api/projects/{pid}/tracks", json={"name": "Dialogue", "track_type": "dialogue"}).json()
    music = client.post(f"/api/projects/{pid}/tracks", json={"name": "Music", "track_type": "music", "volume": 0.6}).json()
    assert (dialogue["order_index"], music["order_index"]) == (0, 1)

    voice = uploaded(wav_file)
    song = uploaded(mp3_file)

    clip = client.post(
        f"/api/tracks/{dialogue['id']}/clips",
        json={"media_id": voice["id"], "timeline_start": 2.0, "source_start": 0.5, "source_end": 2.5, "fade_in": 0.1},
    )
    assert clip.status_code == 201, clip.text
    clip = clip.json()
    assert clip["media"]["id"] == voice["id"]

    # source_end defaults to the media duration
    song_clip = client.post(f"/api/tracks/{music['id']}/clips", json={"media_id": song["id"]}).json()
    assert song_clip["source_end"] == pytest.approx(song["duration"])

    full = client.get(f"/api/projects/{pid}").json()
    assert [t["name"] for t in full["tracks"]] == ["Dialogue", "Music"]
    assert full["tracks"][0]["clips"][0]["id"] == clip["id"]
    assert full["duration"] == pytest.approx(max(4.0, song["duration"]), abs=0.05)

    updated = client.patch(f"/api/clips/{clip['id']}", json={"timeline_start": 5.0, "volume": 0.5}).json()
    assert updated["timeline_start"] == 5.0 and updated["volume"] == 0.5

    moved = client.patch(f"/api/clips/{clip['id']}", json={"track_id": music["id"]}).json()
    assert moved["track_id"] == music["id"]

    track = client.patch(f"/api/tracks/{dialogue['id']}", json={"muted": True, "name": "Voice"}).json()
    assert track["muted"] is True and track["name"] == "Voice"

    assert client.delete(f"/api/clips/{clip['id']}").status_code == 204
    assert client.get(f"/api/clips/{clip['id']}").status_code == 404
    assert client.delete(f"/api/tracks/{dialogue['id']}").status_code == 204


def test_clip_bounds_validated_against_media(client, project, uploaded, wav_file):
    track = client.post(f"/api/projects/{project['id']}/tracks", json={"name": "T"}).json()
    media = uploaded(wav_file)
    url = f"/api/tracks/{track['id']}/clips"

    too_long = client.post(url, json={"media_id": media["id"], "source_end": 99})
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "invalid_timestamps"

    reversed_range = client.post(url, json={"media_id": media["id"], "source_start": 2, "source_end": 1})
    assert reversed_range.status_code == 422

    negative = client.post(url, json={"media_id": media["id"], "timeline_start": -1})
    assert negative.status_code == 422

    missing_media = client.post(url, json={"media_id": str(uuid.uuid4())})
    assert missing_media.status_code == 404


def test_deleting_project_cascades(client, db, project, uploaded, wav_file):
    from sqlalchemy import func, select

    from api.models import Clip, MediaAsset, Track

    track = client.post(f"/api/projects/{project['id']}/tracks", json={"name": "T"}).json()
    media = uploaded(wav_file)
    client.post(f"/api/tracks/{track['id']}/clips", json={"media_id": media["id"]})

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Track)) == 0
    assert db.scalar(select(func.count()).select_from(Clip)) == 0
    assert db.scalar(select(func.count()).select_from(MediaAsset)) == 1  # media survives

import uuid
from pathlib import Path

import pytest

from api.models import MediaAsset
from api.services.audio_mixer import MixInput, build_filter_graph, build_mix_command, expected_duration
from api.utils.paths import resolve_storage_path
from api.worker import process_next_job
from tests.helpers import probe_audio_stream, probe_duration


def test_filter_graph_structure():
    inputs = [
        MixInput(Path("a.wav"), timeline_start=0, source_start=0, source_end=120, volume=0.7),
        MixInput(Path("b.wav"), timeline_start=32.5, source_start=1, source_end=6, volume=1.0, fade_in=0.5, fade_out=1),
    ]
    graph = build_filter_graph(inputs)
    assert "[0:a:0]atrim=start=0:end=120" in graph
    assert "volume=0.7" in graph
    assert "aresample=44100" in graph and "channel_layouts=stereo" in graph
    assert "adelay=delays=32500:all=1" in graph
    assert "afade=t=in:st=0:d=0.5" in graph
    assert "afade=t=out:st=4:d=1" in graph  # 5 s clip, 1 s fade-out
    assert "amix=inputs=2:duration=longest:normalize=0" in graph
    assert graph.endswith("[out]")
    assert expected_duration(inputs) == pytest.approx(120)


def test_mix_command_is_argument_list():
    cmd = build_mix_command([MixInput(Path("x; rm -rf.wav"), 0, 0, 1)], Path("out.mp3"), "mp3")
    assert cmd[:2] == ["-i", "x; rm -rf.wav"]  # passed as a single argv element, no shell
    assert "libmp3lame" in cmd


def test_fades_clamped_to_clip_length():
    graph = build_filter_graph([MixInput(Path("a.wav"), 0, 0, 1, fade_in=5, fade_out=5)])
    assert "afade=t=in:st=0:d=1" in graph and "afade=t=out:st=0:d=1" in graph


def test_mix_endpoint_overlapping_clips(client, db, uploaded, wav_file, mp3_file):
    voice = uploaded(wav_file)  # 3 s
    music = uploaded(mp3_file)  # 4 s @ 48 kHz mono -> exercises resample + upmix
    response = client.post(
        "/api/audio/mix",
        json={
            "tracks": [
                {"media_id": music["id"], "start_time": 0, "source_start": 0, "source_end": 4, "volume": 0.5,
                 "fade_in": 0.5, "fade_out": 1.0},
                {"media_id": voice["id"], "start_time": 2.5, "source_start": 0.5, "source_end": 2.5, "volume": 1.0},
            ],
            "output_format": "wav",
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "pending" and job["job_type"] == "mix"

    assert process_next_job() == uuid.UUID(job["id"])
    job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] == "completed", job["error_message"]
    assert job["progress"] == 100

    out = resolve_storage_path(db.get(MediaAsset, uuid.UUID(job["output_media_id"])).storage_path)
    # voice clip: 2 s long starting at 2.5 s -> mix ends at 4.5 s
    assert probe_duration(out) == pytest.approx(4.5, abs=0.1)
    stream = probe_audio_stream(out)
    assert int(stream["sample_rate"]) == 44100 and stream["channels"] == 2

    download = client.get(f"/api/jobs/{job['id']}/download")
    assert download.status_code == 200 and download.content[:4] == b"RIFF"


def test_mix_rejects_out_of_range_source(client, uploaded, wav_file):
    voice = uploaded(wav_file)
    response = client.post(
        "/api/audio/mix", json={"tracks": [{"media_id": voice["id"], "source_start": 0, "source_end": 30}]}
    )
    assert response.status_code == 422
    assert "tracks[0]" in response.json()["error"]["message"]


def test_mix_requires_tracks(client):
    assert client.post("/api/audio/mix", json={"tracks": []}).status_code == 422

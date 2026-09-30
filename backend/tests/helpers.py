import json
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def probe_audio_stream(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-select_streams", "a:0", str(path)],
        capture_output=True, check=True,
    )
    return json.loads(out.stdout)["streams"][0]

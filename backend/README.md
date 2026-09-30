# Anime Remix Studio — Backend

FastAPI + PostgreSQL backend for importing media, extracting audio, isolating dialogue
from music with Demucs, trimming, mixing, transcribing, and exporting audio remixes.
Everything runs locally: no paid services or cloud AI APIs.

- API: `uvicorn api.server:app --reload` → http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Background worker: `python -m api.worker`

## Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11 or 3.12 | 3.13+ is **not** supported by the pinned PyTorch/Demucs wheels |
| FFmpeg | 5.1+ (tested with 8.1) | `ffmpeg` and `ffprobe` must be on `PATH` |
| PostgreSQL | 14+ (tested with 18) | |
| Disk | ~3 GB | PyTorch CPU, Demucs + Whisper model weights |

### Install FFmpeg (Windows)

```bash
winget install Gyan.FFmpeg
```

Open a new terminal and check that `ffmpeg -version` and `ffprobe -version` both work.
On macOS use `brew install ffmpeg`, and on Debian/Ubuntu use `sudo apt install ffmpeg`.

### PostgreSQL setup

Create a role, the app database, and a **separate** test database. Run this in `psql` as the `postgres` superuser:

```sql
CREATE USER anime_remix WITH PASSWORD 'choose-a-password';
CREATE DATABASE anime_remix OWNER anime_remix;
CREATE DATABASE anime_remix_test OWNER anime_remix;
```

## Setup

From the `backend/` folder:

```bash
py -3.12 -m venv .venv
```

```bash
.venv\Scripts\activate
```

On macOS/Linux, create the venv with `python3.12 -m venv .venv` and activate it with `source .venv/bin/activate`.

Install PyTorch (CPU build) first, then everything else:

```bash
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
```

```bash
pip install -r requirements-dev.txt
```

For an NVIDIA GPU, install the CUDA build of torch instead (see pytorch.org). Then set
`DEMUCS_DEVICE=cuda`, `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`.

Copy the environment file and fill in your database password:

```bash
copy .env.example .env
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://anime_remix:change-me@localhost:5432/anime_remix` | App database (psycopg 3 driver) |
| `TEST_DATABASE_URL` | — | Test database. Its tables are **dropped** by pytest, and it must differ from `DATABASE_URL` |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `STORAGE_ROOT` | `storage` | Media storage root (relative to `backend/`) |
| `MAX_UPLOAD_MB` | `500` | Upload size limit |
| `FFMPEG_PATH` / `FFPROBE_PATH` | `ffmpeg` / `ffprobe` | Binary names or absolute paths |
| `DEMUCS_MODEL` / `DEMUCS_DEVICE` | `htdemucs` / `cpu` | Voice isolation model |
| `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `small` / `cpu` / `int8` | Transcription model |
| `IMPORT_ENABLED` | `true` | Turn URL import on/off |
| `IMPORT_ALLOWED_DOMAINS` | `youtube.com,youtu.be,soundcloud.com,vimeo.com,bandcamp.com` | Allowed import sites |
| `IMPORT_MAX_MB` | `500` | Import size limit |
| `WORKER_POLL_INTERVAL_SECONDS` | `1.0` | How often the worker checks for jobs |
| `WORKER_STALE_JOB_MINUTES` | `120` | On startup, jobs stuck in `processing` longer than this are marked failed |

## Database migrations

```bash
alembic upgrade head
```

After changing models, generate a new migration:

```bash
alembic revision --autogenerate -m "describe change"
```

## Running

You need two processes, in two terminals with the venv active.

API server:

```bash
uvicorn api.server:app --reload
```

Background worker (runs isolation, mixing, transcription, exports and imports):

```bash
python -m api.worker
```

Jobs stay `pending` until a worker picks them up, and you can run more than one worker.
`python -m api.worker --once` processes the queue and then exits.

`GET /api/health` reports whether the database, FFmpeg, Demucs, faster-whisper and yt-dlp are available.

**First-run downloads:** Demucs (`htdemucs`, about 80 MB) and Whisper models download automatically
the first time they are used. The Whisper `small` model is about 480 MB.
They are cached under your user profile (`~/.cache/torch` and `~/.cache/huggingface`).

## Tests

```bash
pytest -v
```

- DB-backed tests use `TEST_DATABASE_URL`. If it is unset or unreachable, they are **skipped** rather than failed.
- Test media is generated on the fly with FFmpeg. Extract, trim, mix and export tests run real FFmpeg.
- The Demucs and Whisper models are mocked in tests. FFmpeg pre/post-processing, storage and jobs still run for real.
- Uploads go to a throwaway temp directory, not `storage/`.

## Architecture

```
api/
  server.py        FastAPI app: CORS, error handlers, routers, /api/health
  worker.py        Job worker process
  core/            Settings (.env) and error types
  db/, models/     SQLAlchemy 2.0 engine/session and ORM models
  schemas/         Pydantic request/response models
  routes/          Thin HTTP handlers (no business logic)
  services/        Media storage, FFmpeg operations, Demucs, Whisper, yt-dlp, mixer, exports, job queue
  utils/           ffmpeg wrapper, safe paths, filename sanitizing, HTTP Range, URL/SSRF checks
alembic/           Migrations
storage/           uploads/ processed/ exports/ temp/
```

- **Files**: stored as `<uuid>.<ext>`. The DB keeps paths relative to `STORAGE_ROOT`, and every path is resolved through a check that refuses anything outside the storage root. User filenames are sanitized and kept only as metadata.
- **FFmpeg**: always run with argument lists (`subprocess.run([...])`), never through a shell.
- **Originals are never modified**: extract, trim, isolate, mix and export always create new media assets, linked to their source via `parent_media_id`.
- **Jobs**: the `processing_jobs` table is the queue. Workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED`. To move to Celery/Redis, change `JobQueue.enqueue` in `services/job_queue.py` to dispatch a task that calls `api.worker.execute_job(job_id)`. Status polling does not change.
- **Auth-ready**: every router depends on `deps.get_current_user` (currently returns `None`). Add authentication there and scope service queries by owner.

### About voice isolation

Demucs is a **music** source-separation model. It separates voices from background music well,
but anime sound effects, ambience and crowd noise can stay in the vocal stem. The API does not claim
clean dialogue extraction, and every isolation result includes a note saying so. To add a better
dialogue or speech-enhancement model, implement `SeparationBackend` in `services/voice_isolation.py`.

### About URL import

URL import is only for media you are authorized to download from sites that allow it. Safeguards:

- Only `http`/`https` URLs on the domain allowlist are accepted, with no embedded credentials and default ports only.
- The host must resolve to public IP addresses only (SSRF protection). This is checked when the request is made and again in the worker.
- yt-dlp's generic extractor is refused, and redirects to sites outside the allowlist are rejected.
- No cookies, logins or DRM workarounds are used. Private, paid, members-only, age-gated or DRM content fails with a clear error.
- Local upload always works as an alternative.

yt-dlp changes often as sites change. If imports start failing, run `pip install -U yt-dlp`.

## API overview

All errors use this shape: `{"error": {"code": "...", "message": "...", "details": ...}}`.

### Media
| Method | Path | Notes |
|---|---|---|
| POST | `/api/media/upload` | multipart `file`. Accepts mp3/wav/mp4/mov/m4a/webm; content is verified with ffprobe. Returns **201** |
| POST | `/api/media/import` | `{"url": "..."}` returns **202** with a job. When the job completes, `output_media_id` is the new media |
| GET | `/api/media` | `?limit&offset&media_type=audio\|video&source=...` |
| GET | `/api/media/{id}` | Metadata including `url` (the stream URL) |
| DELETE | `/api/media/{id}` | Returns 409 if the media is used by a clip |
| GET | `/api/media/{id}/stream` | Supports HTTP Range (206/416), for `<audio>`/`<video>` |
| GET | `/api/media/{id}/transcriptions` | Saved transcriptions |

### Audio
| Method | Path | Body | Result |
|---|---|---|---|
| POST | `/api/audio/extract` | `{media_id, format: wav\|mp3, start_time?, end_time?}` | 201 media |
| POST | `/api/audio/trim` | `{media_id, start_time, end_time, format?}` | 201 media |
| POST | `/api/audio/isolate` | `{media_id, mode: vocals\|instrumental}` | 202 job. `result` has both stem IDs |
| POST | `/api/audio/mix` | `{tracks: [{media_id, start_time, source_start, source_end, volume, fade_in, fade_out}], output_format}` | 202 job |
| POST | `/api/audio/transcribe` | `{media_id, language?}` | 202 job. `result.segments = [{start, end, text}]` |
| GET | `/api/audio/transcriptions/{id}` | | transcription |

### Projects / timeline
| Method | Path |
|---|---|
| POST, GET | `/api/projects` |
| GET, PATCH, DELETE | `/api/projects/{id}`. GET returns tracks, clips and media in one response |
| POST | `/api/projects/{id}/tracks` |
| GET, PATCH, DELETE | `/api/tracks/{id}` |
| POST | `/api/tracks/{id}/clips` |
| GET, PATCH, DELETE | `/api/clips/{id}` |

### Jobs & exports
| Method | Path | Notes |
|---|---|---|
| POST | `/api/exports` | `{project_id, format: mp3\|wav}` returns 202 with a job |
| GET | `/api/jobs` | `?status=` |
| GET | `/api/jobs/{id}` | Poll this. Status goes `pending` → `processing` → `completed` or `failed`, with `progress` 0–100 |
| GET | `/api/jobs/{id}/download` | Returns the output file. 409 if the job has not completed |

### Example workflow (curl)

These examples use bash syntax. In PowerShell, use `curl.exe` and escape the JSON quotes.

```bash
curl -F "file=@episode1.mp4" http://localhost:8000/api/media/upload
```

```bash
curl -X POST http://localhost:8000/api/audio/isolate -H "Content-Type: application/json" -d '{"media_id": "<video-id>", "mode": "vocals"}'
```

```bash
curl http://localhost:8000/api/jobs/<job-id>
```

```bash
curl -X POST http://localhost:8000/api/audio/trim -H "Content-Type: application/json" -d '{"media_id": "<vocals-id>", "start_time": 12.5, "end_time": 19.8}'
```

```bash
curl -X POST http://localhost:8000/api/audio/mix -H "Content-Type: application/json" -d '{"output_format": "mp3", "tracks": [{"media_id": "<music-id>", "volume": 0.7, "source_end": 120, "fade_out": 3}, {"media_id": "<clip-id>", "start_time": 32.5, "volume": 1.0}]}'
```

```bash
curl -OJ http://localhost:8000/api/jobs/<job-id>/download
```

Frontend polling pattern: POST a job-producing endpoint and read `id` from the response.
Poll `GET /api/jobs/{id}` every 1–2 s until `status` is `completed` or `failed`.
When it completes, use `download_url`, or `output_media_id` with `/api/media/{id}/stream`.

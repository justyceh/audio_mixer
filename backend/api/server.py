"""FastAPI application entry point: `uvicorn api.server:app --reload`"""

import importlib.util
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.core.config import get_settings
from api.core.exceptions import register_exception_handlers
from api.deps import get_db
from api.routes import audio, exports, media, processing, projects
from api.utils.ffmpeg import ffmpeg_available
from api.utils.paths import ensure_storage_dirs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_storage_dirs()
    yield


class UploadSizeLimitMiddleware:
    """Reject oversized uploads from their Content-Length before the body is read."""

    def __init__(self, app, path: str, max_bytes: int):
        self.app = app
        self.path = path
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == self.path and scope["method"] == "POST":
            for name, value in scope.get("headers", []):
                if name == b"content-length":
                    try:
                        too_big = int(value) > self.max_bytes
                    except ValueError:
                        too_big = False
                    if too_big:
                        mb = self.max_bytes // (1024 * 1024)
                        response = JSONResponse(
                            status_code=413,
                            content={"error": {"code": "payload_too_large",
                                               "message": f"Upload exceeds the {mb} MB limit", "details": None}},
                        )
                        await response(scope, receive, send)
                        return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Local backend for importing media, isolating dialogue, trimming, mixing and exporting remixes.",
        lifespan=lifespan,
    )
    # Multipart overhead allowance on top of the raw file size limit.
    app.add_middleware(UploadSizeLimitMiddleware, path="/api/media/upload",
                       max_bytes=settings.max_upload_bytes + 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "Content-Length", "Content-Disposition"],
    )
    register_exception_handlers(app)

    for module in (media, audio, projects, processing, exports):
        app.include_router(module.router)

    @app.get("/api/health", tags=["health"])
    def health(db: Session = Depends(get_db)):
        """Reports which local dependencies are available."""
        try:
            db.execute(text("SELECT 1"))
            database = True
        except Exception:
            database = False
        return {
            "status": "ok" if database else "degraded",
            "database": database,
            "ffmpeg": ffmpeg_available(),
            "demucs": importlib.util.find_spec("demucs") is not None,
            "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
            "yt_dlp": importlib.util.find_spec("yt_dlp") is not None,
        }

    return app


app = create_app()

"""Safe storage path handling.

The database only ever stores paths *relative* to STORAGE_ROOT. Every conversion to a
real filesystem path goes through `resolve_storage_path`, which refuses anything that
would escape the storage root (absolute paths, `..`, drive letters, symlink tricks).
"""

import shutil
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from api.core.config import get_settings
from api.core.exceptions import BadRequestError

STORAGE_AREAS = ("uploads", "processed", "exports", "temp")


def storage_root() -> Path:
    return get_settings().storage_root


def ensure_storage_dirs() -> None:
    root = storage_root()
    for area in STORAGE_AREAS:
        (root / area).mkdir(parents=True, exist_ok=True)


def resolve_storage_path(relative_path: str) -> Path:
    root = storage_root()
    pure = PurePosixPath(relative_path.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or ":" in relative_path or not pure.parts:
        raise BadRequestError("Invalid storage path")
    if pure.parts[0] not in STORAGE_AREAS:
        raise BadRequestError("Invalid storage area")
    candidate = (root / Path(*pure.parts)).resolve()
    if not candidate.is_relative_to(root):
        raise BadRequestError("Invalid storage path")
    return candidate


def to_relative(path: Path) -> str:
    resolved = path.resolve()
    root = storage_root()
    if not resolved.is_relative_to(root):
        raise BadRequestError("Path is outside storage root")
    return resolved.relative_to(root).as_posix()


def new_storage_file(area: str, extension: str) -> tuple[str, str, Path]:
    """Allocate a fresh UUID-named file in a storage area.

    Returns (stored_filename, relative_path, absolute_path).
    """
    if area not in STORAGE_AREAS:
        raise ValueError(f"Unknown storage area: {area}")
    ext = extension.lower().lstrip(".")
    if not ext.isalnum():
        raise ValueError(f"Invalid extension: {extension}")
    stored = f"{uuid.uuid4()}.{ext}"
    relative = f"{area}/{stored}"
    absolute = resolve_storage_path(relative)
    absolute.parent.mkdir(parents=True, exist_ok=True)
    return stored, relative, absolute


@contextmanager
def temp_workdir(prefix: str = "work") -> Iterator[Path]:
    """Per-operation scratch directory under storage/temp, always removed afterwards."""
    safe_prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in "-_") or "work"
    path = storage_root() / "temp" / f"{safe_prefix}-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

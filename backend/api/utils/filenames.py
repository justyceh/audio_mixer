import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

_UNSAFE = re.compile(r"[^\w.\- ()\[\]]+", re.UNICODE)


def sanitize_filename(filename: str | None, default: str = "media") -> str:
    """Reduce a user-supplied filename to a safe display name.

    Strips any directory components (both / and \\), control characters and
    anything outside a conservative character set. The result is only used as
    metadata — files on disk are always stored under UUID names.
    """
    if not filename:
        return default
    name = PureWindowsPath(PurePosixPath(filename.replace("\\", "/")).name).name
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = _UNSAFE.sub("_", name).strip(" .")
    if not name or set(name) <= {".", "_"}:
        return default
    return name[:200]


def extension_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower().lstrip(".")

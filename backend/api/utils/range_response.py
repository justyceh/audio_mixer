"""HTTP Range (RFC 9110) support for media streaming."""

from collections.abc import Iterator
from pathlib import Path

from fastapi import Response
from fastapi.responses import StreamingResponse

CHUNK_SIZE = 256 * 1024


class RangeNotSatisfiable(Exception):
    pass


def parse_range_header(header: str, file_size: int) -> tuple[int, int] | None:
    """Parse a single-range `bytes=` header into inclusive (start, end).

    Returns None when the header should be ignored (unsupported unit / multi-range),
    in which case the full content is served. Raises RangeNotSatisfiable for
    syntactically valid ranges that don't overlap the file.
    """
    header = header.strip()
    if not header.lower().startswith("bytes="):
        return None
    spec = header[6:].strip()
    if "," in spec or "-" not in spec:
        return None
    start_s, end_s = (part.strip() for part in spec.split("-", 1))
    try:
        if start_s == "":
            # Suffix range: last N bytes.
            suffix = int(end_s)
            if suffix <= 0:
                raise RangeNotSatisfiable
            start = max(file_size - suffix, 0)
            end = file_size - 1
        else:
            start = int(start_s)
            if start >= file_size:
                raise RangeNotSatisfiable
            end = int(end_s) if end_s else file_size - 1
            if start < 0 or end < start:
                return None
            end = min(end, file_size - 1)
    except ValueError:
        return None
    if file_size == 0 or start >= file_size:
        raise RangeNotSatisfiable
    return start, end


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def range_file_response(path: Path, media_type: str, range_header: str | None) -> Response:
    file_size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes"}

    byte_range = None
    if range_header:
        try:
            byte_range = parse_range_header(range_header, file_size)
        except RangeNotSatisfiable:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{file_size}"})

    if byte_range is None:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(_iter_file(path, 0, file_size), media_type=media_type, headers=headers)

    start, end = byte_range
    length = end - start + 1
    headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    headers["Content-Length"] = str(length)
    return StreamingResponse(_iter_file(path, start, length), status_code=206, media_type=media_type, headers=headers)

"""The single place untrusted bytes become a file on disk.

Two hazards, one module (RESEARCH.md Pitfalls 3 and 4, § Security Domain
V12):

1. **Never trust a client-supplied filename as a path component.**
   :func:`save_upload` always writes to a server-generated
   ``uuid4().hex`` name with an extension derived from the format Pillow
   itself reported. The client's own filename never reaches path
   construction anywhere in this module. :func:`display_name` produces the
   artist-visible name separately, for display only — it strips every
   directory component from both POSIX and Windows conventions and must
   never be joined into a path.

2. **Never let a Pillow exception surface as a bare 500.** A degenerate or
   non-image upload is a routine, expected failure mode for an artist on a
   video call, not a crash. :func:`decode_image` verifies the decoded
   image inside a broad ``try/except`` and raises a structured 400 carrying
   the UI-SPEC Copywriting Contract's exact sentence in every failure case.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image

# Verbatim from 01-UI-SPEC.md's Copywriting Contract — the frontend renders
# this string as-is, so it must not be paraphrased.
UPLOAD_ERROR_DETAIL = (
    "Upload failed: the file isn't a readable image — try a PNG, JPG or TIFF."
)

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_DIMENSION = 20000
ALLOWED_FORMATS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "TIFF": ".tif",
    "BMP": ".bmp",
    "WEBP": ".webp",
}


def decode_image(data: bytes) -> Image.Image:
    """Validate ``data`` is a readable, reasonably sized image.

    Every failure — oversized payload, unparseable bytes, disallowed
    format, degenerate or absurd dimensions — raises the same structured
    400. Nothing downstream ever sees a raw Pillow exception.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=UPLOAD_ERROR_DETAIL)

    try:
        probe = Image.open(BytesIO(data))
        probe.verify()
        # verify() leaves the Image object unusable for further access —
        # re-open the same bytes for the real, returned handle.
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as exc:  # noqa: BLE001 - every decode failure is a 400
        raise HTTPException(status_code=400, detail=UPLOAD_ERROR_DETAIL) from exc

    if image.format not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=UPLOAD_ERROR_DETAIL)

    width, height = image.size
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise HTTPException(status_code=400, detail=UPLOAD_ERROR_DETAIL)

    return image


@dataclass(frozen=True)
class SavedUpload:
    path: Path
    relative_path: str
    width: int
    height: int
    format: str


def save_upload(data: bytes, dest_dir: Path, project_root: Path) -> SavedUpload:
    """Decode, validate, then write ``data`` under a server-generated name.

    ``dest_dir`` is always built from :mod:`comiccolor.web.appconfig`
    constants (``PAGES_DIR``, ``PENDING_DIR``) and never from request data
    — callers must not pass a client-influenced path here. The on-disk
    filename is ``uuid4().hex`` plus the extension for the format Pillow
    itself reported — the client's own filename is never used (RESEARCH.md
    Pitfall 3).
    ``relative_path`` is relative to ``project_root``, which is what goes
    into ``page.source_path`` so the project folder stays portable when
    copied (D-04).
    """
    image = decode_image(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{ALLOWED_FORMATS[image.format]}"
    dest_path = dest_dir / filename
    dest_path.write_bytes(data)
    return SavedUpload(
        path=dest_path,
        relative_path=str(dest_path.relative_to(project_root)),
        width=image.width,
        height=image.height,
        format=image.format,
    )


def display_name(filename: str | None) -> str:
    """A safe, artist-visible name for display only — never a path component.

    Strips every directory component using both POSIX and Windows path
    conventions (a client on either platform could send either separator),
    trims whitespace, truncates to a sane length, and falls back to
    ``"untitled"`` for an empty or missing name. This value is stored as
    ``page.original_name`` for display; it must never be joined into a
    filesystem path.
    """
    if not filename:
        return "untitled"
    stripped = PureWindowsPath(PurePosixPath(filename).name).name.strip()
    if not stripped:
        return "untitled"
    return stripped[:200]

"""Reference (character sheet) routes.

PROJ-03 (reference image management) and PAL-02 (character-sheet colour
proposals — proposed, never persisted until the artist accepts).

D-05 is the whole shape of this module: uploading a character sheet is one
drag-and-drop with zero prompts — no name, no part, no metadata, no colour
count is ever asked at upload time. The app only asks for the character name
once the artist is looking at the extracted colours and knows what to call
them, which is what lets an accepted entry land as ``Kaito / hair`` instead
of taxing every upload with a form.

Two binding resolutions this module holds to, not re-opens (see
01-10-PLAN.md's objective):

1. **Not-yet-accepted sheets are filesystem-only** (resolved RESEARCH.md
   Open Question 2). A pending sheet lives at
   ``<project>/references/pending/<uuid>.<ext>`` and nothing else — no
   dedicated database table backs a pending sheet anywhere in this project.
2. **Proposals are never persisted before accept.** ``POST /sheets`` writes
   no database row; the proposal list exists only in the HTTP response
   (RESEARCH.md § Anti-Patterns). The accept route re-derives the same
   proposals from the file it already wrote, rather than trusting a client-
   supplied colour, which is also what makes rejecting a proposal free —
   "reject" is simply never accepting, nothing to undo.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from ...colour import extract_palette
from .. import uploads
from ..appconfig import PENDING_DIR, REFERENCES_DIR
from ..deps import get_current_project_path
from ..schemas import ProposalResponse, SheetProposalResponse

router = APIRouter()

# Exactly the shape uploads.save_upload's uuid4().hex produces. sheet_id is
# the only client-supplied value that ever influences a path in this module
# (a proposal index is an integer, never a filename), so it is constrained
# to a fixed, closed alphabet before any path is built at all, rather than
# sanitised after the fact — a value like "../../project" or
# "..%2Fproject.db" never reaches the filesystem (RESEARCH.md § Security
# Domain V12, T-01-SHEETID).
SHEET_ID_RE = re.compile(r"^[0-9a-f]{32}$")

SHEET_NOT_FOUND_DETAIL = "That character sheet is no longer available — upload it again."
BAD_PROPOSAL_INDEX_DETAIL = (
    "Those proposals are out of date — re-upload the sheet and try again."
)


def _validate_sheet_id(sheet_id: str) -> str:
    """Reject anything that isn't a bare 32-character lowercase hex id.

    Runs before any path is constructed anywhere in this module. A
    traversal segment, a separator, or an absolute path never gets far
    enough to be joined onto a directory — it fails this regex and becomes
    a 404 with neutral copy, same as a sheet id that was simply never
    issued.
    """
    if not SHEET_ID_RE.match(sheet_id):
        raise HTTPException(status_code=404, detail=SHEET_NOT_FOUND_DETAIL)
    return sheet_id


def _locate(directory: Path, sheet_id: str) -> Path | None:
    """The single ``<sheet_id>.<ext>`` file in ``directory``, if any.

    Globs rather than trying every extension in ``uploads.ALLOWED_FORMATS``
    by hand, then resolves and asserts the match is still inside
    ``directory`` — belt-and-braces alongside :func:`_validate_sheet_id`,
    which already makes escaping the id itself impossible.
    """
    if not directory.is_dir():
        return None
    matches = sorted(directory.glob(f"{sheet_id}.*"))
    if not matches:
        return None
    resolved = matches[0].resolve()
    if not resolved.is_relative_to(directory.resolve()):
        return None
    return resolved


def _pending_path(project_root: Path, sheet_id: str) -> Path:
    """The on-disk file for a still-pending sheet, or a 404.

    Validates ``sheet_id`` first (see :func:`_validate_sheet_id`), so a
    path-traversal attempt never reaches :func:`_locate` at all.
    """
    sheet_id = _validate_sheet_id(sheet_id)
    found = _locate(project_root / PENDING_DIR, sheet_id)
    if found is None:
        raise HTTPException(status_code=404, detail=SHEET_NOT_FOUND_DETAIL)
    return found


@router.post(
    "/sheets",
    response_model=SheetProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_sheet(
    file: UploadFile,
    project_root: Path = Depends(get_current_project_path),
) -> SheetProposalResponse:
    """Upload a character sheet; propose colours, persist nothing (D-05).

    Asks the artist nothing — no character name, no part, no metadata, no
    colour count (D-15 is that the extractor decides the count). The
    uploaded bytes are written under ``references/pending/<uuid>.<ext>``,
    a server-generated name (never the client's filename), and that file is
    the *only* persistence a pending sheet gets: no database row exists for
    it, and the proposals returned below exist only in this response
    (resolved RESEARCH.md Open Question 2; § Anti-Patterns explicitly names
    persisting pre-accept proposal colours as the mistake to avoid). A
    later contributor's instinct to add a dedicated database table for
    "tidiness" is exactly the change this design deliberately does not make.

    The sheet-aware ink/paper pre-pass (D-14) runs first, so what comes
    back is the character's own colours, not the page's ink and paper. An
    all-ink or all-paper sheet raises ``EmptyImageError``, mapped to a 400
    by the app-level handler registered in plan 01-06.

    Deliberately a sync ``def``: this route also touches the filesystem
    (``uploads.decode_image``/``save_upload``, both blocking calls), and
    every route in this module that shares that concern stays sync for
    consistency, even where (as here) no ``Store`` dependency is involved.
    """
    data = file.file.read()
    image = uploads.decode_image(data)

    saved = uploads.save_upload(data, project_root / PENDING_DIR, project_root)
    sheet_id = Path(saved.relative_path).stem

    proposals = extract_palette(image, sheet_mode=True)
    return SheetProposalResponse(
        sheet_id=sheet_id,
        image_url=f"/api/references/sheets/{sheet_id}/image",
        proposals=[
            ProposalResponse(index=i, rgb=colour.rgb, pixel_share=colour.pixel_share)
            for i, colour in enumerate(proposals)
        ],
    )


@router.get("/sheets/{sheet_id}/image")
def get_sheet_image(
    sheet_id: str,
    project_root: Path = Depends(get_current_project_path),
) -> FileResponse:
    """The sheet's own image, so the artist can see it beside the proposal
    cards. Looks in ``references/pending/`` first (the common case — a
    sheet not yet accepted or rejected), then falls back to
    ``references/`` for a sheet already accepted and moved out of pending
    by the accept route below. Both lookups are id-validated and
    containment-asserted the same way (T-01-SHEETID).
    """
    sheet_id = _validate_sheet_id(sheet_id)
    found = _locate(project_root / PENDING_DIR, sheet_id) or _locate(
        project_root / REFERENCES_DIR, sheet_id
    )
    if found is None:
        raise HTTPException(status_code=404, detail=SHEET_NOT_FOUND_DETAIL)
    return FileResponse(found)

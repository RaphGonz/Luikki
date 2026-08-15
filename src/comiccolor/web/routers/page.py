"""Page routes.

PROJ-02 (upload pages into a volume, add more over time without disturbing
what's already there) and PROJ-04 (every page carries its pipeline stage;
any page can be opened by id).

This is where untrusted bytes first reach the filesystem, so it is where
RESEARCH.md Pitfall 3 and Pitfall 4 are actually mitigated (threat register
T-01-PATH, T-01-IMG, T-01-SERVE):

- The client-supplied filename is used for exactly one thing —
  ``display_name()`` for ``page.original_name`` — and never reaches path
  construction. The on-disk filename always comes from
  ``uploads.save_upload``, which generates it from a UUID and the format
  Pillow itself reported. "Just use the original filename, it's friendlier"
  is the exact change a later contributor would be tempted to make here;
  don't.
- Every byte stream goes through ``uploads.save_upload`` (which calls
  ``uploads.decode_image``), so a bad file becomes a ``RejectedUpload``
  entry, never an unhandled exception and never a bare 500.
- ``volume_id`` is validated against the open project *before* the upload
  loop opens, so a stale or invented id is a 404 rather than a foreign-key
  violation raised after the bytes are already on disk. Anything that
  writes must be preceded by everything that can refuse.
- ``GET /{page_id}/image`` resolves the served path from the current
  project root plus the server-generated ``page.source_path``, and asserts
  the resolved path is inside the project root before returning it. The
  client supplies only an integer row id — never a filename or path.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ...model import Page, Project, Store
from ...pipeline import run_import
from ..deps import get_current_project_path, get_project, get_store
from ..schemas import (
    PageResponse,
    PageUploadRejection,
    PageUploadResponse,
    RejectedUpload,
)
from ..uploads import UPLOAD_ERROR_DETAIL, display_name, save_upload
from .. import appconfig
from .volume import get_owned_volume

router = APIRouter()

PAGE_NOT_FOUND_DETAIL = "That page no longer exists — refresh and try again."
NO_READABLE_FILES_DETAIL = (
    "None of those files were readable images — try PNG, JPG or TIFF."
)


def _page_response(page: Page) -> PageResponse:
    """The one place a ``Page`` becomes a ``PageResponse``, so the
    ``image_url`` shape (``/api/pages/{id}/image``) is built in exactly one
    place."""
    return PageResponse(
        id=page.id,
        volume_id=page.volume_id,
        index=page.index,
        original_name=page.original_name,
        width=page.width,
        height=page.height,
        stage=page.stage,
        image_url=f"/api/pages/{page.id}/image",
    )


def _get_owned_page(page_id: int, store: Store) -> Page:
    page = store.page_by_id(page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=PAGE_NOT_FOUND_DETAIL)
    return page


@router.post(
    "/",
    status_code=201,
    response_model=None,
    responses={
        201: {"model": PageUploadResponse},
        400: {"model": PageUploadRejection},
    },
)
def upload_pages(
    volume_id: int,
    files: list[UploadFile],
    project_root: Path = Depends(get_current_project_path),
    store: Store = Depends(get_store),
    project: Project = Depends(get_project),
) -> PageUploadResponse | JSONResponse:
    """Upload one or more page files to ``volume_id``.

    Each file is handled independently: a bad file in a batch is reported
    in ``rejected`` without losing the good ones (an artist dropping twelve
    pages where one is a stray ``.txt`` should get eleven pages and one
    clear message, not eleven lost uploads). Every accepted page is run
    through ``run_import`` so its stage becomes ``panels`` immediately —
    01-UI-SPEC.md §1: a successful upload auto-advances past Import because
    there is nothing for the artist to review at that boundary yet.

    ``volume_id`` is checked **before the loop opens**, via the same
    ``get_owned_volume`` the volume routes use. That ordering is the point:
    ``save_upload`` writes bytes to ``pages/`` before ``store.add_page``
    runs, so a volume id that does not exist used to surface as a
    foreign-key ``IntegrityError`` — a bare 500 — with the image already
    on disk and no row pointing at it. A mid-batch abort also stranded the
    pages accepted earlier in the same request: persisted, never reported.

    Two return shapes, both declared in ``responses`` above so the OpenAPI
    contract carries them: 201 ``PageUploadResponse``, or 400
    ``PageUploadRejection`` when nothing in the batch was readable.
    """
    get_owned_volume(volume_id, project, store)

    accepted: list[PageResponse] = []
    rejected: list[RejectedUpload] = []

    for file in files:
        name = display_name(file.filename)
        data = file.file.read()
        try:
            saved = save_upload(
                data, project_root / appconfig.PAGES_DIR, project_root
            )
        except HTTPException:
            rejected.append(RejectedUpload(filename=name, detail=UPLOAD_ERROR_DETAIL))
            continue

        page = Page(
            volume_id=volume_id,
            source_path=saved.relative_path,
            index=store.next_page_index(volume_id),
            width=saved.width,
            height=saved.height,
            original_name=name,
        )
        try:
            page = store.add_page(page)
        except Exception:
            # The bytes are already written by this point. With the volume
            # checked above there is no *expected* failure left here, but an
            # unexpected one must not also leave a file nothing references
            # — an orphan in pages/ is invisible to the artist and never
            # cleaned up.
            saved.path.unlink(missing_ok=True)
            raise
        run_import(store, page)
        accepted.append(_page_response(page))

    if not accepted:
        # A plain HTTPException only carries `detail`; the frontend also
        # needs the per-file `rejected` reasons in a 400 body, so this one
        # response is built directly rather than raised.
        return JSONResponse(
            status_code=400,
            content=PageUploadRejection(
                detail=NO_READABLE_FILES_DETAIL, rejected=rejected
            ).model_dump(),
        )

    return PageUploadResponse(accepted=accepted, rejected=rejected)


@router.get("/")
def list_pages(
    volume_id: int,
    store: Store = Depends(get_store),
) -> list[PageResponse]:
    pages = store.pages_for_volume(volume_id)
    return [_page_response(p) for p in pages]


@router.get("/{page_id}")
def get_page(page_id: int, store: Store = Depends(get_store)) -> PageResponse:
    """"Open any page for editing" (PROJ-04) — Phase 2 hangs the panel
    editor off this route."""
    page = _get_owned_page(page_id, store)
    return _page_response(page)


@router.get("/{page_id}/image")
def get_page_image(
    page_id: int,
    store: Store = Depends(get_store),
    project_root: Path = Depends(get_current_project_path),
) -> FileResponse:
    page = _get_owned_page(page_id, store)
    resolved = (project_root / page.source_path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        # source_path is always server-generated (uploads.save_upload); this
        # assertion is what keeps that true if the column is ever populated
        # from anywhere else. Never accept a path or filename from the query
        # string here.
        raise HTTPException(status_code=404, detail=PAGE_NOT_FOUND_DETAIL)
    if not resolved.is_file():
        # Starlette's FileResponse raises at *send* time for a missing
        # file, which surfaces as a 500. D-04's "copy the folder" model
        # actively encourages the artist to move these files around
        # outside the app, so a page whose image is gone is a routine
        # state, not a crash — same neutral copy as an unknown page id.
        raise HTTPException(status_code=404, detail=PAGE_NOT_FOUND_DETAIL)
    return FileResponse(resolved)


@router.delete("/{page_id}", status_code=204)
def delete_page(page_id: int, store: Store = Depends(get_store)) -> None:
    """204. The image file is left on disk, for the same reason as volumes
    (T-01-DISK, accepted): orphaned bytes are recoverable, a page an artist
    wanted back is not."""
    _get_owned_page(page_id, store)
    store.delete_page(page_id)

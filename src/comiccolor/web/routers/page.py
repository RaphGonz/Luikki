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

from ...model import Page, PipelineStage, Project, Store
from ...pipeline import STAGES, next_stage, run_import, run_stage, stage_for
from ...pipeline.runner import BubbleDetectionFailed, StageNotImplementedError
from ..deps import get_current_project_path, get_project, get_store
from ..schemas import (
    GoBackRequest,
    GoBackTargetResponse,
    PageResponse,
    PageUploadRejection,
    PageUploadResponse,
    RejectedUpload,
    StageConfirmResponse,
)
from ..uploads import UPLOAD_ERROR_DETAIL, display_name, read_capped, save_upload
from .. import appconfig
from .volume import get_owned_volume

router = APIRouter()

PAGE_NOT_FOUND_DETAIL = "That page no longer exists — refresh and try again."
NO_READABLE_FILES_DETAIL = (
    "None of those files were readable images — try PNG, JPG or TIFF."
)
# UI-SPEC §4's exact empty-state body, reused verbatim as the server-side
# refusal detail so the disabled-button tooltip and the 409 the client would
# get if it ever bypassed the disabled state say the same thing.
NO_PANELS_DETAIL = "Draw at least one panel before continuing."
ALREADY_AT_LAST_STAGE_DETAIL = "This page has already reached its final stage."
GO_BACK_TARGET_NOT_EARLIER_DETAIL = (
    "That stage isn't earlier than where this page is now — refresh and try again."
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


def get_owned_page(page_id: int, store: Store) -> Page:
    """The page, or a 404 if it does not belong to the currently open
    project.

    Public rather than underscore-prefixed because ``panel.py`` and
    ``protected.py`` call it too (same cross-router import precedent this
    module already sets by importing ``get_owned_volume`` from
    ``.volume``): a panel or mask names its page by raw id, and that id
    needs the same check the page routes give it.
    """
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
        try:
            # Capped at read time, not after: an oversized file in a batch
            # is one more RejectedUpload, not 64MB+ of resident bytes.
            data = read_capped(file.file)
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
    page = get_owned_page(page_id, store)
    return _page_response(page)


@router.get("/{page_id}/image")
def get_page_image(
    page_id: int,
    store: Store = Depends(get_store),
    project_root: Path = Depends(get_current_project_path),
) -> FileResponse:
    page = get_owned_page(page_id, store)
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
    get_owned_page(page_id, store)
    store.delete_page(page_id)


@router.post("/{page_id}/stage/confirm", response_model=StageConfirmResponse)
def confirm_stage(page_id: int, store: Store = Depends(get_store)) -> StageConfirmResponse:
    """Advance a page exactly one stage (D-06/D-07/D-10) and run the
    arriving stage's runner, if it has one.

    ``next_stage(page.stage)`` names the one step this route is allowed to
    take — never a client-supplied target, never a walk of the whole chain
    (T-2-35). 409 with ``ALREADY_AT_LAST_STAGE_DETAIL`` when there is none
    (the page is already at ``export``).

    Leaving ``panels`` is refused (409, ``NO_PANELS_DETAIL``) when the page
    currently has zero panels. UI-SPEC §4's reasoning: Phase 1 had no
    delete-heavy surface, so this gate never had to guard against "the
    artist deleted everything." Phase 2 does — D-18 deliberately over-
    proposes panels and D-19 expects the artist to prune them constantly —
    so a page must not be allowed to reach Zones with nothing to segment.
    The Protected gate carries no equivalent guard: a splash page with zero
    speech bubbles is a legitimate page (D-24), so leaving ``protected`` is
    never blocked by mask count.

    The stage is advanced first, then the *target* stage's runner (if any)
    is run against the now-current page. A ``BubbleDetectionFailed`` raised
    by that runner is caught here and turned into ``detection_failed=True``
    plus ``detection_message=str(exc)`` rather than a 5xx — 02-RESEARCH.md
    Pitfall 6's framing: a failed *proposal* is not a failed *stage
    transition*. PROT-01 is "detects and proposes", PROT-02's hand-drawing
    is the guaranteed fallback, so an artist must never be stuck before
    their own tools over a detector hiccup (T-2-17). A
    ``StageNotImplementedError`` (the target stage is declared but has no
    runner yet, e.g. confirming out of ``zones``) is caught and silently
    ignored — it must never reach the artist as an error, since
    01-UI-SPEC.md §1 already forbids the UI from distinguishing "no runner"
    from "not yet reached". This is also how confirming out of ``zones``
    resolves: the stage advances to ``propose`` and nothing runs, rather
    than refusing with a 409 the artist has no way to act on.
    """
    page = get_owned_page(page_id, store)
    target = next_stage(page.stage)
    if target is None:
        raise HTTPException(status_code=409, detail=ALREADY_AT_LAST_STAGE_DETAIL)

    if page.stage == PipelineStage.PANELS and not store.panels_for_page(page_id):
        raise HTTPException(status_code=409, detail=NO_PANELS_DETAIL)

    store.set_page_stage(page_id, target)
    page.stage = target

    detection_failed = False
    detection_message: str | None = None
    try:
        run_stage(store, page, target)
    except BubbleDetectionFailed as exc:
        detection_failed = True
        detection_message = str(exc)
    except StageNotImplementedError:
        pass

    updated = get_owned_page(page_id, store)
    return StageConfirmResponse(
        page=_page_response(updated),
        detection_failed=detection_failed,
        detection_message=detection_message,
    )


def _go_back_targets(store: Store, page: Page) -> list[GoBackTargetResponse]:
    """01-UI-SPEC.md §3, extended by 02-UI-SPEC.md §8: every returned target
    carries a sentence computed from real counts at the moment the dialog
    opens. A target whose cost this phase has no formula for is simply
    absent from the list — never a vague sentence with no numbers in it.

    Phase 2 only defines a cost formula for two targets: going back to
    ``panels`` (discards protected masks, re-runs bubble detection) and
    going back to ``import`` (discards panels and protected masks, re-runs
    panel detection). Any other candidate stage strictly earlier than
    ``page.stage`` — there are none yet reachable within this phase's live
    stages, but the loop is written to generalise — is skipped rather than
    guessed at.
    """
    current = stage_for(page.stage)
    current_index = STAGES.index(current)
    targets: list[GoBackTargetResponse] = []

    for candidate in STAGES[:current_index]:
        if candidate.name == PipelineStage.PANELS:
            masks = len(store.protected_for_page(page.id))
            body = (
                f"This discards {masks} protected mask{'' if masks == 1 else 's'}"
                " and re-runs bubble detection for the whole page."
            )
            discarded = masks
        elif candidate.name == PipelineStage.IMPORT:
            panels = len(store.panels_for_page(page.id))
            masks = len(store.protected_for_page(page.id))
            body = (
                f"This discards {panels} panel polygon{'' if panels == 1 else 's'}"
                f" and {masks} protected mask{'' if masks == 1 else 's'}, and"
                " re-runs panel detection for the whole page."
            )
            discarded = panels + masks
        else:
            continue

        targets.append(
            GoBackTargetResponse(
                stage=candidate.name,
                display_name=candidate.display_name,
                heading=f"Go back to {candidate.display_name}?",
                body=body,
                confirm_label=(
                    f"Go back and discard {discarded} edit"
                    f"{'' if discarded == 1 else 's'}"
                ),
                cancel_label=f"Stay on {current.display_name}",
                discarded_count=discarded,
            )
        )

    return targets


@router.get(
    "/{page_id}/stage/go-back-targets", response_model=list[GoBackTargetResponse]
)
def go_back_targets(
    page_id: int, store: Store = Depends(get_store)
) -> list[GoBackTargetResponse]:
    page = get_owned_page(page_id, store)
    return _go_back_targets(store, page)


@router.post("/{page_id}/stage/go-back", response_model=StageConfirmResponse)
def go_back(
    page_id: int, body: GoBackRequest, store: Store = Depends(get_store)
) -> StageConfirmResponse:
    """D-08: going back is costed and explicit. The artist has already seen
    and confirmed the exact number this dialog's ``GET .../go-back-targets``
    computed; this route re-derives nothing and simply performs the discard
    that sentence promised.

    409 (``GO_BACK_TARGET_NOT_EARLIER_DETAIL``) when ``body.target`` is not
    strictly earlier than ``page.stage`` in ``STAGES`` — a client-supplied
    target is never trusted to be a legitimate backward move (T-2-35).

    Going back to ``panels`` discards ALL of the page's protected masks —
    detector-proposed and hand-drawn alike, ``touched`` or not. This matches
    02-UI-SPEC.md §8's sentence literally: there is no "keep the ones I
    touched" branch, and none should be added. The artist has already
    confirmed the exact count in the dialog, and partial preservation would
    add real complexity to a deliberately heavyweight action for a case
    Phase 2 was never asked to support. Going back to ``import`` discards
    both the panels and the protected masks, for the same reason.

    Re-running detection is not done here — it happens on the artist's next
    forward confirm through ``confirm_stage``, which is what "re-runs bubble
    detection for the whole page" describes from the artist's point of view.
    Do not add a redundant detection call to this route.
    """
    page = get_owned_page(page_id, store)
    current_index = STAGES.index(stage_for(page.stage))
    target_index = STAGES.index(stage_for(body.target))
    if target_index >= current_index:
        raise HTTPException(
            status_code=409, detail=GO_BACK_TARGET_NOT_EARLIER_DETAIL
        )

    if body.target == PipelineStage.PANELS:
        store.delete_protected_for_page(page_id)
    elif body.target == PipelineStage.IMPORT:
        store.delete_protected_for_page(page_id)
        store.delete_panels_for_page(page_id)

    store.set_page_stage(page_id, body.target)
    updated = get_owned_page(page_id, store)
    return StageConfirmResponse(page=_page_response(updated))

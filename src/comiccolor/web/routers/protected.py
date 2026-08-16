"""Protected-mask routes.

PROT-01/02/03: bubble and SFX masks, detector-proposed or hand-drawn, never
coloured. Registered as an empty stub by plan 02-05; plan 02-09 (this file)
adds the five routes below: list, hand-draw, move-vertex, replace-polygon,
delete.

Deliberately every route in this module is a plain ``def``, never
``async def``, because ``get_store`` is a sync generator dependency and
``Store`` is documented as one-per-thread; an ``async def`` route would
resolve that dependency on a different thread than the one running the
handler (see ``deps.py``'s docstring and ``palette.py``'s identical note).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...model import ProtectedMask, Store
from ...segmentation.protected import protected_bbox_and_area
from ..deps import get_store
from ..schemas import (
    PolygonUpdateRequest,
    ProtectedMaskCreateRequest,
    ProtectedMaskListResponse,
    ProtectedMaskResponse,
    VertexUpdateRequest,
)
from .page import get_owned_page

router = APIRouter()

PROTECTED_MASK_NOT_FOUND_DETAIL = (
    "That protected mask no longer exists — refresh and try again."
)
VERTEX_OUT_OF_RANGE_DETAIL = (
    "That vertex is no longer part of this shape — refresh and try again."
)
POLYGON_OUT_OF_PAGE_DETAIL = (
    "That shape reaches outside the page — drag its points back inside and try again."
)
TOO_MANY_MASKS_DETAIL = (
    "This page already has as many protected masks as it can hold — delete one"
    " before adding another."
)
# T-2-07: a real page has tens of bubbles; a request pushing past this is a
# bug or hostile input, and protected_bbox_and_area rasterises once per
# mask, so an unbounded count is unbounded work per request too.
MAX_MASKS_PER_PAGE = 256


def _protected_response(mask: ProtectedMask) -> ProtectedMaskResponse:
    """The one adapter from the domain dataclass to the HTTP contract."""
    return ProtectedMaskResponse(
        id=mask.id,
        page_id=mask.page_id,
        kind=mask.kind,
        polygon=mask.polygon,
        touched=mask.touched,
        area=mask.area,
        bbox=mask.bbox,
    )


def _get_owned_protected_mask(mask_id: int, store: Store) -> ProtectedMask:
    """The mask, or a 404 if it — or its page — does not belong to the
    currently open project.

    Mirrors ``get_owned_volume``'s T-01-IDOR framing (T-2-02): a stale
    ``mask_id`` from a closed project is a correctness refusal, not access
    control, since there is exactly one artist and one open project.
    """
    mask = store.protected_mask_by_id(mask_id)
    if mask is None:
        raise HTTPException(status_code=404, detail=PROTECTED_MASK_NOT_FOUND_DETAIL)
    get_owned_page(mask.page_id, store)
    return mask


def _polygon_within_page(polygon: list[tuple[int, int]], width: int, height: int) -> bool:
    """T-2-03: every create and write checks page-space vertices against the
    page's own bounds before anything reaches ``cv2.fillPoly``."""
    return all(0 <= x <= width and 0 <= y <= height for x, y in polygon)


def _masks_response(store: Store, page_id: int) -> ProtectedMaskListResponse:
    """The full-list payload ``list_protected`` returns directly.

    ``detection_failed=False`` and ``detection_message=None`` are hardcoded
    here — those two fields are only ever set by the stage-confirm route
    (plan 02-11), which runs the detector and reports its own outcome
    inline. A plain list read has no detection run to report on; do not wire
    a detection result into this helper.
    """
    masks = store.protected_for_page(page_id)
    return ProtectedMaskListResponse(
        masks=[_protected_response(m) for m in masks],
        detection_failed=False,
        detection_message=None,
    )


@router.get("/pages/{page_id}/protected", response_model=ProtectedMaskListResponse)
def list_protected(page_id: int, store: Store = Depends(get_store)) -> ProtectedMaskListResponse:
    """PROT-01.

    D-20: these masks are page-scoped, so a bubble straddling two panels
    appears once here and is clipped to a panel only at segmentation time by
    ``rasterize_protected_for_panel``. There is deliberately no per-panel
    listing route; adding one would reintroduce the panel scope D-20
    removed.
    """
    get_owned_page(page_id, store)
    return _masks_response(store, page_id)


@router.post(
    "/pages/{page_id}/protected",
    response_model=ProtectedMaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_mask(
    page_id: int,
    body: ProtectedMaskCreateRequest,
    store: Store = Depends(get_store),
) -> ProtectedMaskResponse:
    """PROT-02: the artist draws a mask by hand, choosing bubble or SFX
    (D-24 — the detector only ever proposes bubbles, so the ``kind`` choice
    comes from the request, not inferred).

    Born ``touched=True``: UI-SPEC §3's dashed outline means "detector-
    proposed and not yet looked at", which a mask the artist just drew never
    is — it renders solid from the moment it exists.
    """
    page = get_owned_page(page_id, store)
    if not _polygon_within_page(body.polygon, page.width, page.height):
        raise HTTPException(status_code=422, detail=POLYGON_OUT_OF_PAGE_DETAIL)
    if len(store.protected_for_page(page_id)) >= MAX_MASKS_PER_PAGE:
        raise HTTPException(status_code=409, detail=TOO_MANY_MASKS_DETAIL)

    area, bbox = protected_bbox_and_area(body.polygon, page.width, page.height)
    mask = store.add_protected_mask(
        ProtectedMask(
            page_id=page_id,
            kind=body.kind,
            polygon=list(body.polygon),
            touched=True,
            area=area,
            bbox=bbox,
        )
    )
    return _protected_response(mask)


@router.patch(
    "/protected/{mask_id}/vertex/{vertex_index}", response_model=ProtectedMaskResponse
)
def move_mask_vertex(
    mask_id: int,
    vertex_index: int,
    body: VertexUpdateRequest,
    store: Store = Depends(get_store),
) -> ProtectedMaskResponse:
    """PROT-03: reshape one vertex.

    Same T-01-FLOOD contract as the panel router: one write per drag,
    committed on ``pointerup``, never one write per ``pointermove``.
    ``store.update_protected_mask_polygon`` unconditionally sets
    ``touched``, which is what flips a detector-proposed mask from dashed to
    solid the instant it is reshaped.
    """
    mask = _get_owned_protected_mask(mask_id, store)
    if not (0 <= vertex_index < len(mask.polygon)):
        raise HTTPException(status_code=400, detail=VERTEX_OUT_OF_RANGE_DETAIL)
    page = get_owned_page(mask.page_id, store)

    polygon = list(mask.polygon)
    polygon[vertex_index] = (body.x, body.y)
    if not _polygon_within_page(polygon, page.width, page.height):
        raise HTTPException(status_code=422, detail=POLYGON_OUT_OF_PAGE_DETAIL)

    area, bbox = protected_bbox_and_area(polygon, page.width, page.height)
    store.update_protected_mask_polygon(mask_id, polygon, area, bbox)

    updated = store.protected_mask_by_id(mask_id)
    if updated is None:
        # The row can disappear between the ownership check above and this
        # re-read (a concurrent DELETE) — the same re-read guard palette.py's
        # update_palette_entry uses.
        raise HTTPException(status_code=404, detail=PROTECTED_MASK_NOT_FOUND_DETAIL)
    return _protected_response(updated)


@router.patch("/protected/{mask_id}/polygon", response_model=ProtectedMaskResponse)
def replace_mask_polygon(
    mask_id: int,
    body: PolygonUpdateRequest,
    store: Store = Depends(get_store),
) -> ProtectedMaskResponse:
    """PROT-03: vertex insert and vertex delete both arrive here as a whole
    new polygon, same as the panel router's wholesale-replace route — the
    client computes the new vertex list, this route only validates and
    persists it (and, via ``update_protected_mask_polygon``, sets
    ``touched``)."""
    mask = _get_owned_protected_mask(mask_id, store)
    page = get_owned_page(mask.page_id, store)
    if not _polygon_within_page(body.polygon, page.width, page.height):
        raise HTTPException(status_code=422, detail=POLYGON_OUT_OF_PAGE_DETAIL)

    area, bbox = protected_bbox_and_area(body.polygon, page.width, page.height)
    store.update_protected_mask_polygon(mask_id, list(body.polygon), area, bbox)

    updated = store.protected_mask_by_id(mask_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=PROTECTED_MASK_NOT_FOUND_DETAIL)
    return _protected_response(updated)


@router.delete("/protected/{mask_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mask(mask_id: int, store: Store = Depends(get_store)) -> None:
    """D-19/UI-SPEC §5: no confirmation dialog, no server-side confirm step
    — in-editor undo is the safety net. 204 with no body, following the
    palette router's convention: deleting a mask changes nothing about any
    other mask (unlike a panel delete, which renumbers)."""
    _get_owned_protected_mask(mask_id, store)
    store.delete_protected_mask(mask_id)

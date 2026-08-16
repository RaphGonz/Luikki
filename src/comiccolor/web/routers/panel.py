"""Panel routes.

PAN-01/02/03: correctable panel boundaries in reading order. Registered as
an empty stub by plan 02-05; this plan (02-08) adds the five routes below —
list, create, move-vertex, replace-polygon, delete — plus the reading-order
recompute helper every mutating route shares.

Deliberately every route in this module is a plain ``def``, never
``async def``, because ``get_store`` is a sync generator dependency and
``Store`` is documented as one-per-thread; an ``async def`` route would
resolve that dependency on a different thread than the one running the
handler (see ``deps.py``'s docstring and ``palette.py``'s identical note).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...model import Page, Panel, Store
from ...pipeline.runner import run_panels
from ..deps import get_store
from ..schemas import (
    PanelCreateRequest,
    PanelListResponse,
    PanelResponse,
    PolygonUpdateRequest,
    VertexUpdateRequest,
)
from .page import get_owned_page

router = APIRouter()

PANEL_NOT_FOUND_DETAIL = "That panel no longer exists — refresh and try again."
VERTEX_OUT_OF_RANGE_DETAIL = (
    "That vertex is no longer part of this shape — refresh and try again."
)
POLYGON_OUT_OF_PAGE_DETAIL = (
    "That shape falls outside the page — refresh and try again."
)
DETECT_WOULD_DISCARD_DETAIL = (
    "This page already has panels. Delete them first if you want to detect again — "
    "detection replaces every panel, including the ones you corrected."
)


def _panel_response(panel: Panel) -> PanelResponse:
    """The one adapter from the domain dataclass to the HTTP contract."""
    return PanelResponse(
        id=panel.id,
        page_id=panel.page_id,
        x=panel.x,
        y=panel.y,
        width=panel.width,
        height=panel.height,
        reading_order=panel.reading_order,
        polygon=panel.polygon,
    )


def _panel_list_response(store: Store, page_id: int) -> PanelListResponse:
    """The whole page's panel list, in reading order.

    The one implementation of "return the whole updated list" — every
    mutating panel route in plan 02-08 returns this, so reading order is
    always server-recomputed and never a second source of truth.
    """
    return PanelListResponse(
        panels=[_panel_response(p) for p in store.panels_for_page(page_id)]
    )


def _get_owned_panel(panel_id: int, store: Store) -> Panel:
    """The panel, or a 404 if it — or its page — does not belong to the
    currently open project.

    Mirrors ``get_owned_volume``'s T-01-IDOR framing (T-2-02): a stale
    ``panel_id`` from a closed project is a correctness refusal, not access
    control, since there is exactly one artist and one open project.
    """
    panel = store.panel_by_id(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=PANEL_NOT_FOUND_DETAIL)
    get_owned_page(panel.page_id, store)
    return panel


def _assert_polygon_in_page(polygon: list[tuple[int, int]], page: Page) -> None:
    """422 when a vertex falls outside ``(0, 0, page.width, page.height)``.

    ``PixelCoord`` already bounds every coordinate to ``[0, MAX_PAGE_PIXEL]``
    absolutely (T-2-01); this is the per-page bound that absolute schema
    range cannot express (T-2-03) — a vertex that is in-range for the schema
    but off the edge of *this* page's raster would still reach
    ``cv2.fillPoly`` downstream without this check.
    """
    for x, y in polygon:
        if not (0 <= x <= page.width and 0 <= y <= page.height):
            raise HTTPException(status_code=422, detail=POLYGON_OUT_OF_PAGE_DETAIL)


def _recompute_reading_order(store: Store, page_id: int) -> None:
    """The server is the single source of truth for panel reading order.

    Every mutating route in this module calls this last, before returning
    the page's whole panel list (``_panel_list_response``). This is the
    resolved answer to the phase's open question about live renumbering: the
    server recomputes on every mutation, the client renders what it is
    given, and ``_reading_order()``'s tier-grouping geometry is deliberately
    never ported to TypeScript — there is exactly one implementation of it,
    here.

    Direction is a backend parameter, fixed at ``"ltr"`` this phase per
    UI-SPEC §7: the artist sees it only as the toolbar's non-interactive
    "Reading order: Left → Right" readout, never a control that could drift
    out of sync with what the server actually computed.

    Imports ``_reading_order`` inside the function body, not at module
    level, so this router does not pull in ``segmentation.panels``'s
    OpenCV import just to serve a list request.
    """
    from ...segmentation.panels import PanelBox, _reading_order

    panels = store.panels_for_page(page_id)
    boxes: list[PanelBox] = []
    for panel in panels:
        box = PanelBox(panel.x, panel.y, panel.width, panel.height)
        box.panel_id = panel.id  # type: ignore[attr-defined]
        boxes.append(box)

    ordered = _reading_order(boxes, "ltr")
    for index, box in enumerate(ordered):
        store.set_panel_reading_order(box.panel_id, index)  # type: ignore[attr-defined]


@router.get("/pages/{page_id}/panels", response_model=PanelListResponse)
def list_panels(page_id: int, store: Store = Depends(get_store)) -> PanelListResponse:
    """PAN-01: a page's panels as polygons, in reading order."""
    get_owned_page(page_id, store)
    return _panel_list_response(store, page_id)


@router.post("/pages/{page_id}/panels/detect", response_model=PanelListResponse)
def detect_panels(page_id: int, store: Store = Depends(get_store)) -> PanelListResponse:
    """PAN-01: run panel detection for this page, on the artist's command.

    ``run_panels`` existed and was registered in the stage registry from
    plan 02-07, but nothing ever called it, so a page sat at the ``panels``
    stage with no panels forever. D-10 is why the registry itself cannot be
    the caller — it declares, it never orchestrates — so the trigger has to
    be an explicit request, and the artist pressing a button is the most
    honest one: detection is a proposal they choose to ask for, not
    something that happens to their page.

    ``run_panels`` deletes the page's existing panels before re-running, so
    this route refuses when panels already exist rather than silently
    discarding the artist's corrections. Clearing them first is a
    deliberate act with its own confirmation, not a side effect of asking
    for a fresh detection.
    """
    page = get_owned_page(page_id, store)
    if store.panels_for_page(page_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DETECT_WOULD_DISCARD_DETAIL,
        )
    run_panels(store, page)
    return _panel_list_response(store, page_id)


@router.post(
    "/pages/{page_id}/panels",
    response_model=PanelListResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_panel(
    page_id: int, body: PanelCreateRequest, store: Store = Depends(get_store)
) -> PanelListResponse:
    """PAN-03: draw a panel the detector missed.

    The bounding box is derived from the polygon here, the same arithmetic
    ``Store.update_panel_polygon`` uses for an edit — a created panel's box
    and polygon start in agreement, never out of sync by construction.
    """
    page = get_owned_page(page_id, store)
    _assert_polygon_in_page(body.polygon, page)

    xs = [v[0] for v in body.polygon]
    ys = [v[1] for v in body.polygon]
    x, y = min(xs), min(ys)

    panel = Panel(
        page_id=page_id,
        x=x,
        y=y,
        width=max(xs) - x,
        height=max(ys) - y,
        reading_order=len(store.panels_for_page(page_id)),
        polygon=list(body.polygon),
    )
    store.add_panel(panel)
    _recompute_reading_order(store, page_id)
    return _panel_list_response(store, page_id)


@router.patch("/panels/{panel_id}/vertex/{vertex_index}", response_model=PanelListResponse)
def move_vertex(
    panel_id: int,
    vertex_index: int,
    body: VertexUpdateRequest,
    store: Store = Depends(get_store),
) -> PanelListResponse:
    """PAN-02: drag one vertex.

    T-01-FLOOD contract (T-2-28, transfer): the client commits on
    ``pointerup``, never on ``pointermove``, so this route is called once
    per drag, not once per frame. A client change that starts calling this
    on every ``pointermove`` would be a regression against that contract,
    not normal traffic.
    """
    panel = _get_owned_panel(panel_id, store)
    if not (0 <= vertex_index < len(panel.polygon)):
        raise HTTPException(status_code=400, detail=VERTEX_OUT_OF_RANGE_DETAIL)

    page = get_owned_page(panel.page_id, store)
    point = (body.x, body.y)
    _assert_polygon_in_page([point], page)

    store.update_panel_vertex(panel_id, vertex_index, point)

    updated = store.panel_by_id(panel_id)
    if updated is None:
        # The row can disappear between the mutation above and this re-read
        # (a concurrent DELETE) — same shape as update_palette_entry's guard.
        raise HTTPException(status_code=404, detail=PANEL_NOT_FOUND_DETAIL)

    _recompute_reading_order(store, updated.page_id)
    return _panel_list_response(store, updated.page_id)


@router.patch("/panels/{panel_id}/polygon", response_model=PanelListResponse)
def replace_polygon(
    panel_id: int, body: PolygonUpdateRequest, store: Store = Depends(get_store)
) -> PanelListResponse:
    """PAN-02: insert or delete a vertex.

    Both arrive here as a whole new polygon — there is no separate insert or
    delete route. ``Polygon``'s ``min_length=3`` (schemas.py) is what enforces
    UI-SPEC §2's "a panel needs at least 3 points" refusal on the wire; the
    client shows the inline toast rather than relying on the 422 itself
    reaching the artist as an error.
    """
    panel = _get_owned_panel(panel_id, store)
    page = get_owned_page(panel.page_id, store)
    _assert_polygon_in_page(body.polygon, page)

    store.update_panel_polygon(panel_id, list(body.polygon))

    updated = store.panel_by_id(panel_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=PANEL_NOT_FOUND_DETAIL)

    _recompute_reading_order(store, updated.page_id)
    return _panel_list_response(store, updated.page_id)


@router.delete("/panels/{panel_id}", response_model=PanelListResponse)
def delete_panel(panel_id: int, store: Store = Depends(get_store)) -> PanelListResponse:
    """PAN-03: delete a panel the detector invented.

    Returns 200 with the updated list rather than the palette router's 204,
    because deleting a panel renumbers every panel after it and the client
    must not guess the new order.

    D-19/UI-SPEC §5: there is no confirmation dialog and no server-side
    confirm step here — deletion is routine, not destructive-confirmed, and
    in-editor undo is the safety net (T-2-29, accepted).
    """
    panel = _get_owned_panel(panel_id, store)
    page_id = panel.page_id
    store.delete_panel(panel_id)
    _recompute_reading_order(store, page_id)
    return _panel_list_response(store, page_id)

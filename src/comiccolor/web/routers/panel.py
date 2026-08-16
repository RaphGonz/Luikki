"""Panel routes.

PAN-01/02/03: correctable panel boundaries in reading order. Registered here
by plan 02-05 with no routes of its own — plan 02-08 adds them.

Deliberately every route in this module is a plain ``def``, never
``async def``, because ``get_store`` is a sync generator dependency and
``Store`` is documented as one-per-thread; an ``async def`` route would
resolve that dependency on a different thread than the one running the
handler (see ``deps.py``'s docstring and ``palette.py``'s identical note).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...model import Panel, Store
from ..deps import get_store
from ..schemas import PanelListResponse, PanelResponse
from .page import get_owned_page

router = APIRouter()

PANEL_NOT_FOUND_DETAIL = "That panel no longer exists — refresh and try again."
VERTEX_OUT_OF_RANGE_DETAIL = (
    "That vertex is no longer part of this shape — refresh and try again."
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

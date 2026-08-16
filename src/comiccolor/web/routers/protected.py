"""Protected-mask routes.

PROT-01/02/03: bubble and SFX masks, detector-proposed or hand-drawn, never
coloured. Registered here by plan 02-05 with no routes of its own — plan
02-09 adds them.

Deliberately every route in this module is a plain ``def``, never
``async def``, because ``get_store`` is a sync generator dependency and
``Store`` is documented as one-per-thread; an ``async def`` route would
resolve that dependency on a different thread than the one running the
handler (see ``deps.py``'s docstring and ``palette.py``'s identical note).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...model import ProtectedMask, Store
from ..deps import get_store
from ..schemas import ProtectedMaskResponse
from .page import get_owned_page

router = APIRouter()

PROTECTED_MASK_NOT_FOUND_DETAIL = (
    "That protected mask no longer exists — refresh and try again."
)
VERTEX_OUT_OF_RANGE_DETAIL = (
    "That vertex is no longer part of this shape — refresh and try again."
)


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

"""Palette routes.

PAL-01 (swatch upload extraction), PAL-03 (hand add/edit/delete/rename) and
PAL-04 (single-row recolour with the affected-pages count). Registered as
an empty stub by plan 01-06; filled by plan 01-09.

D-02: every route here is project-scoped, never volume-scoped, which is
what makes the palette accumulate across every volume in the project.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...model import PaletteEntry, Project, Store
from ..deps import get_project, get_store
from ..schemas import (
    PaletteEntryCreateRequest,
    PaletteEntryResponse,
    PaletteEntryUpdateRequest,
    PaletteUpdateResponse,
)

router = APIRouter()

ENTRY_NOT_FOUND_DETAIL = "That colour is no longer in the palette — refresh and try again."
AUTO_NAME_PREFIX = "Colour "


def _entry_response(entry: PaletteEntry) -> PaletteEntryResponse:
    """The one adapter from the domain dataclass to the HTTP contract."""
    return PaletteEntryResponse(
        id=entry.id,
        rgb=entry.rgb,
        label=entry.label,
        entity_id=entry.entity_id,
        revision=entry.revision,
    )


def _next_colour_number(entries: list[PaletteEntry]) -> int:
    """One past the highest existing auto-name in the project.

    D-16: a second swatch upload must produce ``Colour 5``, ``Colour 6``
    onward rather than colliding with ``Colour 1`` from the first upload.
    Hand-created or renamed entries (non-numeric or non-prefixed labels)
    are simply ignored by this scan, not an error.
    """
    highest = 0
    for entry in entries:
        if entry.label.startswith(AUTO_NAME_PREFIX):
            suffix = entry.label[len(AUTO_NAME_PREFIX) :]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return highest + 1


@router.get("", response_model=list[PaletteEntryResponse])
def list_palette(
    store: Store = Depends(get_store), project: Project = Depends(get_project)
) -> list[PaletteEntryResponse]:
    """The whole project's palette (D-02) — not scoped to any one volume."""
    return [_entry_response(e) for e in store.palette_for_project(project.id)]


@router.post(
    "", response_model=PaletteEntryResponse, status_code=status.HTTP_201_CREATED
)
def create_palette_entry(
    body: PaletteEntryCreateRequest,
    store: Store = Depends(get_store),
    project: Project = Depends(get_project),
) -> PaletteEntryResponse:
    """PAL-03's "+ Add Colour": create an entry entirely by hand.

    Reachable from the same screen as an extraction result at any time
    (01-UI-SPEC.md §4), including seconds after a swatch upload — this
    route does not care whether the project already has entries or none.
    """
    entry = store.add_palette_entry(
        PaletteEntry(project_id=project.id, rgb=body.rgb, label=body.label)
    )
    return _entry_response(entry)


@router.patch("/{entry_id}", response_model=PaletteUpdateResponse)
def update_palette_entry(
    entry_id: int,
    body: PaletteEntryUpdateRequest,
    store: Store = Depends(get_store),
) -> PaletteUpdateResponse:
    """PAL-03 rename and PAL-04 recolour, marshalled onto the two ``Store``
    methods that already implement both mechanics end to end.

    A rename touches only the label. A colour change calls the existing
    single-row colour update and nothing else — no region row is touched,
    no page's pipeline position moves, and no warning or confirmation is
    raised anywhere in this handler. §213 is explicit that a palette edit
    is never a stage regression, at any stage, including on a fully
    reviewed page; this handler is HTTP marshalling onto that mechanic,
    not a reimplementation of it. The response also reports how many pages
    the colour touches, via the existing repaint-set query, which is what
    01-UI-SPEC.md §6's "Updated on {N} page{s}" toast renders.
    """
    entry = store.palette_entry_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND_DETAIL)

    if body.label is not None:
        store.update_palette_label(entry_id, body.label)
    if body.rgb is not None:
        store.update_palette_rgb(entry_id, body.rgb)

    updated = store.palette_entry_by_id(entry_id)
    pages_affected = len(store.pages_affected_by(entry_id))
    return PaletteUpdateResponse(
        entry=_entry_response(updated), pages_affected=pages_affected
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_palette_entry(entry_id: int, store: Store = Depends(get_store)) -> None:
    """PAL-03 delete.

    ``region.palette_entry_id`` is ``ON DELETE SET NULL`` at the schema
    level, so a region that referenced the deleted colour becomes
    unpainted rather than silently keeping a wrong colour baked in
    anywhere — an unpainted region is recoverable, a silently wrong one
    is not.
    """
    entry = store.palette_entry_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND_DETAIL)
    store.delete_palette_entry(entry_id)

"""Palette routes.

PAL-01 (swatch upload extraction), PAL-03 (hand add/edit/delete/rename) and
PAL-04 (single-row recolour with the affected-pages count). Registered as
an empty stub by plan 01-06; filled by plan 01-09.

D-02: every route here is project-scoped, never volume-scoped, which is
what makes the palette accumulate across every volume in the project.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from ...colour import extract_palette
from ...model import PaletteEntry, Project, Store
from .. import uploads
from ..appconfig import REFERENCES_DIR
from ..deps import get_current_project_path, get_project, get_store
from ..schemas import (
    PaletteEntryCreateRequest,
    PaletteEntryResponse,
    PaletteEntryUpdateRequest,
    PaletteUpdateResponse,
    SwatchExtractResponse,
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


@router.post(
    "/swatch",
    response_model=SwatchExtractResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_swatch(
    file: UploadFile,
    store: Store = Depends(get_store),
    project: Project = Depends(get_project),
    project_path: Path = Depends(get_current_project_path),
) -> SwatchExtractResponse:
    """PAL-01: a swatch image becomes real, persisted, auto-named entries.

    Unlike the character-sheet path (plan 01-10), which returns ephemeral
    proposals for individual accept or reject, this route persists every
    extracted colour immediately. That asymmetry is deliberate and comes
    from the requirements themselves: PAL-01 says the app *creates* entries
    from a swatch, while PAL-02 says the app *proposes* entries from a
    character sheet. The two paths are not the same mechanic and must not
    be unified later.

    The swatch path never runs the character sheet's ink/paper pre-pass —
    an artist's deliberate black or white chip on a swatch is real data,
    not noise to filter (D-14 scopes that pre-pass to the sheet path
    only), so the extractor is called with its default behaviour.

    Entries are auto-named ``Colour 1..N``, continuing from the highest
    existing auto-name in the project so a second upload never collides
    with the first (D-16) — no naming prompt ever blocks a working
    palette.

    Deliberately a sync ``def``, not ``async def``: FastAPI runs a sync
    path operation and every sync dependency it needs (``get_store``'s
    per-request sqlite connection) on the same thread-pool thread, which
    is what ``Store``'s "one Store per thread" contract requires. An
    ``async def`` here would run on the event loop thread while
    ``get_store`` still ran in the thread pool, handing the connection to
    a caller on the wrong thread.
    """
    data = file.file.read()
    image = uploads.decode_image(data)
    extracted = extract_palette(image)

    uploads.save_upload(data, project_path / REFERENCES_DIR, project_path)

    existing = store.palette_for_project(project.id)
    next_number = _next_colour_number(existing)
    created = [
        store.add_palette_entry(
            PaletteEntry(
                project_id=project.id,
                rgb=colour.rgb,
                label=f"{AUTO_NAME_PREFIX}{next_number + offset}",
            )
        )
        for offset, colour in enumerate(extracted)
    ]
    return SwatchExtractResponse(entries=[_entry_response(e) for e in created])

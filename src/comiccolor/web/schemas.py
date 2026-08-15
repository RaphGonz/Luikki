"""The whole phase's HTTP request/response contract, declared once.

Every Pydantic model this phase's routers use lives here, before any router
body exists (01-PATTERNS.md § No Analog Found: "shape DTOs 1:1 against
entities.py but keep them separate classes; do not reuse the dataclasses as
Pydantic models"). Declaring the contract up front is what lets plans
01-07 through 01-10 build four different router modules in parallel without
three of them fighting over this file.

Two constrained field types are reused everywhere a colour or a name/label
crosses the browser boundary — ASVS L1 V5 input validation, cheaper here than
a hand-written check repeated in four routers:

- ``RGBTuple`` — three channels, each ``0..255``.
- ``NonEmptyStr`` — a non-empty string with a sane max length.

``PipelineStage`` is imported from :mod:`comiccolor.model` so stage values
validate against the real enum rather than being restated as a free-form
string union that could silently drift from ``model/entities.py``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from ..model import PipelineStage

# ---- Shared constrained field types ---------------------------------------

RGBChannel = Annotated[int, Field(ge=0, le=255)]
RGBTuple = tuple[RGBChannel, RGBChannel, RGBChannel]
NonEmptyStr = Annotated[str, Field(min_length=1, max_length=200)]

# A project name is the one client string this app turns into a *directory
# name*, so it gets its own type rather than reusing ``NonEmptyStr``.
# Constrained to a single safe path segment at the boundary: no separator
# of either flavour, none of Windows' reserved filename characters, no
# control characters, and no leading dot (which is what rules out ``.`` and
# ``..`` and keeps the folder visible on POSIX). ``appconfig.
# create_project_folder`` re-asserts containment independently — this
# pattern is the outer layer, not the only one.
ProjectName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=100,
        pattern="^[^\\\\/:*?\"<>|\\x00-\\x1f.][^\\\\/:*?\"<>|\\x00-\\x1f]*$",
    ),
]


# ---- Projects ---------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: ProjectName
    # Deliberately unconstrained: D-04's folder-pick model lets the artist
    # put a project anywhere on their own machine (the native browse dialog
    # returns arbitrary absolute paths), so there is no workspace to
    # contain this to. It names a *parent*; ``name`` is what must never
    # escape it.
    parent_dir: str | None = None


class ProjectOpenRequest(BaseModel):
    path: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    path: str
    palette_revision: int


class RecentProjectResponse(BaseModel):
    name: str
    path: str
    opened_at: str


class BrowseResponse(BaseModel):
    path: str


# ---- Volumes ------------------------------------------------------------


class VolumeCreateRequest(BaseModel):
    name: NonEmptyStr


class VolumeRenameRequest(BaseModel):
    name: NonEmptyStr


class VolumeResponse(BaseModel):
    id: int
    project_id: int
    name: str
    page_count: int


# ---- Pages ------------------------------------------------------------------


class PageResponse(BaseModel):
    id: int
    volume_id: int
    index: int
    original_name: str
    width: int
    height: int
    stage: PipelineStage
    # Server-built ``/api/pages/{id}/image`` path. The frontend must never
    # construct a filesystem path, and the on-disk name must never reach the
    # client (T-01-PATH, uploads.py's display_name/save_upload split).
    image_url: str


class RejectedUpload(BaseModel):
    filename: str
    detail: str


class PageUploadResponse(BaseModel):
    accepted: list[PageResponse]
    rejected: list[RejectedUpload]


# ---- Pipeline -----------------------------------------------------------


class StageResponse(BaseModel):
    name: PipelineStage
    display_name: str
    upstream: PipelineStage | None
    produces: str
    # 01-UI-SPEC.md §1 needs two facts per stage-strip segment: position
    # (index in the chain, derived by the caller from list order) and
    # capability (whether this phase implements the stage at all). The API
    # reports the distinction; the UI is forbidden from rendering it — both
    # not-yet-reached variants must look identical in Phase 1.
    has_runner: bool


# ---- Palette ------------------------------------------------------------


class PaletteEntryCreateRequest(BaseModel):
    rgb: RGBTuple
    label: NonEmptyStr


class PaletteEntryUpdateRequest(BaseModel):
    label: NonEmptyStr | None = None
    rgb: RGBTuple | None = None


class PaletteEntryResponse(BaseModel):
    id: int
    rgb: RGBTuple
    label: str
    entity_id: int | None
    revision: int


class PaletteUpdateResponse(BaseModel):
    entry: PaletteEntryResponse
    # Feeds 01-UI-SPEC.md §6's "Updated on {N} page{s}" toast — this is why
    # plan 01-03 added Store.pages_affected_by alongside panels_affected_by.
    pages_affected: int


class SwatchExtractResponse(BaseModel):
    entries: list[PaletteEntryResponse]


# ---- Character sheet proposals -------------------------------------------


class ProposalResponse(BaseModel):
    # Proposals carry an index rather than a database id because nothing is
    # persisted until accept — D-05 and RESEARCH.md § Anti-Patterns both
    # forbid writing proposal colours to the database before the artist
    # confirms them.
    index: int
    rgb: RGBTuple
    pixel_share: float


class SheetProposalResponse(BaseModel):
    sheet_id: str
    image_url: str
    proposals: list[ProposalResponse]


class SheetAcceptItem(BaseModel):
    index: int
    part: NonEmptyStr


class SheetAcceptRequest(BaseModel):
    character_name: NonEmptyStr
    items: list[SheetAcceptItem]


class SheetAcceptResponse(BaseModel):
    entity_id: int
    entries: list[PaletteEntryResponse]

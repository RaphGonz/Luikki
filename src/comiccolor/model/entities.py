"""§3 data model.

Everything downstream assumes these shapes. Retrofitting is a rewrite.

Three invariants are enforced structurally rather than by convention:

1. A Region stores ``palette_entry_id`` and has no RGB field at all. There is
   nowhere to bake a colour even by accident. Resolving a region to pixels is
   always a join through PaletteEntry, which is what makes "change the hair
   colour everywhere" a single-row update.

2. Regions within a panel are mutually exclusive and exhaustive. Rather than
   storing one mask per region and checking that property, a panel owns a
   single integer *label map* and a Region is a label value within it. Overlap
   is unrepresentable; exhaustiveness is a coverage check over one array. See
   masks.py.

3. Colour lives at project scope. PaletteEntry and Entity reference
   ``project_id``, never ``volume_id``, even though an artist works inside a
   specific volume's pages. There is no path for a palette entry to be scoped
   to one volume even by accident — that is what makes the palette accumulate
   across the whole project (D-02, §1.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RegionStatus(str, Enum):
    """Provenance of a region's palette assignment, per §3."""

    AUTO = "auto"  # assigned by snapping, unreviewed
    CONFIRMED = "confirmed"  # artist looked at it and accepted
    FLAGGED = "flagged"  # snap distance over threshold, or high seed variance
    MANUAL = "manual"  # artist assigned it directly


class ProtectedKind(str, Enum):
    """§1.2. Excluded from every generative and fill stage, passed through."""

    BUBBLE = "bubble"
    SFX = "sfx"
    BORDER = "border"
    TEXT = "text"




@dataclass
class Project:
    name: str
    id: int | None = None
    # Bumped on every palette mutation. Lets the incremental propagation in
    # Tier 2 (§6) find stale panels without re-running the whole project.
    # Lives here, not on Volume, because the palette accumulates at project
    # scope (D-02) — every volume in the project shares one palette.
    palette_revision: int = 0


@dataclass
class Volume:
    project_id: int
    name: str
    id: int | None = None


@dataclass
class Page:
    volume_id: int
    # Path to the ink layer. Real ink, not extracted — see §7 training data note.
    source_path: str
    index: int
    id: int | None = None
    width: int = 0
    height: int = 0
    # The artist's own filename, display-only. The on-disk source_path is
    # always server-generated (RESEARCH.md Pitfall 3); the two must never be
    # the same string.
    original_name: str = ""


@dataclass
class Panel:
    page_id: int
    # Panel bounds in page pixel coordinates.
    x: int
    y: int
    width: int
    height: int
    # Position in reading order within the page, 0-based.
    reading_order: int
    id: int | None = None
    # Relative path to the label map backing this panel's regions (masks.py).
    # None until segmentation has run.
    label_map_path: str | None = None
    polygon: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Entity:
    """Character, prop, or recurring background. §3."""

    project_id: int
    name: str
    id: int | None = None
    reference_images: list[str] = field(default_factory=list)


@dataclass
class PaletteEntry:
    """Project-scoped, versioned, editable. §1.5.

    ``rgb`` is the single place a colour value lives in the whole system.
    """

    project_id: int
    rgb: tuple[int, int, int]
    label: str  # "Kaito / hair / base"
    id: int | None = None
    entity_id: int | None = None
    # Incremented on every rgb edit. A renderer caches against this.
    revision: int = 0


@dataclass
class Region:
    """An exact mask from trapped-ball, carrying a palette *reference*.

    Deliberately has no rgb field. See module docstring.
    """

    panel_id: int
    # Value identifying this region inside the panel's label map. Non-zero.
    label: int
    id: int | None = None
    palette_entry_id: int | None = None
    # Variance of the extracted mode across seeds (§1.8). None until proposed.
    confidence: float | None = None
    status: RegionStatus = RegionStatus.AUTO
    # Cached from the label map so triage and health metrics do not need to
    # touch pixels. Authority remains the label map.
    area: int = 0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)


@dataclass
class ProtectedMask:
    """§1.2. Frame as protection, not detection.

    Page-scoped, not panel-scoped (D-20): a bubble straddling two panels is
    one row, and each stage clips this page-space ``polygon`` down to a
    panel's local frame at use via ``rasterize_protected_for_panel``, rather
    than the mask itself being split or duplicated per panel.

    Protection means "never coloured", not "content preserved" (D-21) —
    there is no integrity invariant here on the model of ``assert_invariant``
    in masks.py; a protected pixel simply never receives a palette entry.

    ``touched`` is False for a detector-proposed mask (rendered with a dashed
    outline per UI-SPEC §3) and flips to True the instant the artist reshapes
    it or draws a new one by hand (solid outline); a hand-drawn mask starts
    True.
    """

    page_id: int
    kind: ProtectedKind
    polygon: list[tuple[int, int]] = field(default_factory=list)
    id: int | None = None
    touched: bool = False
    area: int = 0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)

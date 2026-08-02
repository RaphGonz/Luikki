"""§3 data model.

Everything downstream assumes these shapes. Retrofitting is a rewrite.

Two invariants are enforced structurally rather than by convention:

1. A Region stores ``palette_entry_id`` and has no RGB field at all. There is
   nowhere to bake a colour even by accident. Resolving a region to pixels is
   always a join through PaletteEntry, which is what makes "change the hair
   colour everywhere" a single-row update.

2. Regions within a panel are mutually exclusive and exhaustive. Rather than
   storing one mask per region and checking that property, a panel owns a
   single integer *label map* and a Region is a label value within it. Overlap
   is unrepresentable; exhaustiveness is a coverage check over one array. See
   masks.py.
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
class Series:
    name: str
    id: int | None = None


@dataclass
class Volume:
    series_id: int
    name: str
    id: int | None = None
    # Bumped on every palette mutation. Lets the incremental propagation in
    # Tier 2 (§6) find stale panels without re-running the volume.
    palette_revision: int = 0


@dataclass
class Page:
    volume_id: int
    # Path to the ink layer. Real ink, not extracted — see §7 training data note.
    source_path: str
    index: int
    id: int | None = None
    width: int = 0
    height: int = 0


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

    volume_id: int
    name: str
    id: int | None = None
    reference_images: list[str] = field(default_factory=list)


@dataclass
class PaletteEntry:
    """Volume-scoped, versioned, editable. §1.5.

    ``rgb`` is the single place a colour value lives in the whole system.
    """

    volume_id: int
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
    """§1.2. Frame as protection, not detection."""

    panel_id: int
    kind: ProtectedKind
    # Relative path to a binary mask PNG.
    mask_path: str
    id: int | None = None
    area: int = 0
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)

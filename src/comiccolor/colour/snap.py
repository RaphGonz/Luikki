"""§1.7 Mode extraction and CIELAB snapping.

Turns a proposal raster — Cobra's output, or any other proposer's — into
`palette_entry_id` per zone. Nothing here ever returns an RGB value to a
caller that stores it: the output is ids, per §3 invariant 1.

Two decisions the spec is explicit about, restated because both look like
arbitrary tuning and neither is:

**Mode, not average.** A zone is rarely one clean colour in a proposal
raster: it has an anti-aliased rim, a gradient, maybe a stray highlight. An
average is pulled by all of it and lands on a colour that appears nowhere in
the zone — skin next to a dark outline averages muddy. The mode is the colour
the zone actually mostly *is*, and outliers cannot drag it. Coarse bins first
so anti-aliasing does not split one colour across a thousand distinct values,
then average *within* the winning bin for sub-bin precision.

**`L*` downweighted.** CIELAB's three axes are `L*` (lightness), `a*`
(green↔red) and `b*` (blue↔yellow). Weighted equally, the same skin in shadow
and in light reads as two colours because only `L*` moved, and they snap to
two palette entries where the colourist wanted one flat. Weighting `L*` below
`a*`/`b*` puts the match on hue and saturation and forgives brightness.
Shading is a later layer's job, never the flat's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.color import rgb2lab

from ..model.entities import PaletteEntry, RegionStatus
from ..model.masks import UNASSIGNED

# Width of a mode bin per channel. 16 gives 16 levels per channel, 4096 bins
# total: coarse enough that an anti-aliased rim falls in the same bin as the
# body it belongs to, fine enough that two genuinely different flats do not.
# Unvalidated starting value, same caveat as every constant in extract.py.
MODE_BIN = 16

# Weight on the L* difference relative to a*/b*. §1.7 suggests ~0.3.
# Unvalidated starting value.
L_WEIGHT = 0.3

# Weighted-CIELAB distance above which a mode is *not* snapped and becomes a
# new flagged entry instead. §1.7: reject before snapping — silently coercing
# a new outfit into an existing entry is worse than an extra entry the artist
# can merge, because they will not notice it. Unvalidated starting value.
SNAP_MAX_DELTA = 12.0


@dataclass(frozen=True)
class ZoneAssignment:
    """One zone's resolved colour, as a reference. No rgb field, deliberately."""

    label: int
    palette_entry_id: int
    # True when nothing in the palette was within SNAP_MAX_DELTA and a new
    # entry was created. Maps to RegionStatus.FLAGGED.
    flagged: bool

    @property
    def status(self) -> RegionStatus:
        return RegionStatus.FLAGGED if self.flagged else RegionStatus.AUTO


def zone_modes(
    proposal: np.ndarray, label_map: np.ndarray, bin_size: int = MODE_BIN
) -> dict[int, tuple[int, int, int]]:
    """Modal colour per zone: largest coarse bin, averaged within that bin.

    `proposal` is HxWx3 uint8 RGB, `label_map` is HxW int with UNASSIGNED for
    line and protected pixels. Returns `{label: (r, g, b)}`, skipping labels
    with no pixels.
    """
    if proposal.shape[:2] != label_map.shape:
        raise ValueError(
            f"proposal {proposal.shape[:2]} does not match label map {label_map.shape}"
        )

    labels = label_map.ravel().astype(np.int64)
    max_label = int(labels.max()) if labels.size else 0
    if max_label < 1:
        return {}

    rgb = proposal.reshape(-1, 3).astype(np.int64)
    levels = 256 // bin_size
    codes = (rgb[:, 0] // bin_size) * levels * levels
    codes += (rgb[:, 1] // bin_size) * levels
    codes += rgb[:, 2] // bin_size

    inside = labels != UNASSIGNED
    n_bins = levels ** 3

    # One bincount over (label, bin) pairs beats a Python loop per zone: a
    # panel can carry several hundred zones and this runs on every generate.
    keyed = np.bincount(
        labels[inside] * n_bins + codes[inside], minlength=(max_label + 1) * n_bins
    )
    best_code = keyed.reshape(max_label + 1, n_bins).argmax(axis=1)

    # Sub-bin precision: average the actual pixels that fell in the winning bin.
    winning = inside & (codes == best_code[labels])
    counts = np.bincount(labels[winning], minlength=max_label + 1)
    means = np.stack(
        [
            np.bincount(labels[winning], weights=rgb[winning, c], minlength=max_label + 1)
            for c in range(3)
        ],
        axis=1,
    )

    out: dict[int, tuple[int, int, int]] = {}
    for label in range(1, max_label + 1):
        if counts[label] == 0:
            continue
        r, g, b = np.rint(means[label] / counts[label]).astype(int)
        out[label] = (int(r), int(g), int(b))
    return out


def _to_lab(colours: np.ndarray) -> np.ndarray:
    """Nx3 uint8 RGB → Nx3 CIELAB."""
    return rgb2lab(colours.reshape(-1, 1, 3).astype(np.float64) / 255.0).reshape(-1, 3)


def weighted_delta(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    """Euclidean CIELAB distance with `L*` scaled by L_WEIGHT.

    Broadcasts, so `lab_a` may be (N,3) and `lab_b` (M,3) → (N,M) when the
    caller adds the axis.
    """
    scale = np.array([L_WEIGHT, 1.0, 1.0])
    return np.sqrt((((lab_a - lab_b) * scale) ** 2).sum(axis=-1))


def nearest_entry(
    rgb: tuple[int, int, int], palette: list[PaletteEntry]
) -> tuple[PaletteEntry | None, float]:
    """Closest palette entry to `rgb` and its weighted CIELAB distance."""
    if not palette:
        return None, float("inf")

    query = _to_lab(np.array([rgb], dtype=np.uint8))[0]
    known = _to_lab(np.array([entry.rgb for entry in palette], dtype=np.uint8))
    distances = weighted_delta(query, known)
    index = int(np.argmin(distances))
    return palette[index], float(distances[index])


def assign_zones(
    proposal: np.ndarray,
    label_map: np.ndarray,
    palette: list[PaletteEntry],
    *,
    threshold: float | None = SNAP_MAX_DELTA,
    next_id: int = 1,
    label_prefix: str = "auto",
) -> tuple[list[ZoneAssignment], list[PaletteEntry]]:
    """Resolve every zone in `label_map` to a palette entry id.

    `palette` is read, never mutated; new entries are returned separately so
    the caller decides whether to keep them. `next_id` is the first id handed
    to a new entry — the caller owns id allocation.

    `threshold=None` means *never* snap: every zone's mode becomes its own
    entry. That is the palette-less path — with no swatch uploaded there is
    nothing to snap to, and inventing a shared palette by merging modes would
    fuse zones the artist expects to be separately selectable.
    """
    modes = zone_modes(proposal, label_map)
    working = list(palette)
    created: list[PaletteEntry] = []
    assignments: list[ZoneAssignment] = []

    for label in sorted(modes):
        rgb = modes[label]
        entry, distance = (None, float("inf"))
        if threshold is not None:
            entry, distance = nearest_entry(rgb, working)

        if entry is not None and distance <= threshold:
            assignments.append(ZoneAssignment(label, int(entry.id or 0), flagged=False))
            continue

        # §1.7 reject-before-snapping. A new entry the artist can merge beats
        # a wrong snap they will never spot.
        new_entry = PaletteEntry(
            project_id=0,
            rgb=rgb,
            label=f"{label_prefix} {next_id}",
            id=next_id,
        )
        next_id += 1
        created.append(new_entry)
        working.append(new_entry)
        assignments.append(
            ZoneAssignment(label, int(new_entry.id or 0), flagged=threshold is not None)
        )

    return assignments, created

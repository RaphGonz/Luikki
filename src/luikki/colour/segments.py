"""§1.7's missing seam: one zone, as something the artist can point at.

`Generate flats` used to resolve a zone's modal colour *and* snap it to the
palette in the same pass, so snapping had no stage boundary — the artist never
saw it happen and could not disagree with it. That is the one step of the
pipeline that was invisible, and it is the step that silently coerced every
neutral zone into a character sheet's ink black (see `snap.weighted_delta`).

A `Segment` is what makes the boundary real: a zone with enough page-space
geometry to be drawn, hit-tested and clicked, plus the palette entry it
currently resolves to. It deliberately carries **no rgb** — the colour lives in
the palette entry, which is what makes re-snapping a single-row change and what
"regions store `palette_entry_id`, never RGB" means in practice.

Segments are never merged or grouped by colour. Two segments that share a
proposal colour are still two segments: the segmentation is deterministic and
earned, the proposal is a guess that degrades with reference coverage, and
letting the guess collapse the segmentation would destroy exactly the zones the
artist needs in order to bucket the page one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..model.masks import UNASSIGNED


@dataclass
class Segment:
    """One zone of one panel, in page space so a click can find it."""

    # Which panel this belongs to (`PanelState.order`) and the zone's label
    # inside that panel's label map. The pair is the segment's identity.
    panel: int
    label: int
    # What the segment currently resolves to. Always set: before any snapping
    # each segment owns a private entry holding its own modal colour.
    palette_entry_id: int
    # Pixels in the zone. The artist's ordering signal — a 300px speck and a
    # 40000px background are not equally worth a click.
    area: int
    # Page-space (x0, y0, x1, y1), and a point guaranteed to lie *inside* the
    # zone rather than the bounds' centre, which for an L-shaped or ring-shaped
    # zone can fall outside it entirely.
    bounds: tuple[int, int, int, int]
    anchor: tuple[int, int]
    # True once the artist has resolved this segment against the reference
    # palette. False means "still showing what the proposer suggested".
    snapped: bool = False

    @property
    def key(self) -> tuple[int, int]:
        return self.panel, self.label


def build_segments(
    panel_order: int,
    label_map: np.ndarray,
    assignments: dict[int, int],
    origin: tuple[int, int],
) -> list[Segment]:
    """Every zone in one panel's label map, as `Segment`s in page space.

    `origin` is the panel's (x, y) on the page. Zones absent from
    `assignments` are skipped rather than guessed at — a zone with no entry
    has not been through `Generate flats` yet.
    """
    offset_x, offset_y = origin
    segments: list[Segment] = []

    labels, counts = np.unique(label_map, return_counts=True)
    for label, area in zip(labels.tolist(), counts.tolist()):
        if label == UNASSIGNED or label not in assignments:
            continue

        rows, cols = np.nonzero(label_map == label)
        # Pick the anchor off the zone's median row, so a crescent or a ring
        # still anchors on its own pixels. Taken from `rows` itself, which
        # `nonzero` returns sorted: `np.median` averages the two middle rows,
        # and for a zone in two pieces that average is a row it has no pixel on.
        median_row = int(rows[len(rows) // 2])
        row_cols = cols[rows == median_row]
        anchor = (int(np.median(row_cols)) + offset_x, median_row + offset_y)

        segments.append(
            Segment(
                panel=panel_order,
                label=int(label),
                palette_entry_id=int(assignments[label]),
                area=int(area),
                bounds=(
                    int(cols.min()) + offset_x,
                    int(rows.min()) + offset_y,
                    int(cols.max()) + offset_x,
                    int(rows.max()) + offset_y,
                ),
                anchor=anchor,
            )
        )
    return segments

"""§1.4 from the third end: the zones that are not zones.

`leaks.py` divides what the segmenter over-merged. This module does the
opposite and joins what it over-split — but only where the geometry says the
piece was never a thing the artist drew.

A trapped-ball fill leaves slivers. The ball is eroded, the residue is handed
back, and along a stroke that residue comes out as a crumb enclosed by one
region. Nothing about its shape is a decision: it is the width of the ball, not
the width of anything on the page.

The rule is geometric on purpose, and it is exactly two conditions:

- the region is small — **as a share of the panel**, never in pixels. A crumb
  on a full-page splash and a crumb on a nine-panel grid are the same crumb to
  the artist and a factor of nine apart in pixels, which is why
  `SegmentationParams.min_area` and `LeakParams.min_piece` are the wrong shape
  and LineFiller's own hardcoded 500 / 250 are worse.
- one neighbour holds nearly the whole of its border. A crumb is enclosed. A
  real small zone — an iris, a highlight, a button — is enclosed too, so this
  condition alone decides nothing and the area ceiling is what separates them.
  That ceiling is measured, not guessed: see `reports/microzones/`.

Colour is never a criterion here, and must not become one after generation: a
zone the model coloured like its neighbour is a zone the model got *right* or a
failure worth seeing, and absorbing it would bury the evidence either way.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from ..model.masks import UNASSIGNED
from .leaks import border_stats
from .trappedball import expand_under_lines, inked_zones


@dataclass
class AbsorbParams:
    """Style-sensitive, like every other threshold in §1.4."""

    # Largest region this pass will touch, as a share of the panel's area.
    # 5e-4 is ~240px on a 480k panel. Chosen on the renders in
    # `reports/microzones/`, by the artist, against the grid from 5e-05 up: the
    # things it takes — a highlight on a cap, the dots on a machine front — are
    # things a colourist wants gone, not detail worth a zone. Above it the
    # renders lose marks that were drawn to be seen. It absorbs 32 regions of
    # 470 on `teddy_page` and 56 of 756 on `laurine_page`.
    #
    # 0.0 turns the pass off. Nothing else about this number is derived: it is
    # a judgement about one artist's ink, and the next one may move it.
    max_area_share: float = 5e-4
    # Share of a region's border one neighbour must hold to swallow it. Below
    # it the region sits between two zones and picking either is a guess.
    min_dominance: float = 0.80


def absorb_micro_zones(
    labels: np.ndarray,
    line_mask: np.ndarray,
    ink: np.ndarray,
    panel_area: int,
    protected: np.ndarray | None = None,
    params: AbsorbParams | None = None,
) -> np.ndarray:
    """Give every crumb the label of the neighbour that encloses it.

    ``labels`` is the segmenter's output and ``line_mask`` the raster it was
    cut from — the structural lines, the same pair `split_open_borders` takes.
    ``ink`` is the artist's *real* ink, needed only to spot the regions that
    are their own spot black. ``panel_area`` is the denominator of the size
    condition.

    Returns a label map on the same support: a region either keeps its label or
    takes a neighbour's whole, and no pixel changes zone on its own.
    """
    params = params or AbsorbParams()
    size = int(labels.max()) + 1
    if size < 2:
        return labels

    # Borders are measured after expansion, where two regions separated by a
    # stroke meet along its centre instead of stopping at its two edges — the
    # same reason `split_open_borders` expands before measuring. The expansion
    # is for the measurement only; the relabel lands on the real shapes.
    expanded = expand_under_lines(labels, line_mask, protected=protected)
    stats = border_stats(expanded, ink)

    neighbours: dict[int, dict[int, int]] = defaultdict(dict)
    for (first, second), entry in stats.items():
        neighbours[first][second] = entry[0]
        neighbours[second][first] = entry[0]

    # Areas come off the unexpanded map: what the region actually is, not what
    # it grew into under the ink.
    areas = np.bincount(labels.ravel(), minlength=size)
    ceiling = params.max_area_share * panel_area

    # Never absorb into the artist's own spot black. That region is punched out
    # after expansion (§ `inked_zones`), so a highlight sitting inside a black
    # mass would not join it — it would vanish into the hole and come back
    # white, which is the failure this guard exists for.
    doomed = inked_zones(labels, ink)
    doomed = np.pad(doomed, (0, max(0, size - doomed.size)))

    parent = list(range(size))

    def find(region: int) -> int:
        while parent[region] != region:
            parent[region] = parent[parent[region]]
            region = parent[region]
        return region

    # Smallest first, so a crumb resting on another crumb resolves through the
    # chain rather than anchoring on it.
    candidates = [
        label
        for label in np.argsort(areas, kind="stable")
        if label != UNASSIGNED and 0 < areas[label] < ceiling
    ]

    for candidate in candidates:
        candidate = int(candidate)
        if find(candidate) != candidate or doomed[candidate]:
            continue
        border = neighbours.get(candidate)
        if not border:
            continue

        total = sum(border.values())
        dominant, held = max(border.items(), key=lambda pair: pair[1])
        if total == 0 or held / total < params.min_dominance:
            continue

        target = find(dominant)
        if target == candidate or doomed[dominant] or doomed[target]:
            continue
        parent[candidate] = target

    roots = np.array([find(region) for region in range(size)], dtype=labels.dtype)
    roots[UNASSIGNED] = UNASSIGNED
    return roots[labels]

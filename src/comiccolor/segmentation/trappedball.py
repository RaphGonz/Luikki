"""§1.4 Trapped-ball region segmentation. Deterministic, exact, inspectable.

The mechanism: erode the fillable area with a disc of radius r. A pixel
survives only if the whole disc fits, so the disc cannot pass through a gap
narrower than 2r. Each surviving connected component is a region *core*.
Dilating a core by the same disc returns it to its true extent, and because
every core pixel had the full disc inside the fillable area, the dilation can
never cross a line. Leaks through open lines are therefore impossible at radius
r — which is why this doubles as §1.3's gap closure and why the radius schedule
is the single most style-sensitive parameter in the pipeline.

Descending radii find large regions first under the strictest leak guarantee,
then progressively smaller ones. A final plain flood fill sweeps up what is
left.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..model.masks import UNASSIGNED, region_stats

DEFAULT_RADII = (5, 4, 3, 2, 1)


@dataclass
class SegmentationParams:
    """Style-sensitive knobs. Defaults tuned for clean manga ink."""

    # None derives the schedule from the artwork via adaptive_radii(), which is
    # the safe default: a fixed schedule that is too coarse for the art does
    # not degrade gracefully, it shatters thin regions.
    radii: tuple[int, ...] | None = None
    # Regions below this pixel area are merged into a neighbour. Suppresses the
    # micro-region explosion from anti-aliasing; does NOT solve hatching, which
    # needs the Tier 3 adapter.
    min_area: int = 24
    # How far to search for a neighbour when merging. Must exceed the ink line
    # width or a sliver will only ever see line pixels around it.
    merge_reach: int = 3
    # Cap on merge passes; each pass can create newly-mergeable regions.
    merge_passes: int = 3


def _ball(radius: int) -> np.ndarray:
    size = 2 * radius + 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def measure_passage_width(fillable: np.ndarray) -> float:
    """Typical width of the fillable corridors, in pixels.

    The distance transform gives every pixel its distance to the nearest line,
    so twice the median over fillable pixels is a robust estimate of how wide
    the artwork's passages actually are.
    """
    if not fillable.any():
        return 1.0
    distance = cv2.distanceTransform(fillable.astype(np.uint8), cv2.DIST_L2, 5)
    values = distance[distance > 0]
    if values.size == 0:
        return 1.0
    return float(2.0 * np.median(values))


def adaptive_radii(fillable: np.ndarray, ceiling: int = 5) -> tuple[int, ...]:
    """Radius schedule bounded by what the artwork can actually accommodate.

    A radius-r ball guards against leaks through gaps up to 2r wide. But if the
    art contains legitimate passages narrower than 2r, the ball cannot tell them
    from leaks: it finds cores only where such a passage happens to bulge, and
    every bulge becomes its own region, shattering one strip into dozens.

    So the largest usable radius is set by the artwork's narrowest legitimate
    passage, not by how much gap tolerance we would like. On densely hatched
    pages that bound is small, which is a real and unavoidable statement about
    the method: **gap closure and hatching are in direct tension**, and no
    radius satisfies both. Hatching has to be removed upstream (§7 Tier 3), not
    segmented around.
    """
    limit = max(1, min(ceiling, int(measure_passage_width(fillable) // 2)))
    return tuple(range(limit, 0, -1))


def trapped_ball_segment(
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
    params: SegmentationParams | None = None,
) -> np.ndarray:
    """Segment the fillable area into exact, non-overlapping regions.

    ``line_mask`` is boolean, True on ink. ``protected`` is boolean, True where
    a bubble/SFX mask forbids filling (§1.2). Returns an int32 label map where
    0 is unassigned (line or protected) and each other value is one region.
    """
    params = params or SegmentationParams()

    fillable = ~line_mask
    if protected is not None:
        fillable &= ~protected

    labels = np.zeros(line_mask.shape, dtype=np.int32)
    unfilled = fillable.copy()
    next_label = 1

    radii = params.radii if params.radii is not None else adaptive_radii(fillable)

    for radius in sorted(radii, reverse=True):
        if not unfilled.any():
            break
        next_label = _fill_at_radius(labels, unfilled, radius, next_label)

    # Erode-then-dilate is a morphological opening, and an opening does not
    # restore its input: it rounds off corners and pinch points. The residue
    # is not a new region, it is the part of an existing region the ball could
    # not reach. Give it back before counting anything, or every rectangular
    # region reports four spurious corner regions.
    _absorb_residue(labels, unfilled)

    # What is left now genuinely had no core at any radius: shapes thinner
    # than the smallest ball. Those are real, separate regions.
    next_label = _fill_remainder(labels, unfilled, next_label)

    if params.min_area > 1:
        labels = merge_small_regions(labels, params)

    return labels


def _fill_at_radius(
    labels: np.ndarray, unfilled: np.ndarray, radius: int, next_label: int
) -> int:
    ball = _ball(radius)
    eroded = cv2.erode(unfilled.astype(np.uint8), ball)
    if not eroded.any():
        return next_label

    count, cores = cv2.connectedComponents(eroded, connectivity=4)
    if count <= 1:
        return next_label

    stats = region_stats(cores.astype(np.int32))
    height, width = labels.shape

    for core_label, (_, (bx, by, bw, bh)) in stats.items():
        # Work in a padded crop: the dilation reaches at most `radius` beyond
        # the core's bounding box, so nothing outside the pad can be touched.
        x0 = max(0, bx - radius - 1)
        y0 = max(0, by - radius - 1)
        x1 = min(width, bx + bw + radius + 1)
        y1 = min(height, by + bh + radius + 1)

        core = (cores[y0:y1, x0:x1] == core_label).astype(np.uint8)
        grown = cv2.dilate(core, ball).astype(bool)

        # Two cores at the same radius can have overlapping dilations. First
        # one to claim a pixel keeps it; `unfilled` shrinks as we go.
        window = unfilled[y0:y1, x0:x1]
        grown &= window
        if not grown.any():
            continue

        labels[y0:y1, x0:x1][grown] = next_label
        window[grown] = False
        next_label += 1

    return next_label


def _absorb_residue(labels: np.ndarray, unfilled: np.ndarray) -> None:
    """Grow existing labels into leftover pixels, without crossing a line.

    Expansion is confined to ``unfilled``, which never contains line or
    protected pixels. So a label can only reach pixels connected to it *within*
    the fillable area — the corner of a box interior can be reclaimed by the
    interior and is unreachable from outside. That containment is what makes
    this safe to do before regions are counted.
    """
    kernel = np.ones((3, 3), np.uint8)
    # cv2.dilate has no int32 path; float32 is exact well past any plausible
    # region count.
    work = labels.astype(np.float32)

    while unfilled.any():
        grown = cv2.dilate(work, kernel)
        newly = unfilled & (grown > 0)
        if not newly.any():
            break
        work[newly] = grown[newly]
        unfilled[newly] = False

    labels[:] = work.astype(np.int32)


def _fill_remainder(labels: np.ndarray, unfilled: np.ndarray, next_label: int) -> int:
    if not unfilled.any():
        return next_label
    count, comps = cv2.connectedComponents(unfilled.astype(np.uint8), connectivity=4)
    for comp in range(1, count):
        mask = comps == comp
        labels[mask] = next_label
        next_label += 1
    unfilled[:] = False
    return next_label


def merge_small_regions(labels: np.ndarray, params: SegmentationParams) -> np.ndarray:
    """Absorb sub-threshold regions into their largest-contact neighbour.

    The search reaches across ink lines on purpose. A sliver sitting between
    two strokes has nothing but line pixels immediately around it, so a
    1-pixel neighbourhood would find no neighbour at all.
    """
    kernel = _ball(params.merge_reach)

    for _ in range(params.merge_passes):
        stats = region_stats(labels)
        small = sorted(
            (label for label, (area, _) in stats.items() if area < params.min_area),
            key=lambda label: stats[label][0],
        )
        if not small:
            break

        merged_any = False
        height, width = labels.shape

        for label in small:
            area, (bx, by, bw, bh) = stats[label]
            reach = params.merge_reach
            x0, y0 = max(0, bx - reach - 1), max(0, by - reach - 1)
            x1, y1 = min(width, bx + bw + reach + 1), min(height, by + bh + reach + 1)

            crop = labels[y0:y1, x0:x1]
            mask = crop == label
            if not mask.any():
                continue  # already absorbed this pass

            neighbourhood = cv2.dilate(mask.astype(np.uint8), kernel).astype(bool)
            candidates = crop[neighbourhood & ~mask]
            candidates = candidates[candidates != UNASSIGNED]
            if candidates.size == 0:
                continue

            counts = np.bincount(candidates)
            target = int(counts.argmax())
            if target == label:
                continue
            crop[mask] = target
            merged_any = True

        if not merged_any:
            break

    return labels


def expand_under_lines(
    labels: np.ndarray,
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
) -> np.ndarray:
    """Grow each region under the ink so flats composite without fringing.

    §10: anti-aliased line art needs the flat colour to continue *beneath* the
    line, otherwise the AA edge blends toward paper white and haloes. Every
    line pixel takes the label of its nearest region.

    Protected pixels are left at 0 — bubbles must stay unpainted. A protected
    polygon can overlap an ink pixel (e.g. a bubble drawn across a panel
    frame border), and a pixel that is both "line" and "protected" must stay
    protected: expansion is a line-art fix, and PROT-04 (D-21) always wins
    that conflict. Without ``protected`` this can only key off ``line_mask``,
    which is correct whenever protection and ink never overlap — pass
    ``protected`` explicitly whenever that is not guaranteed.
    """
    from scipy import ndimage

    filled = labels != UNASSIGNED
    if not filled.any():
        return labels

    # Nearest filled pixel for every pixel, then read its label through.
    _, indices = ndimage.distance_transform_edt(~filled, return_indices=True)
    expanded = labels[tuple(indices)]

    out = labels.copy()
    target = line_mask & (labels == UNASSIGNED)
    if protected is not None:
        target &= ~protected
    out[target] = expanded[target]
    return out

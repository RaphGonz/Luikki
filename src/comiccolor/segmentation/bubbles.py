"""§1.2 Frame as protection, not detection. Speech-bubble proposal.

D-22 (user's own design, adopted over every OSS detector surveyed): a bubble
is text surrounded by white.

1. Detect glyphs on the page.
2. Flood-fill the enclosing white outward from the text as seed.
3. Cap by maximum area, so an *unclosed* bubble cannot leak into the whole
   page or run out along the gutters between panels.
4. Discard when the text sits on a large white fill or on a coloured area --
   that is lettering on artwork, not a bubble.

D-23: this needs text *detection*, not OCR. The characters are never read,
only located, so there is no OCR engine, no language pack and no licence
question -- just `cv2.connectedComponentsWithStats` filtered by height
similarity and aspect ratio, the signature of glyphs sitting on a shared
baseline. Hatching has irregular heights and no shared baseline, which is
why it does not survive to become a bubble seed.

D-24: SFX lettering gets no automatic proposal this phase. A glyph cluster
with no enclosing white to fill produces nothing here by construction --
`PROT-02`'s hand-drawing covers SFX completely, so this is not a missing
feature, it is the designed shape of the algorithm.

D-25: learned bubble detectors were surveyed and rejected on licence, not
quality (GPL-3.0 derivatives, Manga109 research-only encumbrance, conflicts
with Cobra's OpenRAIL++-M). If one is ever added it belongs behind an
optional seam distributing no restricted weights, on the model of Cobra
itself ("build the seam, spike inside") -- not bundled here.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class BubbleParams:
    # Band around the page's median small-component height a glyph must
    # fall in -- D-23's "similar height" filter.
    min_glyph_height_frac: float = 0.4
    max_glyph_height_frac: float = 2.5
    # Rejects long straight runs (panel frames, speed lines) that happen to
    # be short in one dimension -- neither a glyph's width nor its height
    # may exceed this multiple of the other.
    max_glyph_aspect: float = 4.0
    # A lone blob is dirt, not lettering; this is the "bounding-box
    # clustering to drop lonely boxes" step the Rabbit1010 precedent names.
    min_glyphs_per_cluster: int = 3
    # Merges the lines of one text block so a bubble is filled once from its
    # whole text block rather than once per character.
    cluster_dilate_px: int = 15
    # D-22 point 3's cap. [ASSUMED] per 02-RESEARCH.md A3 and needs tuning
    # against real project pages: too low silently discards large legitimate
    # bubbles, too high lets an unclosed bubble leak along a gutter.
    max_area_frac: float = 0.35
    # A fill smaller than this is a hole in the ink, not a bubble.
    min_area_frac: float = 0.001
    # Below this mean brightness (0-255) the filled ground is artwork or a
    # coloured area, not paper -- D-22 point 4's "lettering on artwork"
    # discard. Half of the 8-bit range is the natural midpoint, not tuned
    # against real pages.
    min_ground_brightness: float = 127.0
    # A hard ceiling on returned masks, so a pathological page cannot
    # produce an unbounded list (T-2-05).
    max_bubbles: int = 64
    # `approxPolyDP` tolerance as a fraction of contour perimeter, never a
    # fixed pixel constant (02-RESEARCH.md Pitfall 1). [ASSUMED] per A2,
    # needs tuning against real detected bubbles.
    epsilon_frac: float = 0.01


def _glyph_candidates(line_mask: np.ndarray, params: BubbleParams) -> np.ndarray:
    """Small dark blobs of similar height and modest aspect ratio.

    D-23's claim: these two filters together reject hatching, because
    hatching has irregular heights and no shared baseline, while a line of
    lettering has near-uniform glyph heights sitting on one baseline. Text
    *detection*, not OCR -- the components are never read, only located.
    """
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        line_mask.astype(np.uint8), connectivity=8
    )
    glyph_mask = np.zeros_like(line_mask, dtype=bool)
    if count <= 1:
        return glyph_mask

    heights = stats[1:, cv2.CC_STAT_HEIGHT]
    median_height = float(np.median(heights))
    low = params.min_glyph_height_frac * median_height
    high = params.max_glyph_height_frac * median_height

    for index in range(1, count):
        height = stats[index, cv2.CC_STAT_HEIGHT]
        width = stats[index, cv2.CC_STAT_WIDTH]
        if not (low <= height <= high):
            continue
        if width == 0 or height == 0:
            continue
        if width / height > params.max_glyph_aspect:
            continue
        if height / width > params.max_glyph_aspect:
            continue
        glyph_mask |= labels == index

    return glyph_mask


def _glyph_clusters(glyphs: np.ndarray, params: BubbleParams) -> list[np.ndarray]:
    """One seed mask per text block, dropping lonely glyphs.

    Glyphs are dilated by `cluster_dilate_px` and grouped by connectivity so
    the lines of one text block merge into one cluster; a cluster surviving
    with fewer than `min_glyphs_per_cluster` *original* glyph components is
    dirt, not lettering, and is dropped.
    """
    if not glyphs.any():
        return []

    _, glyph_labels = cv2.connectedComponents(glyphs.astype(np.uint8), connectivity=8)

    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (params.cluster_dilate_px, params.cluster_dilate_px)
    )
    dilated = cv2.dilate(glyphs.astype(np.uint8), kernel)
    cluster_count, cluster_labels = cv2.connectedComponents(dilated, connectivity=8)

    clusters: list[np.ndarray] = []
    for cluster_id in range(1, cluster_count):
        seed_mask = (cluster_labels == cluster_id) & glyphs
        glyph_ids = set(int(v) for v in np.unique(glyph_labels[seed_mask]) if v != 0)
        if len(glyph_ids) < params.min_glyphs_per_cluster:
            continue
        clusters.append(seed_mask)

    return clusters


def detect_bubbles(
    grey: np.ndarray, line_mask: np.ndarray, params: BubbleParams | None = None
) -> list[np.ndarray]:
    """Text-seeded flood fill: D-22's algorithm end to end.

    Returns one boolean mask per detected bubble, in page space, same shape
    as `line_mask`. A glyph cluster's fill is discarded when it is unclosed
    (area above `max_area_frac`, D-22 point 3), too small to be a bubble
    (below `min_area_frac`), or sitting on dark/textured ground rather than
    paper (below `min_ground_brightness`, D-22 point 4). Two clusters inside
    one bubble never yield two masks -- a cluster whose seed already lies
    inside an accepted fill is skipped.
    """
    params = params or BubbleParams()
    height, width = line_mask.shape
    max_area = params.max_area_frac * height * width
    min_area = params.min_area_frac * height * width

    glyphs = _glyph_candidates(line_mask, params)
    clusters = _glyph_clusters(glyphs, params)

    non_ink = ~line_mask
    neighbourhood = np.ones((3, 3), dtype=np.uint8)
    fill_target = non_ink.astype(np.uint8) * 255

    bubbles: list[np.ndarray] = []
    filled_so_far = np.zeros_like(line_mask, dtype=bool)

    for seed_mask in clusters:
        if len(bubbles) >= params.max_bubbles:
            break

        # A seed point on the paper immediately adjacent to the cluster --
        # not a glyph pixel itself, which is ink by construction and floods
        # nothing.
        border = cv2.dilate(seed_mask.astype(np.uint8), neighbourhood).astype(bool)
        border &= non_ink & ~seed_mask
        ys, xs = np.nonzero(border)
        if ys.size == 0:
            continue
        seed_point = (int(xs[0]), int(ys[0]))
        if filled_so_far[seed_point[1], seed_point[0]]:
            continue  # already covered by an accepted bubble

        flood_mask = np.zeros((height + 2, width + 2), dtype=np.uint8)
        cv2.floodFill(
            fill_target.copy(),
            flood_mask,
            seed_point,
            255,
            loDiff=0,
            upDiff=0,
            flags=4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8),
        )
        filled = flood_mask[1:-1, 1:-1].astype(bool)
        area = int(filled.sum())
        if area < min_area or area > max_area:
            continue  # too small to be a bubble, or an unclosed leak

        mean_brightness = float(grey[filled].mean())
        if mean_brightness < params.min_ground_brightness:
            continue  # lettering on artwork, not a bubble (D-22 point 4)

        bubbles.append(filled)
        filled_so_far |= filled

    return bubbles


def mask_to_polygon(mask: np.ndarray, epsilon_frac: float = 0.01) -> list[tuple[int, int]]:
    """Trace a detected bubble's outer contour into an editable vertex list.

    `epsilon_frac` is perimeter-relative (Pitfall 1), never a fixed pixel
    tolerance. Returns `[]` when there is no contour, or when the simplified
    contour has fewer than 3 points, so a degenerate trace never reaches the
    store as an unrenderable polygon.
    """
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []

    largest = max(contours, key=cv2.contourArea)
    epsilon = epsilon_frac * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    if len(approx) < 3:
        return []

    return [(int(point[0][0]), int(point[0][1])) for point in approx]

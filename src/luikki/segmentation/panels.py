"""§1.1 Panel segmentation. Geometric, deterministic, no learning.

The method: **the gutter is what a large ball can reach from the page margin.**

Erode the paper-white area with a disc sized to the gutter. A disc that big
cannot fit inside artwork, so what survives is the gutter network plus the
page margin — and the gutter network is connected to the margin. Flood from
the border through the surviving area, dilate back, and the complement is the
panels.

This is the same trapped-ball trick used in §1.4, applied one level up, and it
is chosen over the obvious alternatives because of how real pages fail:

- *Projection profiles (XY-cut)* cannot distinguish a gutter from the sparse
  interior of a panel — line art is mostly white everywhere — and a single SFX
  crossing a gutter blocks the cut for the whole page.
- *Hole filling* requires panel frames to be closed contours. They routinely
  are not: hair, SFX and figures break frames, and frames run off the page.

Working in 2D fixes both. An SFX sitting in a gutter is something the ball
routes around, because blocking one point does not disconnect a network. A
frame broken by a few pixels of hair is a hole too small for the ball to pass
through, so the panel stays sealed — a gap has to be gutter-width before it
merges two panels.

Remaining limits, stated rather than hidden: panels that share a border with
no gutter between them merge into one; a page with no gutters at all (full
bleed) returns a single whole-page panel. Both are honest failures rather than
cuts through artwork.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

ReadingDirection = Literal["rtl", "ltr"]


@dataclass
class PanelParams:
    # Narrowest gutter to recognise, as a fraction of the page's shorter side.
    # This is the single load-bearing parameter: it is simultaneously the
    # smallest gutter that separates panels and the largest frame break that
    # will not leak between them.
    #
    # 0.009 is measured, not chosen. Swept against the artist's own counts in
    # `test_pages/panel_counts.txt`, the behaviour has a cliff between 0.009
    # and 0.010: `tintin_page.jpg` returns 12 boxes at or below 0.009 and 5 at
    # or above 0.010, because above it the disc no longer fits in the gutters
    # *between* panels of one row and whole rows survive as single blobs. The
    # old 0.012 was on the wrong side of that cliff.
    #
    # Two things this does not fix, recorded so the next person does not
    # re-derive them by tuning. On tintin the left column of rows 1-2 still
    # merges into one box, and a merge is the expensive failure: an artist can
    # drag a wrong panel's corners but cannot split one box into two, and
    # there is no add-panel button. Separately, the page title and a balloon
    # poking into the margin come back as panels; per D-19 that is the cheap
    # failure and is left alone rather than filtered, because every filter
    # that removes them also removes a genuinely thin panel.
    min_gutter_frac: float = 0.009
    # Panels below this share of page area are debris, not panels.
    min_area_frac: float = 0.005
    # Reject blobs less solid than this (area over bounding-box area). Filters
    # L-shaped merges and stray line networks that survived the fill.
    #
    # D-18: this is a FLOOR, so it silently DISCARDS components, not
    # mis-boxes them. On a borderless panel the surviving component is the
    # ink silhouette of the drawing itself (no frame to seal `_gutter_network`
    # against), and an irregular silhouette's area/bbox ratio sits well under
    # the old 0.55. Explicit user instruction: over-propose and let the
    # artist delete a false positive (D-19) rather than under-propose and
    # make them draw a whole panel from scratch. Do not raise this back —
    # a value near 0.55 again silently drops every ink-silhouette borderless
    # panel and looks, to the next contributor, like nothing changed.
    min_solidity: float = 0.25
    # `approxPolyDP` tolerance for a traced panel outline, as a fraction of
    # contour perimeter. Fine on purpose: at 0.02 every shape on every test
    # page collapsed to 4-5 vertices, which flattens away the notch a diamond
    # bites out of its neighbour -- the whole reason for tracing.
    polygon_epsilon_frac: float = 0.005
    # Above this many vertices the blob is artwork, not a panel, and its
    # bounding box is used instead. See `_panel_polygon` for the measurement.
    max_polygon_vertices: int = 12
    # Shortest run counted as a panel frame, as a fraction of the shorter side.
    frame_length_frac: float = 0.05
    # Longest break in a frame to repair, as a fraction of the shorter side.
    # Sized to swallow hair, SFX and figures crossing a border.
    frame_gap_frac: float = 0.10
    # 02-UI-SPEC.md §7: the project's motivating examples are Franco-Belgian,
    # so left-to-right is the default. Reading order is a backend parameter
    # for this phase, not a per-project setting, and the toolbar shows a
    # non-interactive "Reading order: Left -> Right" readout so the
    # convention is never silently assumed. "rtl" (manga) stays reachable by
    # passing it explicitly.
    reading: ReadingDirection = "ltr"


@dataclass
class PanelBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class Panel:
    """A panel as its outline, with the bounding box that contains it.

    The polygon is the panel; the box is where to crop. Both are kept because
    they answer different questions and a diamond makes the difference
    obvious: its box overlaps four neighbours, and only the polygon says which
    pixels are actually its own. Everything downstream already knew this --
    `_blocked_for` has always rasterised the polygon and returned everything
    outside it unlabelled.
    """

    polygon: list[tuple[int, int]]
    box: PanelBox

    @property
    def x(self) -> int:
        return self.box.x

    @property
    def y(self) -> int:
        return self.box.y

    @property
    def width(self) -> int:
        return self.box.width

    @property
    def height(self) -> int:
        return self.box.height

    @property
    def area(self) -> int:
        return self.box.area


def box_to_polygon(box: PanelBox) -> list[tuple[int, int]]:
    """Seed a panel's four-vertex polygon from its bounding box (D-17).

    Returns the corners top-left, top-right, bottom-right, bottom-left —
    clockwise starting at the top-left — in page-pixel space. This is the
    only way a panel becomes a polygon: `findContours` must never be called
    here. `_gutter_network` cannot be blocked by a frame on a borderless
    panel, so the surviving component is the ink silhouette of the drawing,
    not a frame; tracing it with `findContours` + `approxPolyDP` yields a
    polygon shaped like the character rather than the panel. The box is the
    correct starting shape; `Panel.polygon` (entities.py) is where an artist
    then reshapes it via vertex editing (D-19).
    """
    x0, y0 = box.x, box.y
    x1, y1 = box.x + box.width, box.y + box.height
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _panel_polygon(
    blob: np.ndarray, box: PanelBox, params: PanelParams
) -> list[tuple[int, int]]:
    """Trace one blob's outline, or fall back to its box.

    D-17 forbade `findContours` here outright, and the reason was sound: with
    no frame to seal `_gutter_network` against, a borderless panel's surviving
    blob is the ink silhouette of the drawing, so tracing it returns a polygon
    shaped like the character. That reversal is conditional, not total, and
    both halves are visible on `diagonal_page.jpg`:

    * Its five framed panels trace exactly. The diamond comes back as a
      rotated square and its four neighbours come back correctly notched where
      it bites into them -- 6 to 8 vertices each. No bounding box can express
      that page at all: the diamond's box overlaps all four neighbours.
    * Its top panel is borderless, and the trace faithfully follows the
      artwork -- wings, confetti, hair -- at 40 vertices. Exactly D-17's case.

    The vertex count is what separates them. Measured over the seven test
    pages at `polygon_epsilon_frac`, framed panels come back with 4 to 9
    vertices and borderless artwork with 31 to 43. `max_polygon_vertices` sits
    in that gap, and above it the box is used, which is what D-17 asked for.

    The epsilon has to stay fine for this to work: at 0.02 every blob on every
    page collapsed to 4-5 vertices, erasing both the notches and the signal.
    """
    contours, _ = cv2.findContours(
        blob.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return box_to_polygon(box)

    outline = max(contours, key=cv2.contourArea)
    epsilon = params.polygon_epsilon_frac * cv2.arcLength(outline, True)
    simplified = cv2.approxPolyDP(outline, epsilon, True)

    if len(simplified) < 3 or len(simplified) > params.max_polygon_vertices:
        return box_to_polygon(box)

    return [(int(point[0][0]), int(point[0][1])) for point in simplified]


def segment_panels(
    line_mask: np.ndarray, params: PanelParams | None = None
) -> list[Panel]:
    """Return panels, as outlines, in reading order."""
    params = params or PanelParams()
    height, width = line_mask.shape
    short_side = min(height, width)
    radius = max(2, int(short_side * params.min_gutter_frac) // 2)

    gutter = _gutter_network(line_mask, radius)
    panel_area = ~gutter

    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        panel_area.astype(np.uint8), connectivity=4
    )

    min_area = params.min_area_frac * height * width
    panels: list[Panel] = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < min_area:
            continue
        if area / float(w * h) < params.min_solidity:
            continue
        box = PanelBox(int(x), int(y), int(w), int(h))
        panels.append(Panel(_panel_polygon(labels == index, box, params), box))

    if not panels:
        # No gutters found at all: full bleed, or a page that is one image.
        whole = PanelBox(0, 0, width, height)
        return [Panel(box_to_polygon(whole), whole)]

    return _reading_order(panels, params.reading)


def _reinforce_frames(line_mask: np.ndarray, length: int, gap: int) -> np.ndarray:
    """Repair breaks in panel frames before looking for gutters.

    A panel border is a long straight run; the thing crossing it — hair, an
    SFX glyph, a figure leaning out of frame — is short. So: keep only pixels
    belonging to long horizontal or vertical runs, bridge gaps along those runs,
    and add the result back to the line mask.

    Adding ink can only seal, never split. Panel area is defined as everything
    the margin cannot reach, and ink is never gutter, so reinforcing a straight
    line *inside* a panel (a building edge, a table) changes nothing. That
    asymmetry is what makes this safe to apply everywhere rather than only
    where a frame is suspected.
    """
    mask = line_mask.astype(np.uint8)

    horizontal_run = cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1))
    vertical_run = cv2.getStructuringElement(cv2.MORPH_RECT, (1, length))
    horizontal_gap = cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1))
    vertical_gap = cv2.getStructuringElement(cv2.MORPH_RECT, (1, gap))

    # Opening keeps only structures a long straight element fits inside.
    horizontals = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_run)
    verticals = cv2.morphologyEx(mask, cv2.MORPH_OPEN, vertical_run)

    # Closing along the same axis joins collinear fragments across the break.
    bridges = (
        cv2.morphologyEx(horizontals, cv2.MORPH_CLOSE, horizontal_gap) & ~horizontals
    ) | (cv2.morphologyEx(verticals, cv2.MORPH_CLOSE, vertical_gap) & ~verticals)

    # Critical: two panels side by side have collinear top borders, so closing
    # alone happily bridges straight across the gutter and welds them into one
    # panel. What separates the two cases is what sits in the break — artwork
    # crossing a frame leaves ink there, a gutter is clean paper. Keep only
    # bridge pixels that have ink nearby.
    reach = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gap // 3 + 1,) * 2)
    near_ink = cv2.dilate(mask, reach).astype(bool)

    return (mask.astype(bool)) | (bridges.astype(bool) & near_ink)


def _gutter_network(line_mask: np.ndarray, radius: int) -> np.ndarray:
    """Paper reachable by a disc of ``radius`` travelling in from the margin."""
    white = (~line_mask).astype(np.uint8)
    size = 2 * radius + 1
    ball = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    # Disc centres that fit entirely in paper.
    eroded = cv2.erode(white, ball)
    if not eroded.any():
        return np.zeros_like(line_mask)

    count, labels = cv2.connectedComponents(eroded, connectivity=4)
    if count <= 1:
        return np.zeros_like(line_mask)

    # Keep only the components the margin touches. A panel interior is paper
    # too, and also survives erosion — being connected to the border is the
    # whole discriminator.
    border = np.concatenate(
        [labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]
    )
    outside = set(int(v) for v in np.unique(border) if v != 0)
    if not outside:
        return np.zeros_like(line_mask)

    core = np.isin(labels, list(outside))
    # Dilate back: erosion shrank the gutter by the disc, restore its extent.
    grown = cv2.dilate(core.astype(np.uint8), ball).astype(bool)
    return grown & ~line_mask


def _reading_order(boxes: list[Panel], reading: ReadingDirection) -> list[Panel]:
    """Group panels into tiers, then order within each tier.

    Tiers run top to bottom in both traditions; only the horizontal direction
    differs. A panel spanning several tiers on one side of the page joins the
    first tier it overlaps, which is what a reader does.
    """
    tiers: list[list[Panel]] = []

    for box in sorted(boxes, key=lambda b: b.y):
        for tier in tiers:
            top = min(b.y for b in tier)
            bottom = max(b.y + b.height for b in tier)
            overlap = min(bottom, box.y + box.height) - max(top, box.y)
            if overlap > 0.5 * min(bottom - top, box.height):
                tier.append(box)
                break
        else:
            tiers.append([box])

    ordered: list[Panel] = []
    for tier in tiers:
        # Secondary sort by y keeps a stacked column reading top to bottom.
        tier.sort(key=lambda b: (-b.x if reading == "rtl" else b.x, b.y))
        ordered += tier
    return ordered

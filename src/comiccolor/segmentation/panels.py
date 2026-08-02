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
    min_gutter_frac: float = 0.012
    # Panels below this share of page area are debris, not panels.
    min_area_frac: float = 0.005
    # Reject blobs less solid than this (area over bounding-box area). Filters
    # L-shaped merges and stray line networks that survived the fill.
    min_solidity: float = 0.55
    # Shortest run counted as a panel frame, as a fraction of the shorter side.
    frame_length_frac: float = 0.05
    # Longest break in a frame to repair, as a fraction of the shorter side.
    # Sized to swallow hair, SFX and figures crossing a border.
    frame_gap_frac: float = 0.10
    reading: ReadingDirection = "rtl"


@dataclass
class PanelBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


def segment_panels(
    line_mask: np.ndarray, params: PanelParams | None = None
) -> list[PanelBox]:
    """Return panel boxes in reading order."""
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
    boxes: list[PanelBox] = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < min_area:
            continue
        if area / float(w * h) < params.min_solidity:
            continue
        boxes.append(PanelBox(int(x), int(y), int(w), int(h)))

    if not boxes:
        # No gutters found at all: full bleed, or a page that is one image.
        return [PanelBox(0, 0, width, height)]

    return _reading_order(boxes, params.reading)


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


def _reading_order(boxes: list[PanelBox], reading: ReadingDirection) -> list[PanelBox]:
    """Group panels into tiers, then order within each tier.

    Tiers run top to bottom in both traditions; only the horizontal direction
    differs. A panel spanning several tiers on one side of the page joins the
    first tier it overlaps, which is what a reader does.
    """
    tiers: list[list[PanelBox]] = []

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

    ordered: list[PanelBox] = []
    for tier in tiers:
        # Secondary sort by y keeps a stacked column reading top to bottom.
        tier.sort(key=lambda b: (-b.x if reading == "rtl" else b.x, b.y))
        ordered += tier
    return ordered

"""Synthetic page builders shared across the backend test suite.

Every builder here returns freshly allocated numpy arrays from pure
parameters — no image file ever touches disk, following the
``tests/test_panels.py`` / ``tests/test_trappedball.py`` idiom of boolean
arrays built by slice assignment. This module exists so ``tests/test_bubbles.py``
(D-22/D-23's bubble detector) and ``tests/test_trappedball.py`` (the
boundary-crossing case success criterion 4 names) share one definition of
"a page with a bubble" rather than each inventing one.
"""

from __future__ import annotations

import cv2
import numpy as np


def glyph_row(
    page: np.ndarray,
    x: int,
    y: int,
    count: int = 6,
    glyph_w: int = 8,
    glyph_h: int = 12,
    gap: int = 5,
) -> None:
    """Write ``count`` baseline-aligned dark blobs of identical height into
    ``page`` (a boolean array), in place.

    This is the positive case D-23's height/baseline/aspect filters must
    accept: every blob shares the same top (``y``) and the same height
    (``glyph_h``), the signature of text sitting on a baseline.
    """
    for i in range(count):
        gx = x + i * (glyph_w + gap)
        page[y : y + glyph_h, gx : gx + glyph_w] = True


def bubble_page(width: int = 600, height: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """A page with one closed elliptical speech-bubble outline containing a
    glyph row, plus a patch of irregular-height hatching outside it.

    Returns ``(grey, line_mask)``: ``line_mask`` is a bool array (the bubble
    outline and the two text-like patches), ``grey`` is its uint8 inverse
    (255 = paper, 0 = ink). The glyph row inside the bubble is D-23's
    positive case; the irregular-height hatching outside it is the negative
    case the same filters must reject.
    """
    drawing = np.zeros((height, width), dtype=np.uint8)

    centre = (width // 2, height // 2)
    axes = (width // 4, height // 6)
    cv2.ellipse(drawing, centre, axes, 0, 0, 360, 1, thickness=2)

    line_mask = drawing.astype(bool)
    glyph_row(
        line_mask,
        x=centre[0] - 24,
        y=centre[1] - 6,
        count=6,
        glyph_w=8,
        glyph_h=12,
        gap=5,
    )

    # Irregular-height hatching outside the bubble: no shared baseline, no
    # uniform height -- the case D-23's filters must reject.
    heights = (6, 14, 9, 20, 5, 17)
    hatch_x, hatch_y = 40, height - 60
    for i, h in enumerate(heights):
        gx = hatch_x + i * 14
        line_mask[hatch_y : hatch_y + h, gx : gx + 4] = True

    grey = np.where(line_mask, 0, 255).astype(np.uint8)
    return grey, line_mask


def boundary_crossing_page(
    width: int = 600, height: int = 400
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int, int, int]]]:
    """A synthetic two-panel page whose bubble straddles the gutter.

    Returns ``(grey, line_mask, panel_boxes)``: two framed panels
    (``panel_boxes`` as ``(x, y, w, h)`` tuples) separated by a vertical
    gutter, with one closed bubble outline centred on the gutter so its
    pixels fall inside BOTH panel boxes. This is success criterion 4's
    "not only on a clean test page" fixture -- D-20's page-scoped
    ``ProtectedMask`` exists specifically because this case is
    unrepresentable at panel scope.
    """
    gutter = 30
    panel_w = (width - 3 * gutter) // 2
    panel_h = height - 2 * gutter
    panel_y = gutter
    panel1_x = gutter
    panel2_x = gutter + panel_w + gutter

    panel_boxes: list[tuple[int, int, int, int]] = [
        (panel1_x, panel_y, panel_w, panel_h),
        (panel2_x, panel_y, panel_w, panel_h),
    ]

    drawing = np.zeros((height, width), dtype=np.uint8)
    for px, py, pw, ph in panel_boxes:
        cv2.rectangle(drawing, (px, py), (px + pw - 1, py + ph - 1), 1, thickness=2)

    # The bubble is centred on the gutter's midpoint and wide enough that
    # its outline reaches past both panel edges into each panel's interior.
    gutter_mid_x = panel1_x + panel_w + gutter // 2
    centre = (gutter_mid_x, height // 2)
    axes = (gutter + 20, 40)
    cv2.ellipse(drawing, centre, axes, 0, 0, 360, 1, thickness=2)

    line_mask = drawing.astype(bool)
    grey = np.where(line_mask, 0, 255).astype(np.uint8)
    return grey, line_mask, panel_boxes

"""PROT-01, D-22, D-23, D-24: the bubble detector's behavioural contract.

D-22's own algorithm -- detect the text, flood-fill the enclosing white
outward from it, cap the area, discard text that is not sitting in white --
is exercised here against `comiccolor.segmentation.bubbles`. The first test
verifies `cv2.floodFill`'s `FLOODFILL_MASK_ONLY` flag/mask-size/fill-value
convention directly against the installed OpenCV 5.0.0 build, per
02-RESEARCH.md Pitfall 2 -- that convention is `[ASSUMED]` in the research
sketch, not trusted, until this test proves it on this machine. D-24's SFX
deferral needs no positive test: lettering with no enclosing white to fill
falls out of every case below by construction, which is why PROT-02's
hand-drawing is the guaranteed fallback rather than a gap.
"""

from __future__ import annotations

import cv2
import numpy as np

from tests.conftest import bubble_page, glyph_row


def test_floodfill_mask_only_semantics_on_this_opencv_build():
    """02-RESEARCH.md Pitfall 2: `FLOODFILL_MASK_ONLY` needs a mask 2px
    larger than the image on every side, and the newMaskVal-in-high-byte
    flag convention (`255 << 8`) is easy to get backwards. A hand-built
    closed white box, flood-filled from an interior pixel, must come back
    as True *inside* the box and False *outside* it after cropping the 2px
    padding -- the inverted-mask symptom this test exists to catch."""
    image = np.zeros((20, 20), dtype=np.uint8)
    image[5:15, 5:15] = 255  # a closed 10x10 white box

    mask = np.zeros((22, 22), dtype=np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (255 << 8)
    cv2.floodFill(image.copy(), mask, (9, 9), 255, loDiff=0, upDiff=0, flags=flags)

    cropped = mask[1:-1, 1:-1].astype(bool)
    assert cropped[5:15, 5:15].all(), "the box interior must be filled"
    outside = cropped.copy()
    outside[5:15, 5:15] = False
    assert not outside.any(), "nothing outside the box should be filled"


def test_one_bubble_yields_one_mask():
    """`bubble_page()` has one closed bubble outline containing a
    baseline-aligned glyph row -- D-22's positive case must yield exactly
    one mask, not one per glyph."""
    from comiccolor.segmentation.bubbles import detect_bubbles

    grey, line_mask = bubble_page()
    bubbles = detect_bubbles(grey, line_mask)
    assert len(bubbles) == 1


def test_hatching_is_not_a_bubble():
    """Irregular-height hatching with no shared baseline and no enclosing
    outline -- D-23's negative case. Whatever glyph candidates the height/
    aspect filters admit, there is no closed white to fill, so the fill
    either escapes the open page (area cap) or never seeds at all."""
    from comiccolor.segmentation.bubbles import detect_bubbles

    width, height = 600, 400
    line_mask = np.zeros((height, width), dtype=bool)
    heights = (6, 14, 9, 20, 5, 17)
    hatch_x, hatch_y = 40, height - 60
    for i, h in enumerate(heights):
        gx = hatch_x + i * 14
        line_mask[hatch_y : hatch_y + h, gx : gx + 4] = True
    grey = np.where(line_mask, 0, 255).astype(np.uint8)

    assert detect_bubbles(grey, line_mask) == []


def test_unclosed_bubble_is_discarded_by_area_cap():
    """A bubble outline with a gap in it, on a page with open white
    margins, must yield zero bubbles rather than one covering most of the
    page -- D-22 point 3, the unclosed-bubble leak."""
    from comiccolor.segmentation.bubbles import detect_bubbles

    width, height = 600, 400
    drawing = np.zeros((height, width), dtype=np.uint8)
    centre = (width // 2, height // 2)
    axes = (width // 4, height // 6)
    # Only 0..300 degrees drawn: the remaining 60 degrees is the gap the
    # fill escapes through into the page margins.
    cv2.ellipse(drawing, centre, axes, 0, 0, 300, 1, thickness=2)

    line_mask = drawing.astype(bool)
    glyph_row(
        line_mask, x=centre[0] - 24, y=centre[1] - 6, count=6, glyph_w=8, glyph_h=12, gap=5
    )
    grey = np.where(line_mask, 0, 255).astype(np.uint8)

    assert detect_bubbles(grey, line_mask) == []


def test_lettering_on_artwork_is_discarded():
    """A closed outline enclosing dark/textured ground rather than paper --
    D-22 point 4's "lettering sitting on artwork," which is also why D-24
    can defer SFX proposal: a glyph cluster on ink produces nothing here by
    construction, not by a separate rule."""
    from comiccolor.segmentation.bubbles import detect_bubbles

    width, height = 600, 400
    drawing = np.zeros((height, width), dtype=np.uint8)
    centre = (width // 2, height // 2)
    axes = (width // 4, height // 6)
    cv2.ellipse(drawing, centre, axes, 0, 0, 360, 1, thickness=2)

    line_mask = drawing.astype(bool)
    glyph_row(
        line_mask, x=centre[0] - 24, y=centre[1] - 6, count=6, glyph_w=8, glyph_h=12, gap=5
    )

    # Dark/textured ground everywhere, inside a properly closed outline --
    # isolates the brightness discard from the area cap, which would also
    # accept this geometry if it were paper-white.
    grey = np.full((height, width), 80, dtype=np.uint8)
    grey[line_mask] = 0

    assert detect_bubbles(grey, line_mask) == []


def test_mask_to_polygon_returns_page_space_vertices():
    """The traced polygon has a workable vertex count and stays within the
    page bounds -- an editable vertex polygon, not a raster blob."""
    from comiccolor.segmentation.bubbles import mask_to_polygon

    width, height = 200, 150
    mask = np.zeros((height, width), dtype=bool)
    mask[30:100, 40:160] = True

    polygon = mask_to_polygon(mask)

    assert 3 <= len(polygon) <= 64
    for x, y in polygon:
        assert 0 <= x < width
        assert 0 <= y < height


def test_mask_to_polygon_on_empty_mask_returns_empty_list():
    """No contour, no polygon -- a degenerate trace must never reach the
    store as an unrenderable shape."""
    from comiccolor.segmentation.bubbles import mask_to_polygon

    mask = np.zeros((50, 50), dtype=bool)
    assert mask_to_polygon(mask) == []

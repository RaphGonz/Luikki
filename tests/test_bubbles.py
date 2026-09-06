"""PROT-01, D-22, D-24, D-25: the bubble detector's behavioural contract.

Detection is a model now (`bubbles.BubbleDetector`), and the tests split along
that seam. The tracing step -- box in, polygon out -- is ordinary geometry and
is tested here directly with hand-built boxes, so the whole of the logic that
can be wrong is covered without a 161 MB download. The model itself is checked
against the artist's counts in `test_pages/bubble_counts.txt` by one test that
skips when the weights are not on this machine.

The negative cases the old heuristic detector needed -- hatching is not a
bubble, lettering on artwork is not a bubble -- have moved to that same
model-backed test, because they are now claims about the model rather than
about anything in this repository. They are the cases the heuristic version
failed on real pages: hatching read as `iiii`, cup holders read as `OOO`.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from luikki.segmentation.bubbles import BubbleParams, trace_bubble

PAGES = Path(__file__).resolve().parent.parent / "test_pages"


def _page(name: str) -> Path:
    """A test page by filename, wherever under `test_pages/` it now lives.

    The artist groups the pages by book as the set grows, so the directory
    layout moves; the filenames in `bubble_counts.txt` do not. Searching by
    name keeps the counts file the thing this test is pinned to.
    """
    found = sorted(PAGES.rglob(name))
    if not found:
        raise FileNotFoundError(f"{name} is not anywhere under {PAGES}")
    return found[0]


def _page_with_balloon(gap: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """A closed elliptical balloon with a line of lettering inside it.

    `gap` opens the outline by that many degrees, which is the case that broke
    every flood-fill version of this module: an open outline is a `C`, and
    filling a `C` fills the stroke and leaves the middle out.
    """
    width, height = 600, 400
    drawing = np.zeros((height, width), dtype=np.uint8)
    centre = (width // 2, height // 2)
    axes = (120, 60)
    cv2.ellipse(drawing, centre, axes, 0, gap, 360, 1, thickness=2)

    line_mask = drawing.astype(bool)
    for i in range(6):
        x = centre[0] - 45 + i * 15
        line_mask[centre[1] - 8 : centre[1] + 8, x : x + 9] = True

    box = np.array(
        [centre[0] - axes[0], centre[1] - axes[1], centre[0] + axes[0], centre[1] + axes[1]],
        dtype=np.float32,
    )
    return line_mask, box


def _area(polygon: list[tuple[int, int]]) -> float:
    return abs(cv2.contourArea(np.array(polygon, dtype=np.int32)))


def _is_simple(polygon: list[tuple[int, int]]) -> bool:
    """No edge crosses another. A star-shaped trace guarantees this; the test
    exists because the previous version returned polygons that folded inward
    around the lettering, and that is what a self-crossing shape looks like."""
    points = [np.array(p, dtype=float) for p in polygon]
    n = len(points)

    def crosses(a, b, c, d):
        def side(p, q, r):
            u, v = q - p, r - p
            return np.sign(u[0] * v[1] - u[1] * v[0])

        return (
            side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0
        )

    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if crosses(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
                return False
    return True


def test_closed_balloon_traces_its_outline():
    """The polygon covers the balloon rather than the lettering inside it.
    The ellipse is 120x60, so its area is about 22600 px against a box of
    240x120 = 28800 -- anything near the text's own 100x16 means the trace
    stopped at the words."""
    line_mask, box = _page_with_balloon()
    polygon = trace_bubble(line_mask, box)

    assert len(polygon) >= 3
    assert 0.6 * 28800 <= _area(polygon) <= 1.4 * 28800


def test_open_balloon_still_traces():
    """A 40-degree gap in the outline must change the result hardly at all.
    This is `manga_page.jpg`'s case, where Otsu leaves the outline dotted, and
    it is the case that made every closed-curve method return a shape folded
    in around the text."""
    closed_mask, box = _page_with_balloon()
    open_mask, _ = _page_with_balloon(gap=40)

    closed = _area(trace_bubble(closed_mask, box))
    opened = _area(trace_bubble(open_mask, box))

    assert opened > 0.8 * closed


def test_traced_polygon_is_simple():
    """No self-intersection, open outline or closed."""
    for gap in (0, 40):
        line_mask, box = _page_with_balloon(gap=gap)
        assert _is_simple(trace_bubble(line_mask, box))


def test_borderless_balloon_traces_its_lettering():
    """A balloon with no outline drawn at all comes back as its text block.

    This is the one place the trace has no boundary to find, so the furthest
    ink on each ray *is* the lettering. Protecting the text block rather than
    the box is the better of the two available answers -- the box would claim
    the artwork around a borderless caption and leave holes in the flats --
    but it is a real limitation and not a bug: the white margin of such a
    caption is left unprotected and will be coloured.
    """
    line_mask, box = _page_with_balloon()
    line_mask[:, :] = False
    for i in range(6):
        x = 300 - 45 + i * 15
        line_mask[192:208, x : x + 9] = True

    polygon = trace_bubble(line_mask, box)
    assert _area(polygon) < 0.25 * 28800
    for x, y in polygon:
        assert 230 <= x <= 370 and 170 <= y <= 230


def test_polygon_stays_inside_the_page():
    """A balloon at the page edge must not produce out-of-bounds vertices."""
    line_mask, _ = _page_with_balloon()
    box = np.array([-30.0, -20.0, 90.0, 60.0], dtype=np.float32)
    for x, y in trace_bubble(line_mask, box):
        assert 0 <= x < line_mask.shape[1]
        assert 0 <= y < line_mask.shape[0]


def test_degenerate_box_returns_no_polygon():
    """A box a few pixels across is not a balloon; it must yield nothing
    rather than an unrenderable shape."""
    line_mask, _ = _page_with_balloon()
    assert trace_bubble(line_mask, np.array([10.0, 10.0, 14.0, 14.0])) == []


def test_vertex_count_stays_editable():
    """The artist will drag these points. A trace of 128 rays that came back
    as 128 vertices would be a raster blob wearing a polygon's clothes."""
    line_mask, box = _page_with_balloon()
    assert 3 <= len(trace_bubble(line_mask, box)) <= 40


@pytest.mark.skipif(
    not (
        Path(os.environ.get("LUIKKI_BUBBLE_MODEL", "models/comic_bubble_detector.onnx")).exists()
        and PAGES.exists()
    ),
    reason="detector weights or test pages not on this machine",
)
def test_detector_matches_the_artists_counts():
    """The numbers in `test_pages/bubble_counts.txt`, which the artist wrote.

    Three of these pages have no balloons at all and are the cases the
    heuristic detector invented them on: hatching read as `iiii` on moebius
    and antoine, cup holders read as `OOO` on teddy. A page of SFX lettering
    (laurine's Blop/Pop/Hiii) must still yield exactly its four balloons.
    """
    from luikki.segmentation.bubbles import BubbleDetector, detect_bubbles
    from luikki.segmentation.preprocess import load_line_art

    expected = {
        "antoine_page.png": 0,
        "laurine_page.jpg": 4,
        "manga_page.jpg": 4,
        "moebius_page.jpg": 0,
        "teddy_page.png": 0,
        "tintin_page.jpg": 12,
    }
    detector = BubbleDetector()

    found = {}
    for name in expected:
        line_mask, grey = load_line_art(_page(name))
        found[name] = len(detect_bubbles(grey, line_mask, detector=detector))

    assert found == expected


def test_params_are_overridable():
    """`BubbleParams` is the whole of the tuning surface; a caller must be
    able to trade fit for robustness without editing the module."""
    line_mask, box = _page_with_balloon()
    coarse = trace_bubble(line_mask, box, BubbleParams(epsilon_frac=0.1))
    fine = trace_bubble(line_mask, box, BubbleParams(epsilon_frac=0.001))
    assert len(fine) > len(coarse)

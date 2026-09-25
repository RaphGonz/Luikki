"""The fast LineFiller passes give upstream's answer, pixel for pixel.

`linefiller_fast` exists for speed only. If it ever disagrees with the vendored
code, the segmentation changed without anyone looking at a render, so every
pass is compared on real ink as well as on a drawing built to be awkward.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from luikki.segmentation import linefiller_fast as fast
from luikki.segmentation.segmenter import LineFillerSegmenter

PAGES = Path(__file__).resolve().parents[1] / "test_pages"


def _drawn() -> np.ndarray:
    """Closed shapes, open ones, thin gaps, specks and a frame touching the edge."""
    image = np.full((300, 420), 255, np.uint8)
    cv2.rectangle(image, (0, 0), (419, 299), 0, 2)
    cv2.circle(image, (90, 90), 50, 0, 2)
    cv2.ellipse(image, (260, 120), (90, 50), 0, 20, 340, 0, 3)  # open: a leak
    cv2.line(image, (20, 200), (400, 210), 0, 1)
    cv2.line(image, (200, 150), (205, 290), 0, 4)
    for x in range(30, 400, 37):
        cv2.circle(image, (x, 260), 2, 0, -1)
    return image


def _real(name: str, box: tuple[int, int, int, int]) -> np.ndarray:
    path = PAGES / name
    if not path.exists():
        pytest.skip(f"{name} not in test_pages")
    grey = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    x, y, w, h = box
    crop = grey[y : y + h, x : x + w]
    return np.where(crop < 128, 0, 255).astype(np.uint8)


def _images():
    yield "drawn", _drawn()
    yield "teddy", _real("teddy_page.png", (300, 900, 700, 600))
    yield "antoine", _real("antoine_page.png", (400, 400, 800, 700))


@pytest.fixture(scope="module")
def upstream():
    return LineFillerSegmenter._load()


def _same_fills(ours, theirs):
    assert len(ours) == len(theirs)
    for (rows, cols), (their_rows, their_cols) in zip(ours, theirs):
        np.testing.assert_array_equal(rows, their_rows)
        np.testing.assert_array_equal(cols, their_cols)


@pytest.mark.parametrize("name,image", list(_images()))
def test_every_pass_matches_upstream(upstream, name, image):
    ours_image = theirs_image = image
    ours_fills, theirs_fills = [], []
    for radius, method in zip((3, 2, 1), ("max", "mean", "mean")):
        ours = fast.trapped_ball_fill_multi(ours_image, radius, method=method)
        theirs = upstream.trapped_ball_fill_multi(theirs_image, radius, method=method)
        _same_fills(ours, theirs)
        ours_fills += ours
        theirs_fills += theirs
        ours_image = upstream.mark_fill(ours_image, ours)
        theirs_image = upstream.mark_fill(theirs_image, theirs)

    ours = fast.flood_fill_multi(ours_image)
    theirs = upstream.flood_fill_multi(theirs_image)
    _same_fills(ours, theirs)

    fillmap = upstream.build_fill_map(theirs_image, theirs_fills + theirs)
    np.testing.assert_array_equal(
        fast.merge_fill(fillmap, max_iter=10), upstream.merge_fill(fillmap, max_iter=10)
    )

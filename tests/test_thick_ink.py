"""A thick stroke is a wall, even when the extractor hands back only its edges.

The second tester's page (antoine_page) merged zones across strokes ten pixels
wide: MangaLineExtraction returned each one as two thin edges, and a break in
either edge let the zones meet through the stroke's hollow middle.
"""

from __future__ import annotations

import cv2
import numpy as np

from luikki.segmentation.preprocess import thick_ink
from luikki.segmentation.segmenter import LineFillerSegmenter


def test_the_band_keeps_strokes_and_drops_hatching_and_spot_blacks():
    ink = np.zeros((200, 300), bool)
    ink[20:180, 40:52] = True  # a 12 px stroke
    for x in range(100, 160, 8):
        ink[20:180, x : x + 2] = True  # 2 px hatching
    ink[60:140, 200:280] = True  # an 80 px spot black

    band = thick_ink(ink)
    assert band[20:180, 40:52].mean() > 0.9
    assert not band[:, 100:160].any()
    # Only the corners a round ball cannot reach into.
    assert band[60:140, 200:280].mean() < 0.05


def _same_zone(line_mask: np.ndarray, left, right) -> bool:
    labels = LineFillerSegmenter().segment(line_mask)
    return labels[left] == labels[right]


def test_a_hollowed_stroke_with_a_broken_edge_still_separates_two_zones():
    height, width = 240, 320
    ink = np.zeros((height, width), bool)
    cv2.rectangle(ink.view(np.uint8), (4, 4), (width - 5, height - 5), 1, 3)
    ink[:, 154:166] = True  # the stroke between the two zones, 12 px

    # What the extractor returns: the frame, and the stroke as its two edges,
    # one of them broken — the corridor the zones leaked through.
    extracted = np.zeros_like(ink)
    cv2.rectangle(extracted.view(np.uint8), (4, 4), (width - 5, height - 5), 1, 3)
    extracted[:, 154:156] = True
    extracted[:, 164:166] = True
    extracted[100:130, 154:156] = False
    extracted[150:180, 164:166] = False

    left, right = (120, 60), (120, 260)
    assert _same_zone(extracted, left, right), "the leak this fixes"
    assert not _same_zone(extracted | thick_ink(ink), left, right)

"""A page drawn here, for checking a build where the test pages cannot go.

    python packaging/synthetic_page.py <out.png>

The test pages are under copyright and the release build runs in public, so
`smoke.py` gets this instead: panels, a figure with closed and open lines, a
balloon with its tail. It checks that every step runs in the bundle, not how
well: judging segmentation is for real ink.
"""

from __future__ import annotations

import sys

import cv2
import numpy as np


def draw() -> np.ndarray:
    page = np.full((1600, 1100), 255, dtype=np.uint8)
    for x0, y0, x1, y1 in ((40, 40, 1060, 700), (40, 730, 535, 1560), (565, 730, 1060, 1120), (565, 1150, 1060, 1560)):
        cv2.rectangle(page, (x0, y0), (x1, y1), 0, 6)
    # A figure: head, shoulders, an arm left open at the elbow.
    cv2.circle(page, (300, 360), 110, 0, 5)
    cv2.ellipse(page, (300, 640), (190, 120), 0, 180, 360, 0, 5)
    cv2.line(page, (150, 560), (90, 690), 0, 5)
    cv2.line(page, (450, 560), (520, 640), 0, 5)
    # A balloon and its tail, pointing at the head.
    cv2.ellipse(page, (760, 220), (220, 120), 0, 0, 360, 0, 4)
    cv2.line(page, (640, 320), (430, 330), 0, 4)
    cv2.line(page, (700, 335), (430, 330), 0, 4)
    # Something in each small panel: a house, a sun, a hatched ground.
    cv2.rectangle(page, (160, 1100), (420, 1400), 0, 5)
    cv2.line(page, (140, 1110), (290, 950), 0, 5)
    cv2.line(page, (440, 1110), (290, 950), 0, 5)
    cv2.circle(page, (810, 920), 100, 0, 5)
    for x in range(600, 1040, 30):
        cv2.line(page, (x, 1540), (x + 20, 1400), 0, 2)
    return page


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    cv2.imwrite(sys.argv[1], draw())

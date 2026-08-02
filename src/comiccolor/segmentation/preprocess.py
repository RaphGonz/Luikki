"""Loading real ink layers into a binary line mask.

§7's training-data note cuts both ways: real ink layers are not the clean,
closed, uniformly weighted rasters the manga literature trains on. They arrive
as RGBA with meaningful alpha, as greyscale with heavy anti-aliasing, or as
merged art. This module normalises those into one boolean array and nothing
more — every downstream stage takes ``line_mask`` where True means ink.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_line_art(
    path: str | Path,
    threshold: int | None = None,
    supersample: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Load an ink layer and binarise it.

    Returns ``(line_mask, grey)`` where ``line_mask`` is boolean with True on
    ink, and ``grey`` is the 8-bit greyscale the mask was derived from (kept
    because anti-aliased edges carry sub-pixel information the flats need to
    composite under, §10).

    ``threshold`` of None uses Otsu. ``supersample`` of 2-4 upscales before
    binarising, which is §10's remedy for anti-aliased line art — it keeps thin
    AA-only lines from dropping out and closing gaps that are not really there.
    """
    path = Path(path)
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"could not read image: {path}")

    if raw.ndim == 3 and raw.shape[2] == 4:
        # Alpha is the ink channel on a real ink layer: transparent = no ink.
        alpha = raw[:, :, 3]
        rgb = raw[:, :, :3]
        luma = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
        # Composite over white so ink darkness and coverage both count.
        grey = (255 - (255 - luma).astype(np.float32) * (alpha / 255.0)).astype(np.uint8)
    elif raw.ndim == 3:
        grey = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    else:
        grey = raw

    if grey.dtype != np.uint8:
        grey = cv2.normalize(grey, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    if supersample > 1:
        grey = cv2.resize(
            grey,
            (grey.shape[1] * supersample, grey.shape[0] * supersample),
            interpolation=cv2.INTER_CUBIC,
        )

    if threshold is None:
        _, binary = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        _, binary = cv2.threshold(grey, threshold, 255, cv2.THRESH_BINARY_INV)

    return binary.astype(bool), grey


def ink_fraction(line_mask: np.ndarray) -> float:
    """Share of the page that is ink. A quick sanity check on binarisation.

    Values over ~0.35 usually mean the threshold caught a screentone or a spot
    black as line, which will wreck the region count in P3.
    """
    return float(np.count_nonzero(line_mask)) / line_mask.size


def estimate_line_width(line_mask: np.ndarray) -> float:
    """Median stroke width in pixels, via the distance transform on ink.

    Used to size the gap-closure and region-merge kernels so they scale with
    the art rather than with a hard-coded constant.
    """
    if not line_mask.any():
        return 1.0
    dist = cv2.distanceTransform(line_mask.astype(np.uint8), cv2.DIST_L2, 5)
    # Ridge pixels approximate the stroke medial axis; twice their distance is
    # the local stroke width.
    ridge = dist[dist > 0]
    if ridge.size == 0:
        return 1.0
    return float(2.0 * np.percentile(ridge, 75))

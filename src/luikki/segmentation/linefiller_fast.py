"""LineFiller's three slow passes, rewritten to give the same answer faster.

The vendored `linefiller.trappedball_fill` does whole-image work for every
fill it makes: a full `np.where` to find the next seed, a full erosion, two
full-size flood masks, a full `np.where` to read the fill back. On a 14 Mpx
page with thousands of zones that is thousands of passes over 14 million
pixels, and the second tester waited minutes for it. `merge_fill` does the same
once per zone per iteration, with `np.where(result == id)`.

Everything here is **bit-identical** to upstream, which `tests/test_linefiller_fast.py`
checks against the vendored code. Nothing about the segmentation changes, so
there is no render to judge, only a clock. The equivalences it rests on:

- A fill is confined to its component's bounding box grown by the ball radius
  (one dilation shrinks it, one erosion grows it back), so every morphology
  step can run on that crop. Outside the crop upstream's buffers hold 255,
  which neither the dilation nor the erosion lets reach a pixel that matters.
- The unfilled area only ever loses pixels, so the first unfilled point in
  raster order only moves forward: a cursor replaces the full `np.where`.
  The same holds for its erosion, kept up to date around each fill.
- The merge reads every zone's pixels from the map as it stood at the start of
  the iteration. One stable argsort gives all of them in one pass, each list
  in the order `np.where` would have returned it.
"""

from __future__ import annotations

import cv2
import numpy as np

_CHUNK = 1 << 16


def _ball(radius: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))


class _Cursor:
    """The first 255 of a flat array whose 255s only ever turn to 0."""

    def __init__(self, flat: np.ndarray):
        self.flat = flat
        self.at = 0

    def next(self) -> int | None:
        size = self.flat.size
        while self.at < size:
            chunk = self.flat[self.at : self.at + _CHUNK]
            hits = np.flatnonzero(chunk == 255)
            if hits.size:
                self.at += int(hits[0])
                return self.at
            self.at += chunk.size
        return None


def _component(unfilled: np.ndarray, mask: np.ndarray, seed: tuple[int, int]):
    """The 4-connected run of 255 holding `seed`, as a crop and its box.

    `mask` is a reused (h + 2, w + 2) zero buffer: flooding in mask-only mode
    touches the component and nothing else, where upstream allocates and
    scans two whole-page arrays per fill.
    """
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | (1 << 8)
    _, _, _, (x, y, w, h) = cv2.floodFill(unfilled, mask, seed, 0, 0, 0, flags)
    inside = mask[y + 1 : y + 1 + h, x + 1 : x + 1 + w].astype(bool)
    mask[y + 1 : y + 1 + h, x + 1 : x + 1 + w] = 0
    return inside, (x, y, w, h)


def trapped_ball_fill_multi(image: np.ndarray, radius: int, method: str = "mean", max_iter: int = 1000):
    """`linefiller.trapped_ball_fill_multi`, same arguments, same result."""
    height, width = image.shape
    ball = _ball(radius)
    unfilled = image.copy()
    eroded = cv2.morphologyEx(unfilled, cv2.MORPH_ERODE, ball)
    cursor = _Cursor(eroded.reshape(-1))
    mask = np.zeros((height + 2, width + 2), np.uint8)

    filled, sizes = [], []
    for _ in range(max_iter):
        at = cursor.next()
        if at is None:
            break
        seed_y, seed_x = divmod(at, width)

        inside, (x, y, w, h) = _component(unfilled, mask, (seed_x, seed_y))
        # The crop: the component's box, grown past where the fill can reach.
        margin = radius + 1
        x0, y0 = max(0, x - margin), max(0, y - margin)
        x1, y1 = min(width, x + w + margin), min(height, y + h + margin)

        pass1 = np.full((y1 - y0, x1 - x0), 255, np.uint8)
        pass1[y - y0 : y - y0 + h, x - x0 : x - x0 + w][inside] = 0
        pass1 = cv2.morphologyEx(pass1, cv2.MORPH_DILATE, ball)
        mask2 = cv2.copyMakeBorder(pass1, 1, 1, 1, 1, cv2.BORDER_CONSTANT, 0)
        pass2 = np.full(pass1.shape, 255, np.uint8)
        cv2.floodFill(pass2, mask2, (seed_x - x0, seed_y - y0), 0, 0, 0, 4)
        pass2 = cv2.morphologyEx(pass2, cv2.MORPH_ERODE, ball)

        rows, cols = np.nonzero(pass2 == 0)
        rows += y0
        cols += x0
        unfilled[rows, cols] = 0
        filled.append((rows, cols))
        sizes.append(len(rows))

        # The erosion changes only near what was just filled.
        e0, f0 = max(0, x0 - 2 * radius), max(0, y0 - 2 * radius)
        e1, f1 = min(width, x1 + 2 * radius), min(height, y1 + 2 * radius)
        window = cv2.morphologyEx(unfilled[f0:f1, e0:e1], cv2.MORPH_ERODE, ball)
        g0, h0 = max(0, x0 - radius), max(0, y0 - radius)
        g1, h1 = min(width, x1 + radius), min(height, y1 + radius)
        eroded[h0:h1, g0:g1] = window[h0 - f0 : h1 - f0, g0 - e0 : g1 - e0]

    sizes = np.asarray(sizes)
    if method == "max":
        floor = np.max(sizes)
    elif method == "median":
        floor = np.median(sizes)
    elif method == "mean":
        floor = np.mean(sizes)
    else:
        floor = 0
    return [filled[i] for i in np.where(sizes >= floor)[0]]


def flood_fill_multi(image: np.ndarray, max_iter: int = 20000):
    """`linefiller.flood_fill_multi`, same arguments, same result."""
    height, width = image.shape
    unfilled = image.copy()
    cursor = _Cursor(unfilled.reshape(-1))
    mask = np.zeros((height + 2, width + 2), np.uint8)

    filled = []
    for _ in range(max_iter):
        at = cursor.next()
        if at is None:
            break
        seed_y, seed_x = divmod(at, width)
        inside, (x, y, _, _) = _component(unfilled, mask, (seed_x, seed_y))
        rows, cols = np.nonzero(inside)
        rows += y
        cols += x
        unfilled[rows, cols] = 0
        filled.append((rows, cols))
    return filled


def _border_point(points, rect, max_height: int, max_width: int):
    """Upstream's `get_border_point`, unchanged: it is already local."""
    x1, y1, x2, y2 = rect
    bx1, by1 = max(0, x1 - 2), max(0, y1 - 2)
    bx2 = x2 + 3 if x2 + 3 < max_width else max_width
    by2 = y2 + 3 if y2 + 3 < max_height else max_height

    fill = np.zeros((by2 - by1, bx2 - bx1), np.uint8)
    fill[(points[0] - by1, points[1] - bx1)] = 255

    contours, _ = cv2.findContours(fill, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    approx = cv2.approxPolyDP(contours[0], 0.02 * cv2.arcLength(contours[0], True), True)

    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    border = cv2.morphologyEx(fill, cv2.MORPH_DILATE, cross) - fill
    rows, cols = np.where(border == 255)
    return (rows + by1, cols + bx1), approx


def merge_fill(fillmap: np.ndarray, max_iter: int = 10):
    """`linefiller.merge_fill`, same arguments, same result."""
    max_height, max_width = fillmap.shape[:2]
    result = fillmap.copy()
    lines = fillmap == 0

    for _ in range(max_iter):
        result[lines] = 0

        # Every zone's pixels, in one pass instead of one scan per zone.
        flat = result.reshape(-1)
        order = np.argsort(flat, kind="stable")
        ids, starts, counts = np.unique(flat[order], return_index=True, return_counts=True)

        fills = []
        for fill_id, start, count in zip(ids, starts, counts):
            rows, cols = np.divmod(order[start : start + count], max_width)
            fills.append(
                {
                    "id": fill_id,
                    "point": (rows, cols),
                    "area": int(count),
                    "rect": (int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())),
                }
            )

        for fill in fills:
            if fill["id"] == 0:
                continue

            border_points, approx = _border_point(fill["point"], fill["rect"], max_height, max_width)
            pixel_ids = np.unique(result[border_points])

            ids_around = pixel_ids[np.nonzero(pixel_ids)]
            new_id = fill["id"]
            if len(ids_around) == 0:
                if fill["area"] < 5:
                    new_id = 0
            else:
                new_id = ids_around[0]

            if len(approx) == 1 or fill["area"] == 1:
                result[fill["point"]] = new_id
            if len(approx) in [2, 3, 4, 5] and fill["area"] < 500:
                result[fill["point"]] = new_id
            if fill["area"] < 250 and len(ids_around) == 1:
                result[fill["point"]] = new_id
            if fill["area"] < 50:
                result[fill["point"]] = new_id

        if len(ids) == len(np.unique(result)):
            break

    return result

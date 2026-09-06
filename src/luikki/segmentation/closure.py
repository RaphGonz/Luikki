"""§1.3 Line gap closure. The highest-variance step across art styles.

Two mechanisms, in order of preference:

1. The trapped-ball radius schedule itself. A ball of radius r cannot escape
   through a gap narrower than 2r, so segmenting at descending radii already
   tolerates gaps without touching the line raster. This is preferred because
   it modifies nothing and is reversible by changing one parameter.

2. Endpoint bridging, here. Skeletonise the ink, find stroke ends, and join
   ends that are close and roughly facing each other. This *does* modify the
   line raster, so it is opt-in and the modification is returned separately
   from the original mask — the bridges are never composited into the
   deliverable, only into the raster that segmentation consumes.

Sketch and ink lines are open by nature. Extracted lines are not, which is
exactly why §7 warns against evaluating on extracted line art: it makes this
stage look solved when it is not.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize

_NEIGHBOUR_KERNEL = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)


@dataclass
class ClosureParams:
    # Longest gap to bridge, in pixels. Scale with line width, not page size.
    max_gap: float = 12.0
    # Reject a bridge unless one endpoint's outward stroke direction points
    # within this many degrees of the partner. Stops parallel hatching strokes
    # being stitched into a ladder.
    max_angle_deg: float = 75.0
    # Steps walked back along the skeleton to estimate stroke direction.
    tangent_steps: int = 6
    # Morphological closing radius applied before bridging. 0 disables.
    close_radius: int = 0


def close_line_gaps(
    line_mask: np.ndarray, params: ClosureParams | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(closed_mask, bridges)``.

    ``closed_mask`` is the line mask with bridges added, for segmentation to
    consume. ``bridges`` is just the added pixels, kept so the effect is
    inspectable and so nothing synthetic reaches the export.
    """
    params = params or ClosureParams()
    work = line_mask.copy()

    if params.close_radius > 0:
        size = 2 * params.close_radius + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        work = cv2.morphologyEx(work.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)

    bridges = _bridge_endpoints(work, params)
    return work | bridges, bridges


def find_endpoints(line_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Skeleton stroke ends. Returns ``(skeleton, endpoint_coords[N, 2])`` as (y, x)."""
    skeleton = skeletonize(line_mask)
    counts = ndimage.convolve(
        skeleton.astype(np.uint8), _NEIGHBOUR_KERNEL, mode="constant", cval=0
    )
    endpoints = skeleton & (counts == 1)
    ys, xs = np.nonzero(endpoints)
    return skeleton, np.stack([ys, xs], axis=1)


def _bridge_endpoints(line_mask: np.ndarray, params: ClosureParams) -> np.ndarray:
    skeleton, points = find_endpoints(line_mask)
    # uint8 rather than bool so cv2.line can draw into it directly.
    bridges = np.zeros(line_mask.shape, dtype=np.uint8)
    if len(points) < 2:
        return bridges.astype(bool)

    directions = np.stack(
        [_tangent(skeleton, tuple(p), params.tangent_steps) for p in points]
    )

    from scipy.spatial import cKDTree

    tree = cKDTree(points)
    pairs = tree.query_pairs(params.max_gap, output_type="ndarray")
    if len(pairs) == 0:
        return bridges.astype(bool)

    deltas = points[pairs[:, 1]] - points[pairs[:, 0]]
    distances = np.linalg.norm(deltas, axis=1)
    keep = distances > 0
    pairs, deltas, distances = pairs[keep], deltas[keep], distances[keep]
    if len(pairs) == 0:
        return bridges.astype(bool)

    unit = deltas / distances[:, None]
    cos_limit = np.cos(np.radians(params.max_angle_deg))
    # Each endpoint's outward direction should point toward its partner.
    facing_a = np.einsum("ij,ij->i", directions[pairs[:, 0]], unit)
    facing_b = np.einsum("ij,ij->i", directions[pairs[:, 1]], -unit)
    aligned = (facing_a > cos_limit) & (facing_b > cos_limit)

    pairs, distances = pairs[aligned], distances[aligned]
    if len(pairs) == 0:
        return bridges.astype(bool)

    # Greedy shortest-first, one bridge per endpoint.
    order = np.argsort(distances)
    used: set[int] = set()
    for index in order:
        a, b = int(pairs[index][0]), int(pairs[index][1])
        if a in used or b in used:
            continue
        y0, x0 = points[a]
        y1, x1 = points[b]
        cv2.line(bridges, (int(x0), int(y0)), (int(x1), int(y1)), 1, 1)
        used.add(a)
        used.add(b)

    return bridges.astype(bool)


def _tangent(skeleton: np.ndarray, point: tuple[int, int], steps: int) -> np.ndarray:
    """Outward unit direction of the stroke at an endpoint.

    Walks back along the skeleton and returns the vector from the far pixel to
    the endpoint, i.e. the direction the stroke was heading when it stopped.
    """
    y, x = point
    height, width = skeleton.shape
    visited = {(y, x)}
    frontier = [(y, x)]
    far = (y, x)

    for _ in range(steps):
        nxt = []
        for cy, cx in frontier:
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = cy + dy, cx + dx
                    if not (0 <= ny < height and 0 <= nx < width):
                        continue
                    if not skeleton[ny, nx] or (ny, nx) in visited:
                        continue
                    visited.add((ny, nx))
                    nxt.append((ny, nx))
        if not nxt:
            break
        frontier = nxt
        far = frontier[0]

    vector = np.array([y - far[0], x - far[1]], dtype=np.float64)
    norm = np.linalg.norm(vector)
    if norm == 0:
        return np.zeros(2)
    return vector / norm

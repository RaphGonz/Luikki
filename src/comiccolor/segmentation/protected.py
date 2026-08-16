"""§1.2 Protected masks: frame as protection, not detection.

D-20: `ProtectedMask` is stored **page-scoped**, not panel-scoped, so a
speech bubble straddling two panels stays one object — reshape and delete
do the obvious thing. Clipping a page-space polygon down to one panel's
local coordinate frame happens only at the moment of use (segmentation),
never as a second persisted copy. This module is that one clip function.

D-21: protection means "never coloured", not "content preserved". The
export is colour patches only; a protected area simply never receives a
palette entry, so no patch is ever emitted there. That makes PROT-04 a flat
property — no emitted colour patch overlaps a protected mask — not an
integrity invariant threaded through the pipeline the way `masks.py`'s
`assert_invariant` is for label-map exhaustiveness. There is deliberately
no fail-loud assertion chain built on top of this module.
"""

from __future__ import annotations

import cv2
import numpy as np


def rasterize_protected_for_panel(
    polygons: list[list[tuple[int, int]]],
    panel_x: int,
    panel_y: int,
    panel_w: int,
    panel_h: int,
) -> np.ndarray:
    """Clip page-space protected polygons into one panel's local frame.

    Returns a boolean array of shape ``(panel_h, panel_w)``, True where a
    polygon covers that pixel. Polygons with fewer than 3 vertices are
    skipped rather than raising -- degenerate input should not fail a whole
    segmentation pass over one bad shape.

    `cv2.fillPoly` already clips to the destination array's bounds, so a
    polygon that only partially overlaps the panel -- or lies entirely
    outside it -- needs no manual intersection arithmetic here. That is
    also what makes a polygon straddling two panels work correctly when
    this function is called once per panel with the same page-space
    vertices: each call clips independently, and nothing is lost or
    double-counted so long as the caller unions in page space, not here.
    """
    out = np.zeros((panel_h, panel_w), dtype=np.uint8)

    for polygon in polygons:
        if len(polygon) < 3:
            continue
        local = np.array(
            [(x - panel_x, y - panel_y) for x, y in polygon], dtype=np.int32
        )
        cv2.fillPoly(out, [local], 1)

    return out.astype(bool)


def protected_bbox_and_area(
    polygon: list[tuple[int, int]], page_w: int, page_h: int
) -> tuple[int, tuple[int, int, int, int]]:
    """Area and bounding box of one page-space polygon, computed once.

    The store needs both values on write (`ProtectedMask.area`,
    `ProtectedMask.bbox`), and there must be exactly one definition of them
    -- this rasterises the polygon into a page-sized array rather than
    letting the store and this module compute it two different ways.
    """
    if len(polygon) < 3:
        return 0, (0, 0, 0, 0)

    page = np.zeros((page_h, page_w), dtype=np.uint8)
    local = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(page, [local], 1)

    ys, xs = np.nonzero(page)
    if ys.size == 0:
        return 0, (0, 0, 0, 0)

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    area = int(ys.size)
    bbox = (x0, y0, x1 - x0 + 1, y1 - y0 + 1)
    return area, bbox

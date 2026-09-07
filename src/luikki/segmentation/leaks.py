"""§1.3 again, from the other end: find the leaks instead of closing the gaps.

Gap closure tries to repair the line before segmenting. Measured on
`diagonal_page` against the artist's own corrected map, that does not work: of
46 leaks only 22 close at *any* trapped-ball radius up to 12, and
straight-segment endpoint bridging moves the count from 48 to 44 while adding
fragmentation at every setting (`reports/new_algo/REPORT.md`).

So this module leaves the line alone and audits the result instead. A ball
smaller than the shipped segmenter's proposes where a zone *could* be split, and
each proposal is judged on what lies under the border it would draw:

- a **leak** is a line with a hole in it. Nearly all of the proposed border sits
  on ink; only the hole is open. The ball was simply too big to fit through.
- a **tunnel** is a legitimate passage that narrowed until the fill stopped and
  started a new zone. Its border is open along its whole length, because there
  was never a line there.

``max_open_share`` is where one becomes the other. Splits are only ever *added*
to what the segmenter returned — a zone may be divided, never re-drawn — so this
step cannot invent a leak, only fail to catch one.

Leak area 10.7% -> 6.5% of the page on `diagonal_page`, for 13.8% -> 15.6%
fragmentation. That direction is deliberate: a leak is silent and costs a cut
stroke, an extra zone is visible and costs one sweep.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass

import cv2
import numpy as np

from ..model.masks import UNASSIGNED
from .trappedball import SegmentationParams, expand_under_lines, trapped_ball_segment


@dataclass
class LeakParams:
    """Style-sensitive, like every other threshold in §1.4."""

    # Radii for the audit pass. Larger than what the shipped segmenter commits
    # to, because the point is to see the splits it could not.
    radii: tuple[int, ...] = (4, 3, 2, 1)
    # Accept a split only if at most this share of the border it would draw is
    # open paper. Above it the border is a tunnel, not a line with a hole.
    max_open_share: float = 0.14
    # Ignore proposals that would carve off less than this. Below it the split
    # is anti-aliasing, and the artist would merge it straight back.
    min_piece: int = 150
    # Borders shorter than this carry no evidence either way.
    min_border: int = 6


def split_open_borders(
    labels: np.ndarray,
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
    params: LeakParams | None = None,
) -> np.ndarray:
    """Divide zones that a line with a hole in it should have kept apart.

    ``labels`` is any segmenter's output, ``line_mask`` the raster it was cut
    from. Returns a label map on the same support: every pixel keeps its zone or
    takes a new one carved out of it, and no pixel changes zone otherwise.
    """
    params = params or LeakParams()
    if labels.max() < 1:
        return labels

    audit = trapped_ball_segment(
        line_mask,
        protected=protected,
        params=SegmentationParams(radii=params.radii),
    )

    # Borders are measured after expansion, where two zones separated by a
    # stroke meet along its centre instead of stopping at its two edges. That is
    # what makes "how much of this border is ink" answerable at all.
    coarse = expand_under_lines(labels, line_mask, protected=protected)
    fine = expand_under_lines(audit, line_mask, protected=protected)

    pieces = _overlay(coarse, fine)
    owner = _majority(pieces, coarse)
    kept = _undo_tunnels(pieces, line_mask, owner, params)

    out = kept[pieces]
    out[labels == UNASSIGNED] = UNASSIGNED
    return out


def _overlay(coarse: np.ndarray, fine: np.ndarray) -> np.ndarray:
    """Connected components of the two partitions laid over each other."""
    outside = (coarse == UNASSIGNED) | (fine == UNASSIGNED)
    stride = int(fine.max()) + 1
    pairs = coarse.astype(np.int64) * stride + fine

    count, connected = cv2.connectedComponents((~outside).astype(np.uint8), 4)
    pairs = np.where(outside, -1, pairs * (count + 1) + connected)

    # +1 because label 0 is reserved. Without it, a page with nothing outside
    # has its first real piece silently renumbered to UNASSIGNED.
    _, inverse = np.unique(pairs, return_inverse=True)
    pieces = (inverse.reshape(coarse.shape) + 1).astype(np.int32)
    pieces[outside] = UNASSIGNED
    return pieces


def _majority(pieces: np.ndarray, coarse: np.ndarray) -> np.ndarray:
    """The zone each piece came out of, indexed by piece label."""
    size = int(pieces.max()) + 1
    order = np.argsort(pieces.ravel(), kind="stable")
    sorted_pieces = pieces.ravel()[order]
    sorted_zones = coarse.ravel()[order]

    bounds = np.searchsorted(sorted_pieces, np.arange(size + 1))
    owner = np.zeros(size, dtype=np.int64)
    for piece in range(1, size):
        span = sorted_zones[bounds[piece] : bounds[piece + 1]]
        if span.size:
            owner[piece] = int(np.bincount(span).argmax())
    return owner


def _border_stats(pieces: np.ndarray, ink: np.ndarray) -> dict:
    """``{(a, b): [border length, of which ink]}`` over 4-neighbour contacts."""
    size = int(pieces.max()) + 1
    stats: dict = defaultdict(lambda: [0, 0])

    sides = (
        (pieces[:, :-1], pieces[:, 1:], ink[:, :-1], ink[:, 1:]),
        (pieces[:-1, :], pieces[1:, :], ink[:-1, :], ink[1:, :]),
    )
    for left, right, ink_left, ink_right in sides:
        touching = (left != right) & (left > 0) & (right > 0)
        if not touching.any():
            continue
        a, b = left[touching], right[touching]
        inked = ink_left[touching] | ink_right[touching]
        key = np.minimum(a, b).astype(np.int64) * size + np.maximum(a, b)
        unique, inverse = np.unique(key, return_inverse=True)
        total = np.bincount(inverse)
        on_ink = np.bincount(inverse, weights=inked.astype(np.float64))
        for packed, length, drawn in zip(unique, total, on_ink):
            entry = stats[(int(packed // size), int(packed % size))]
            entry[0] += int(length)
            entry[1] += int(drawn)
    return stats


def _undo_tunnels(
    pieces: np.ndarray, ink: np.ndarray, owner: np.ndarray, params: LeakParams
) -> np.ndarray:
    """Put every proposed split back except the ones that look like a leak.

    Openest border first, and the border is recomputed after every join: a chain
    of individually reasonable joins otherwise adds up to a leak, which is
    exactly the failure this module exists to prevent.
    """
    stats = _border_stats(pieces, ink)
    size = int(pieces.max()) + 1
    area = np.bincount(pieces.ravel(), minlength=size)

    neighbours: dict = defaultdict(dict)
    for (a, b), entry in stats.items():
        neighbours[a][b] = entry
        neighbours[b][a] = entry

    parent = list(range(size))

    def find(piece: int) -> int:
        while parent[piece] != piece:
            parent[piece] = parent[parent[piece]]
            piece = parent[piece]
        return piece

    def open_share(entry: list[int]) -> float:
        return (entry[0] - entry[1]) / entry[0]

    def is_tunnel(a: int, b: int) -> bool:
        if owner[a] != owner[b]:
            return False  # never join what the segmenter separated
        entry = neighbours[a][b]
        if entry[0] < params.min_border:
            return True
        if area[a] < params.min_piece or area[b] < params.min_piece:
            return True
        return open_share(entry) > params.max_open_share

    heap = [(-open_share(entry), a, b) for (a, b), entry in stats.items()]
    heapq.heapify(heap)

    while heap:
        _, a, b = heapq.heappop(heap)
        a, b = find(a), find(b)
        if a == b or b not in neighbours[a] or not is_tunnel(a, b):
            continue

        parent[b] = a
        area[a] += area[b]
        for other, entry in list(neighbours[b].items()):
            other = find(other)
            if other == a:
                continue
            merged = neighbours[a].setdefault(other, [0, 0])
            merged[0] += entry[0]
            merged[1] += entry[1]
            neighbours[other][a] = merged
            neighbours[other].pop(b, None)
            heapq.heappush(heap, (-open_share(merged), a, other))
        neighbours[a].pop(b, None)
        neighbours.pop(b, None)

    roots = np.array([find(piece) for piece in range(size)], dtype=np.int32)
    roots[UNASSIGNED] = UNASSIGNED
    return roots

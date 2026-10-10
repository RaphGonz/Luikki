"""§G3 Fake flat colours: eight entries, and no two touching zones alike.

Luikki proposes no colour (ROADMAP G). The flats still need one per zone, so
that a colourist can take a zone with the magic wand (contiguous) the way they
take one on flats made by hand — and that only works if a zone never shares
its colour with a zone it touches. So the colours are a graph colouring of the
zones' adjacency, over a short series of well-separated colours: the
professional replaces them anyway.

The eight colours are palette entries, ids 1 to 8. A zone stores an id and
never an RGB (rule 1): `palette_entry_id` stays what it was.
"""

from __future__ import annotations

import numpy as np

from ..model.entities import PaletteEntry
from ..model.masks import UNASSIGNED

# Okabe and Ito's eight, black swapped for a pale pink: far apart from each
# other for every kind of colour vision, and none of them ink.
FLAT_RGB = (
    (230, 159, 0),
    (86, 180, 233),
    (0, 158, 115),
    (240, 228, 66),
    (0, 114, 178),
    (213, 94, 0),
    (204, 121, 167),
    (255, 190, 200),
)

FLAT_PALETTE = [
    PaletteEntry(project_id=0, rgb=rgb, label=f"Flat {index}", id=index)
    for index, rgb in enumerate(FLAT_RGB, start=1)
]


def adjacency(page: np.ndarray) -> np.ndarray:
    """Every pair of zones that touch, in 8-connectivity, as (a, b) with a < b.

    Eight, not four: two zones meeting at a corner are one region to a magic
    wand that is set to diagonal neighbours, and Photoshop's is.
    """
    pairs = []
    for a, b in (
        (page[:, :-1], page[:, 1:]),
        (page[:-1, :], page[1:, :]),
        (page[:-1, :-1], page[1:, 1:]),
        (page[:-1, 1:], page[1:, :-1]),
    ):
        # Where the label changes first, then the zero test on those few: the
        # same pairs, with one whole-page comparison instead of three.
        differ = a != b
        left, right = a[differ], b[differ]
        touching = (left != UNASSIGNED) & (right != UNASSIGNED)
        left, right = left[touching].astype(np.int64), right[touching].astype(np.int64)
        low, high = np.minimum(left, right), np.maximum(left, right)
        pairs.append(np.unique(low << 32 | high))
    if not pairs:
        return np.zeros((0, 2), np.int64)
    joined = np.unique(np.concatenate(pairs))
    return np.stack([joined >> 32, joined & 0xFFFFFFFF], axis=1)


def colour_graph(nodes: list[int], edges: np.ndarray, colours: int = len(FLAT_RGB)) -> dict[int, int]:
    """Greedy colouring, in the order of `nodes`: each takes, of the colours
    none of its coloured neighbours holds, the one the page has used least so
    far — so the eight are spread over the page rather than two doing all the
    work, which read as a chequerboard.

    In node order rather than by degree, so an edit to one corner of the page
    leaves the colours of the zones before it where they were. A drawn page is
    close to planar and four colours nearly always suffice; should a zone see
    all eight around it, it takes the one its neighbours use least.
    """
    neighbours: dict[int, list[int]] = {node: [] for node in nodes}
    for a, b in edges.tolist():
        if a in neighbours and b in neighbours:
            neighbours[a].append(b)
            neighbours[b].append(a)
    chosen: dict[int, int] = {}
    total = np.zeros(colours, np.int64)
    for node in nodes:
        used = np.bincount(
            [chosen[other] for other in neighbours[node] if other in chosen], minlength=colours
        )
        free = np.flatnonzero(used == 0)
        colour = int(free[total[free].argmin()]) if free.size else int(used.argmin())
        chosen[node] = colour
        total[colour] += 1
    return chosen


def assign_flat_colours(
    page_size: tuple[int, int], panels: list[tuple[int, int, np.ndarray]]
) -> list[dict[int, int]]:
    """`zone -> palette entry id` for each panel, over the whole page.

    `panels` is `(x, y, label_map)` per panel. Coloured on the page rather than
    panel by panel: two panels sharing a frame line have zones that meet under
    it, and a magic wand does not stop at a panel's edge.
    """
    width, height = page_size
    page = np.zeros((height, width), np.int32)
    offsets = []
    offset = 0
    for x, y, labels in panels:
        rows = min(labels.shape[0], height - y)
        cols = min(labels.shape[1], width - x)
        patch = labels[:rows, :cols].astype(np.int32)
        window = page[y : y + rows, x : x + cols]
        inside = patch != UNASSIGNED
        np.copyto(window, patch + offset, where=inside)
        offsets.append(offset)
        offset += int(labels.max()) + 1 if labels.size else 1

    # The labels each panel holds, in order: what `np.unique` gave, without
    # sorting the whole map.
    held = [np.flatnonzero(np.bincount(labels.ravel())) for _, _, labels in panels]
    nodes = []
    for present, base in zip(held, offsets):
        nodes += [int(label) + base for label in present if label != UNASSIGNED]
    chosen = colour_graph(nodes, adjacency(page))

    result = []
    for present, base in zip(held, offsets):
        result.append(
            {
                int(label): FLAT_PALETTE[chosen[int(label) + base]].id
                for label in present
                if label != UNASSIGNED
            }
        )
    return result

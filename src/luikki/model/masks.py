"""Label-map storage and the exclusivity/exhaustiveness invariant.

A panel's regions live in one ``int32`` array the size of the panel. Label 0 is
reserved for "not a region" — line pixels and protected areas. Every other
label is exactly one Region.

Storing it this way rather than as N boolean masks is what makes §3's
"mutually exclusive and exhaustive" an invariant of the representation instead
of a property that has to be re-verified after every edit. Merge is a relabel,
split is a relabel, and neither can produce an overlap.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Label reserved for line pixels, protected masks, and page background.
UNASSIGNED = 0


def save_label_map(path: str | Path, label_map: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if label_map.dtype != np.int32:
        label_map = label_map.astype(np.int32)
    np.savez_compressed(path, labels=label_map)


def load_label_map(path: str | Path) -> np.ndarray:
    with np.load(Path(path)) as data:
        return data["labels"]


def save_binary_mask(path: str | Path, mask: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, mask=mask.astype(bool))


def load_binary_mask(path: str | Path) -> np.ndarray:
    with np.load(Path(path)) as data:
        return data["mask"]


def region_stats(label_map: np.ndarray) -> dict[int, tuple[int, tuple[int, int, int, int]]]:
    """Area and bounding box per label, excluding UNASSIGNED.

    Returns ``{label: (area, (x, y, w, h))}``.
    """
    flat = label_map.ravel()
    max_label = int(flat.max()) if flat.size else 0
    if max_label < 1:
        return {}

    counts = np.bincount(flat, minlength=max_label + 1)

    # Bounding boxes via per-label min/max over coordinates, vectorised.
    ys, xs = np.nonzero(label_map)
    labels_at = label_map[ys, xs]
    big = max_label + 1
    min_x = np.full(big, label_map.shape[1], dtype=np.int64)
    max_x = np.full(big, -1, dtype=np.int64)
    min_y = np.full(big, label_map.shape[0], dtype=np.int64)
    max_y = np.full(big, -1, dtype=np.int64)
    np.minimum.at(min_x, labels_at, xs)
    np.maximum.at(max_x, labels_at, xs)
    np.minimum.at(min_y, labels_at, ys)
    np.maximum.at(max_y, labels_at, ys)

    out: dict[int, tuple[int, tuple[int, int, int, int]]] = {}
    for label in range(1, max_label + 1):
        area = int(counts[label])
        if area == 0:
            continue
        x0, y0 = int(min_x[label]), int(min_y[label])
        bbox = (x0, y0, int(max_x[label]) - x0 + 1, int(max_y[label]) - y0 + 1)
        out[label] = (area, bbox)
    return out


def region_count(label_map: np.ndarray) -> int:
    """Number of distinct regions. The P3 health metric (§1.4, §5)."""
    return int(np.count_nonzero(np.bincount(label_map.ravel())[1:]))


def regions_to_cover(label_map: np.ndarray, fraction: float = 0.9) -> int:
    """How many of the largest regions it takes to cover ``fraction`` of area.

    A raw region count cannot tell "this panel has 900 things in it" apart from
    "this panel has 30 things in it and 870 hatching slivers". This can: on
    hatched art the largest handful of regions account for nearly all the area
    while the count runs into the hundreds.

    The gap between this and the total count is the size of the problem §7's
    hatching adapter has to solve.
    """
    stats = region_stats(label_map)
    if not stats:
        return 0
    areas = np.sort(np.array([area for area, _ in stats.values()]))[::-1]
    target = areas.sum() * fraction
    return int(np.searchsorted(np.cumsum(areas), target) + 1)


def check_coverage(
    label_map: np.ndarray,
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
) -> dict[str, int | float | bool]:
    """Verify §3's exhaustiveness invariant.

    Every fillable pixel — not line, not protected — must carry a non-zero
    label. Exclusivity needs no check: the representation cannot express an
    overlap.

    ``line_mask`` and ``protected`` are boolean, True where the pixel is a line
    or protected respectively.
    """
    fillable = ~line_mask
    if protected is not None:
        fillable = fillable & ~protected

    assigned = label_map != UNASSIGNED
    uncovered = int(np.count_nonzero(fillable & ~assigned))
    # Labels that landed on a line or protected pixel: a leak, not a gap.
    leaked = int(np.count_nonzero(assigned & ~fillable))
    total_fillable = int(np.count_nonzero(fillable))

    return {
        "fillable_pixels": total_fillable,
        "uncovered_pixels": uncovered,
        "leaked_pixels": leaked,
        "coverage": (total_fillable - uncovered) / total_fillable if total_fillable else 1.0,
        "exhaustive": uncovered == 0,
    }


def relabel_sequential(label_map: np.ndarray) -> np.ndarray:
    """Compact labels to 1..N, preserving UNASSIGNED as 0."""
    unique = np.unique(label_map)
    unique = unique[unique != UNASSIGNED]
    lookup = np.zeros(int(label_map.max()) + 1, dtype=np.int32)
    lookup[unique] = np.arange(1, len(unique) + 1, dtype=np.int32)
    return lookup[label_map]


class LabelMapInvariantError(Exception):
    """Raised when a label map violates §3 exhaustiveness.

    Exclusivity is structural and cannot be violated by construction — a
    pixel holds exactly one label, so there is no state to check for overlap
    (see module docstring). Exhaustiveness has no such guarantee: a merge,
    split, gap-absorb or undo step can leave a fillable pixel with no label,
    or leak a label onto a line/protected pixel. This exception is how that
    failure surfaces.
    """


def assert_invariant(
    label_map: np.ndarray,
    line_mask: np.ndarray,
    protected: np.ndarray | None = None,
) -> None:
    """Verify §3's exhaustiveness invariant, loudly.

    Delegates to ``check_coverage`` rather than reimplementing it, and raises
    ``LabelMapInvariantError`` when the report says the map is not
    exhaustive, or when any label has leaked onto a line/protected pixel — a
    leak is a correctness bug the same way a gap is, even though
    ``check_coverage`` still reports ``exhaustive: True`` for it (a leak
    covers a pixel that should have been left at 0, it does not leave a
    fillable pixel uncovered).

    ``check_coverage`` is for reporting and metrics: a caller reads the
    report and decides what to do with it. ``assert_invariant`` is for
    edit-time enforcement — Phase 3's zone editor calls it after every merge,
    split, gap-absorb and undo transition, where the only correct response to
    a violation is to fail loudly rather than let a broken label map persist.

    ``line_mask`` and ``protected`` are boolean, True where the pixel is a
    line or protected respectively — the same convention ``check_coverage``
    uses.
    """
    report = check_coverage(label_map, line_mask, protected)
    if not report["exhaustive"]:
        raise LabelMapInvariantError(
            f"{report['uncovered_pixels']} fillable pixels have no region "
            f"(coverage={report['coverage']:.4f})"
        )
    if report["leaked_pixels"]:
        raise LabelMapInvariantError(
            f"{report['leaked_pixels']} pixels carry a label but sit on a "
            f"line or protected pixel (coverage={report['coverage']:.4f})"
        )

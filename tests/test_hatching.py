"""Regression tests for strip fragmentation.

A corridor between two parallel lines is ONE region. A ball too wide to fit
inside it finds cores only where it happens to widen, and each of those becomes
a separate region — so one hatching strip shatters into dozens. These pin that
behaviour with synthetic art whose region count is known exactly.
"""

import numpy as np
import pytest

from comiccolor.model.masks import region_count
from comiccolor.segmentation.trappedball import (
    SegmentationParams,
    adaptive_radii,
    measure_passage_width,
    trapped_ball_segment,
)


def parallel_lines(count: int, pitch: int, wobble: float = 0.0, size=(200, 300)):
    """Full-width horizontal lines, so every strip is genuinely isolated."""
    page = np.zeros(size, dtype=bool)
    for i in range(count):
        base = 15 + i * pitch
        for x in range(size[1]):
            y = base + int(round(wobble * np.sin(x / 15.0 + i * 1.3)))
            if 0 <= y < size[0]:
                page[y, x] = True
    return page


DENSE = pytest.mark.xfail(
    reason=(
        "Our hand-rolled trapped-ball still shatters dense hatching; the "
        "adaptive radius estimate is not tight enough. Not being tuned — this "
        "is the acceptance bar for swapping in hepesu/LineFiller, which ships "
        "the merge/grouping step this implementation lacks."
    ),
    strict=False,
)


@pytest.mark.parametrize(
    "count,pitch,wobble",
    [
        (8, 20, 0.0),                       # clean, widely spaced
        (8, 20, 4.0),                       # hand-drawn wobble
        pytest.param(18, 9, 2.0, marks=DENSE),  # dense hatching
        pytest.param(24, 7, 1.0, marks=DENSE),  # denser still
    ],
)
def test_each_strip_is_one_region(count, pitch, wobble):
    """A corridor between two parallel lines is ONE region. Ground truth."""
    page = parallel_lines(count, pitch, wobble)
    expected = count + 1  # strips between lines, plus the surrounding area

    labels = trapped_ball_segment(page, params=SegmentationParams(min_area=1))

    assert region_count(labels) == expected


def test_oversized_radius_shatters_strips():
    """The bug itself, pinned: 19 true regions reported as hundreds."""
    page = parallel_lines(18, 9, 2.0)

    oversized = trapped_ball_segment(
        page, params=SegmentationParams(radii=(5, 4, 3, 2, 1), min_area=1)
    )
    narrow = trapped_ball_segment(
        page, params=SegmentationParams(radii=(2, 1), min_area=1)
    )

    assert region_count(oversized) > 100, "the shattering failure mode"
    assert region_count(narrow) == 19, "a ball that fits recovers ground truth"


def test_passage_width_tracks_line_spacing():
    narrow = measure_passage_width(~parallel_lines(24, 7, 0.0))
    wide = measure_passage_width(~parallel_lines(8, 20, 0.0))
    assert narrow < wide


def test_adaptive_radii_shrink_on_dense_art():
    dense = adaptive_radii(~parallel_lines(24, 7, 0.0))
    sparse = adaptive_radii(~parallel_lines(8, 20, 0.0))
    assert max(dense) <= max(sparse)
    assert min(dense) == 1, "the schedule must always bottom out at a plain fill"


def test_gap_closure_still_works_on_art_that_allows_it():
    """The adaptive cap must not silently disable §1.3 on ordinary art."""
    line = np.zeros((120, 120), dtype=bool)
    line[30, 30:90] = True
    line[89, 30:90] = True
    line[30:90, 30] = True
    line[30:90, 89] = True
    line[30, 55:58] = False  # 3px gap

    labels = trapped_ball_segment(line, params=SegmentationParams(min_area=4))
    assert labels[60, 60] != labels[5, 5], "ball leaked through a 3px gap"

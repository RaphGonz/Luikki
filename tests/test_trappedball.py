import numpy as np

from comiccolor.model.masks import check_coverage, region_count, region_stats
from comiccolor.segmentation.trappedball import (
    SegmentationParams,
    expand_under_lines,
    trapped_ball_segment,
)


def _box_page(gap: int = 0) -> np.ndarray:
    """A 120x120 page with one closed box, optionally with a gap in its wall."""
    line = np.zeros((120, 120), dtype=bool)
    line[30, 30:90] = True
    line[89, 30:90] = True
    line[30:90, 30] = True
    line[30:90, 89] = True
    if gap:
        start = 55
        line[30, start : start + gap] = False
    return line


def test_closed_box_gives_inside_and_outside():
    labels = trapped_ball_segment(_box_page(), params=SegmentationParams(min_area=4))
    assert region_count(labels) == 2
    assert labels[60, 60] != labels[5, 5]


def test_small_gap_does_not_leak():
    """A ball wider than the gap cannot escape. This is §1.3 gap closure."""
    labels = trapped_ball_segment(
        _box_page(gap=3), params=SegmentationParams(radii=(5, 4, 3), min_area=4)
    )
    assert labels[60, 60] != labels[5, 5], "ball leaked through a 3px gap"


def test_large_gap_does_leak_as_expected():
    """Stated honestly: a gap wider than 2r is not closed by this mechanism."""
    labels = trapped_ball_segment(
        _box_page(gap=25), params=SegmentationParams(radii=(3, 2, 1), min_area=4)
    )
    assert labels[60, 60] == labels[5, 5]


def test_output_is_exhaustive_over_fillable_area():
    line = _box_page()
    labels = trapped_ball_segment(line, params=SegmentationParams(min_area=4))
    report = check_coverage(labels, line)
    assert report["exhaustive"], report


def test_no_label_lands_on_a_line_pixel():
    line = _box_page()
    labels = trapped_ball_segment(line, params=SegmentationParams(min_area=4))
    assert not labels[line].any()


def test_protected_area_is_never_filled():
    line = _box_page()
    protected = np.zeros_like(line)
    protected[40:60, 40:60] = True
    labels = trapped_ball_segment(line, protected=protected, params=SegmentationParams(min_area=4))
    assert not labels[protected].any()


def test_small_regions_are_merged_away():
    line = np.zeros((80, 80), dtype=bool)
    line[40, :] = True
    # A 2x2 speck fenced off in the top half.
    line[10, 10:14] = True
    line[13, 10:14] = True
    line[10:14, 10] = True
    line[10:14, 13] = True

    unmerged = trapped_ball_segment(line, params=SegmentationParams(min_area=1, radii=(1,)))
    merged = trapped_ball_segment(line, params=SegmentationParams(min_area=64, radii=(1,)))
    assert region_count(merged) < region_count(unmerged)


def test_expand_under_lines_covers_ink_but_not_protected():
    line = _box_page()
    protected = np.zeros_like(line)
    protected[95:110, 95:110] = True

    labels = trapped_ball_segment(line, protected=protected, params=SegmentationParams(min_area=4))
    expanded = expand_under_lines(labels, line)

    assert expanded[line].all(), "ink pixels should take a neighbouring label"
    assert not expanded[protected].any(), "protected pixels must stay unpainted"
    # Region identities are preserved, only extended.
    assert region_count(expanded) == region_count(labels)


def test_labels_are_positive_and_stats_agree_with_pixels():
    labels = trapped_ball_segment(_box_page(), params=SegmentationParams(min_area=4))
    stats = region_stats(labels)
    assert all(label > 0 for label in stats)
    assert sum(area for area, _ in stats.values()) == int(np.count_nonzero(labels))

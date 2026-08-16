import cv2
import numpy as np

from comiccolor.model.masks import check_coverage, region_count, region_stats
from comiccolor.segmentation.protected import rasterize_protected_for_panel
from comiccolor.segmentation.trappedball import (
    SegmentationParams,
    expand_under_lines,
    trapped_ball_segment,
)
from tests.conftest import boundary_crossing_page


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


def test_protected_pixels_stay_unassigned_across_a_panel_boundary():
    """PROT-04 / success criterion 4, unit-level half.

    A page-scoped bubble (D-20) that straddles the gutter between two panels
    must leave zero protected pixels carrying a non-zero label in EITHER
    panel's own segmentation, before and after `expand_under_lines` -- the
    step most likely to leak a label into a protected area. The manual
    end-to-end UAT pass on a real page with real ink is the other half,
    recorded in 02-VALIDATION.md's Manual-Only table.
    """
    _, line_mask, panel_boxes = boundary_crossing_page()
    height, _ = line_mask.shape
    gutter = 30
    panel1_x, panel_y, panel_w, _ = panel_boxes[0]

    # The bubble's page-space polygon, derived from boundary_crossing_page's
    # own known geometry (same centre/axes it drew its ellipse outline with).
    gutter_mid_x = panel1_x + panel_w + gutter // 2
    centre = (gutter_mid_x, height // 2)
    axes = (gutter + 20, 40)
    polygon = [(int(x), int(y)) for x, y in cv2.ellipse2Poly(centre, axes, 0, 0, 360, 5)]

    for panel_x, panel_y, panel_w, panel_h in panel_boxes:
        panel_line = line_mask[panel_y : panel_y + panel_h, panel_x : panel_x + panel_w]
        panel_protected = rasterize_protected_for_panel(
            [polygon], panel_x, panel_y, panel_w, panel_h
        )

        # Assert non-vacuity first: the clip must actually land something.
        assert panel_protected.any(), "bubble should reach this panel's interior"

        labels = trapped_ball_segment(
            panel_line, protected=panel_protected, params=SegmentationParams(min_area=4)
        )
        assert not labels[panel_protected].any()

        expanded = expand_under_lines(labels, panel_line, protected=panel_protected)
        assert not expanded[panel_protected].any()

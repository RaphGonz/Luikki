import cv2
import numpy as np

from comiccolor.segmentation.protected import (
    protected_bbox_and_area,
    rasterize_protected_for_panel,
)
from tests.conftest import boundary_crossing_page


def _ellipse_polygon(
    centre: tuple[int, int], axes: tuple[int, int], angle: int = 0, delta: int = 5
) -> list[tuple[int, int]]:
    pts = cv2.ellipse2Poly(centre, axes, angle, 0, 360, delta)
    return [(int(x), int(y)) for x, y in pts]


def test_polygon_fully_inside_panel_rasterises_at_local_offset():
    panel_x, panel_y, panel_w, panel_h = 50, 50, 100, 80
    polygon = [(60, 60), (120, 60), (120, 110), (60, 110)]

    out = rasterize_protected_for_panel([polygon], panel_x, panel_y, panel_w, panel_h)

    assert out.dtype == bool
    assert out.shape == (panel_h, panel_w)
    # (60, 60) in page space is (10, 10) in panel-local space.
    assert out[10, 10]
    assert not out[0, 0]


def test_polygon_fully_outside_panel_is_all_false():
    polygon = [(1000, 1000), (1010, 1000), (1010, 1010), (1000, 1010)]

    out = rasterize_protected_for_panel([polygon], 0, 0, 50, 50)

    assert out.shape == (50, 50)
    assert out.dtype == bool
    assert not out.any()


def test_empty_polygon_list_returns_all_false():
    out = rasterize_protected_for_panel([], 0, 0, 40, 30)

    assert out.shape == (30, 40)
    assert out.dtype == bool
    assert not out.any()


def test_degenerate_polygon_is_skipped_not_raised():
    # Two vertices: not a polygon. Must be skipped, never raise.
    out = rasterize_protected_for_panel([[(1, 1), (2, 2)]], 0, 0, 10, 10)

    assert out.shape == (10, 10)
    assert not out.any()


def test_straddling_polygon_union_equals_page_space_intersection():
    """cv2.fillPoly clips to the destination array's bounds -- no manual
    intersection arithmetic is needed for a polygon spanning two panels."""
    panel1 = (50, 50, 100, 200)
    panel2 = (150, 50, 100, 200)
    polygon = [(80, 100), (220, 100), (220, 160), (80, 160)]  # straddles x=150

    r1 = rasterize_protected_for_panel([polygon], *panel1)
    r2 = rasterize_protected_for_panel([polygon], *panel2)

    page = np.zeros((300, 300), dtype=np.uint8)
    cv2.fillPoly(page, [np.array(polygon, dtype=np.int32)], 1)
    page_bool = page.astype(bool)

    px1, py1, pw1, ph1 = panel1
    px2, py2, pw2, ph2 = panel2
    ref1 = page_bool[py1 : py1 + ph1, px1 : px1 + pw1]
    ref2 = page_bool[py2 : py2 + ph2, px2 : px2 + pw2]

    assert np.array_equal(r1, ref1)
    assert np.array_equal(r2, ref2)
    assert r1.any() and r2.any()


def test_boundary_crossing_polygon_lands_in_both_panels():
    """PROT-04 / success criterion 4: a page-scoped bubble spanning two
    panels rasterises into non-empty True regions in BOTH local frames."""
    _, line_mask, panel_boxes = boundary_crossing_page()
    height, _ = line_mask.shape
    gutter = 30
    panel1_x, panel_y, panel_w, _ = panel_boxes[0]

    gutter_mid_x = panel1_x + panel_w + gutter // 2
    centre = (gutter_mid_x, height // 2)
    axes = (gutter + 20, 40)
    polygon = _ellipse_polygon(centre, axes)

    r1 = rasterize_protected_for_panel([polygon], *panel_boxes[0])
    r2 = rasterize_protected_for_panel([polygon], *panel_boxes[1])

    assert r1.any(), "bubble should reach panel 1's interior"
    assert r2.any(), "bubble should reach panel 2's interior"


def test_protected_bbox_and_area_matches_page_rasterisation():
    polygon = [(20, 20), (80, 20), (80, 70), (20, 70)]

    area, bbox = protected_bbox_and_area(polygon, page_w=200, page_h=200)

    # cv2.fillPoly fills inclusive of the boundary pixel, so a rectangle
    # with corners at 20 and 80 covers pixel columns 20..80 inclusive (61).
    assert bbox == (20, 20, 61, 51)
    assert area == 61 * 51

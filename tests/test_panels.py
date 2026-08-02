import numpy as np

from comiccolor.segmentation.panels import PanelParams, segment_panels


def _grid_page(rows: int, cols: int, size: int = 300, gutter: int = 30) -> np.ndarray:
    """A page of framed panels separated by empty gutters."""
    height = rows * size + (rows + 1) * gutter
    width = cols * size + (cols + 1) * gutter
    page = np.zeros((height, width), dtype=bool)

    for r in range(rows):
        for c in range(cols):
            y = gutter + r * (size + gutter)
            x = gutter + c * (size + gutter)
            page[y, x : x + size] = True
            page[y + size - 1, x : x + size] = True
            page[y : y + size, x] = True
            page[y : y + size, x + size - 1] = True
            # Some content so the panel is not just a frame.
            page[y + 50 : y + 60, x + 50 : x + 200] = True
    return page


def test_finds_every_panel_in_a_grid():
    boxes = segment_panels(_grid_page(3, 2))
    assert len(boxes) == 6


def test_single_panel_page():
    boxes = segment_panels(_grid_page(1, 1))
    assert len(boxes) == 1


def test_manga_reading_order_is_right_to_left():
    page = _grid_page(1, 2)
    boxes = segment_panels(page, PanelParams(reading="rtl"))
    assert len(boxes) == 2
    assert boxes[0].x > boxes[1].x, "first panel read should be the rightmost"


def test_western_reading_order_is_left_to_right():
    page = _grid_page(1, 2)
    boxes = segment_panels(page, PanelParams(reading="ltr"))
    assert boxes[0].x < boxes[1].x


def test_tiers_are_ordered_top_to_bottom_in_both_traditions():
    page = _grid_page(2, 1)
    for reading in ("rtl", "ltr"):
        boxes = segment_panels(page, PanelParams(reading=reading))  # type: ignore[arg-type]
        assert boxes[0].y < boxes[1].y


def test_full_bleed_page_falls_back_to_one_panel():
    """No gutters anywhere. Documented limit, not a crash."""
    page = np.zeros((400, 400), dtype=bool)
    page[::3, :] = True  # dense texture edge to edge
    boxes = segment_panels(page)
    assert len(boxes) == 1


def test_blank_page_returns_one_panel():
    boxes = segment_panels(np.zeros((200, 200), dtype=bool))
    assert len(boxes) == 1


def test_panels_do_not_overlap():
    boxes = segment_panels(_grid_page(2, 2))
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            overlap_x = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
            overlap_y = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
            assert overlap_x <= 0 or overlap_y <= 0, "panels overlap"

import cv2
import numpy as np

from comiccolor.segmentation.panels import PanelBox, PanelParams, box_to_polygon, segment_panels


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


def test_box_to_polygon_seeds_four_corners_clockwise():
    polygon = box_to_polygon(PanelBox(10, 20, 100, 50))
    assert polygon == [(10, 20), (110, 20), (110, 70), (10, 70)]


def _borderless_silhouette_page(size: int = 300) -> np.ndarray:
    """A solid, no-frame ink blob (circle plus two arms) with low solidity.

    D-18's motivating case: no rectangular frame at all, so the proposed
    panel has to come from the ink silhouette itself, which is irregular
    enough that area / bbox_area lands well under the old 0.55 floor.
    """
    page = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(page, (100, 100), 50, 1, thickness=-1)
    page[90:110, 100:280] = 1  # arm reaching right
    page[100:120, 90:110] = 1  # arm reaching down
    return page.astype(bool)


def test_borderless_silhouette_is_proposed_not_discarded():
    page = _borderless_silhouette_page()
    boxes = segment_panels(page)
    assert len(boxes) >= 1
    box = boxes[0]
    assert not (box.x == 0 and box.y == 0 and box.width == page.shape[1] and box.height == page.shape[0])


def test_default_reading_order_is_left_to_right():
    boxes = segment_panels(_grid_page(1, 2))
    assert boxes[0].x < boxes[1].x, "default reading order should be ltr"


# -- polygons, not boxes ----------------------------------------------------


def _diamond_page(size: int = 600) -> np.ndarray:
    """A page holding one rotated square panel, framed, on white."""
    page = np.zeros((size, size), dtype=np.uint8)
    half = size // 2
    reach = int(size * 0.36)
    corners = np.array(
        [[half, half - reach], [half + reach, half], [half, half + reach], [half - reach, half]]
    )
    cv2.polylines(page, [corners], True, 1, thickness=3)
    return page.astype(bool)


def test_a_rotated_panel_keeps_its_shape():
    """The case no bounding box can express. A diamond's box overlaps every
    neighbour it has; only its outline says which pixels are its own."""
    panels = segment_panels(_diamond_page())
    assert len(panels) == 1

    polygon = panels[0].polygon
    assert 3 <= len(polygon) <= 6, f"a diamond is not {len(polygon)} vertices"

    # A box would cover twice the area a rotated square does.
    traced = cv2.contourArea(np.array(polygon, dtype=np.int32))
    box = panels[0].width * panels[0].height
    assert traced < 0.7 * box


def test_a_rectangular_panel_still_gives_four_corners():
    """The common case must not get more complicated."""
    panels = segment_panels(_grid_page(2, 2))
    for panel in panels:
        assert len(panel.polygon) == 4


def test_artwork_falls_back_to_its_bounding_box():
    """D-17's case, kept. With no frame to seal the gutter network against, a
    borderless panel's blob is the drawing itself, and tracing it would return
    a polygon shaped like the character. Above `max_polygon_vertices` the box
    is used instead."""
    size = 500
    page = np.zeros((size, size), dtype=np.uint8)
    rng = np.random.default_rng(0)
    centre = np.array([size // 2, size // 2])
    points = []
    for i in range(40):
        angle = 2 * np.pi * i / 40
        radius = 120 + rng.integers(-45, 45)
        points.append(centre + [int(radius * np.cos(angle)), int(radius * np.sin(angle))])
    cv2.fillPoly(page, [np.array(points)], 1)

    panels = segment_panels(page.astype(bool))
    assert len(panels) == 1
    assert len(panels[0].polygon) == 4, "a ragged blob must come back as its box"


def test_polygon_and_box_agree():
    """The box must contain the polygon: it is where the crop is taken, and
    the polygon then masks inside it."""
    for page in (_grid_page(2, 2), _diamond_page()):
        for panel in segment_panels(page):
            for x, y in panel.polygon:
                assert panel.x <= x <= panel.x + panel.width
                assert panel.y <= y <= panel.y + panel.height


def test_polygons_are_closed_without_repeating_the_first_point():
    """`rasterize_protected_for_panel` fills these; a duplicated closing
    vertex is a degenerate edge."""
    for panel in segment_panels(_grid_page(2, 2)):
        assert panel.polygon[0] != panel.polygon[-1]

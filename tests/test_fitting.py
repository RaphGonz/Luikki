"""Fitting a panel and its references into Cobra's aspect buckets.

`cobra.py` has never been executed — no GPU here — so everything in it that
*can* be tested without the model is tested, and this is that part. The two
helpers are pure geometry over PIL images and need nothing but Pillow.

The measurement behind them, from `segment_panels` over the six real test
pages: panels run 0.63:1 to 3.38:1 while Cobra's widest bucket is 2.06:1, so
13 of 23 panels were being squashed by over 5% and one by 1.69x. These tests
pin that no squashing survives, and that no reference content is thrown away.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from luikki.colour.cobra import _ASPECT_TOLERANCE, _letterbox, _tiles


def _image(width: int, height: int, colour=(120, 60, 200)) -> Image.Image:
    return Image.new("RGB", (width, height), colour)


# -- the query side: letterbox ----------------------------------------------


@pytest.mark.parametrize(
    "size",
    [(1895, 561), (533, 170), (313, 464), (612, 581), (1046, 980)],
    ids=["teddy-wide", "tintin-strip", "laurine-tall", "manga-square", "antoine"],
)
def test_letterbox_never_distorts_a_real_panel(size):
    """Aspect in equals aspect out, for the actual panel shapes measured on
    the test pages. This is the whole point of the change."""
    canvas, box = _letterbox(_image(*size), 512, 256)

    assert canvas.size == (512, 256)
    inner_w, inner_h = box[2] - box[0], box[3] - box[1]
    assert inner_w / inner_h == pytest.approx(size[0] / size[1], rel=0.01)


def test_letterbox_fills_the_frame_on_one_axis():
    """Letterboxing must not shrink the panel more than it has to — the
    content should touch two opposite edges."""
    canvas, box = _letterbox(_image(1895, 561), 512, 256)
    inner_w, inner_h = box[2] - box[0], box[3] - box[1]
    assert inner_w == 512 or inner_h == 256


def test_letterbox_pads_with_white_not_black():
    """Padding is paper. Black padding would read as ink to a model whose
    whole input is a line drawing."""
    canvas, box = _letterbox(_image(400, 100, (10, 10, 10)), 512, 512)
    pixels = np.asarray(canvas)
    assert tuple(pixels[2, 256]) == (255, 255, 255)
    assert tuple(pixels[box[1] + 5, 256]) == (10, 10, 10)


def test_letterbox_box_crops_back_to_the_original_aspect():
    """The contract `propose` relies on: crop by the returned box and you get
    the panel back, not the panel plus a white margin."""
    source = _image(1895, 561)
    canvas, box = _letterbox(source, 512, 256)
    recovered = canvas.crop(box)
    assert recovered.size[0] / recovered.size[1] == pytest.approx(1895 / 561, rel=0.01)


def test_letterbox_handles_a_panel_larger_than_the_frame_in_both_axes():
    canvas, box = _letterbox(_image(4000, 3000), 512, 512)
    assert canvas.size == (512, 512)
    assert box[2] - box[0] <= 512 and box[3] - box[1] <= 512


# -- the reference side: tiles ----------------------------------------------


def test_a_matching_aspect_is_one_tile():
    """A page-shaped reference against a page-shaped query keeps taking
    Cobra's own path: one resize, no cutting."""
    tiles = _tiles(_image(672, 960), 512, 731, budget=6)
    assert len(tiles) == 1
    assert tiles[0].size == (512, 731)


def test_tolerance_matches_cobras_own():
    """Reused from `cobra_utils.utils.process_image` rather than invented."""
    assert _ASPECT_TOLERANCE == 0.15


def test_a_tall_sheet_against_a_wide_panel_is_cut_not_cropped():
    """The case that motivated the change. Cobra's `process_image` would keep
    a horizontal band through the middle and discard the heads and the feet;
    tiling must cover the sheet top to bottom."""
    tiles = _tiles(_image(800, 2000), 512, 256, budget=6)

    assert len(tiles) > 1
    assert all(t.size == (512, 256) for t in tiles)


def test_tiles_cover_the_whole_reference():
    """Nothing is thrown away — the first tile starts at the top edge and the
    last one ends at the bottom."""
    source = Image.new("RGB", (400, 1200))
    for y in range(1200):
        for x in (0, 399):
            source.putpixel((x, y), (y % 256, 0, 0))
    source.putpixel((200, 0), (0, 255, 0))
    source.putpixel((200, 1199), (0, 0, 255))

    tiles = _tiles(source, 512, 256, budget=12)
    first = np.asarray(tiles[0])
    last = np.asarray(tiles[-1])
    assert (first[:4] == [0, 255, 0]).any(), "top edge missing from the first tile"
    assert (last[-4:] == [0, 0, 255]).any(), "bottom edge missing from the last tile"


def test_tiles_overlap_so_a_seam_does_not_split_a_face():
    """Half-overlap: consecutive tiles must share content."""
    source = Image.new("RGB", (400, 1200))
    for y in range(1200):
        source.putpixel((200, y), (y % 256, (y // 256) * 40, 0))

    tiles = _tiles(source, 400, 200, budget=12)
    assert len(tiles) >= 3
    a, b = np.asarray(tiles[0]), np.asarray(tiles[1])
    assert (a[100:] == b[:100]).mean() > 0.5, "consecutive tiles share no content"


def test_budget_caps_the_tile_count_and_keeps_the_middle():
    """A tall sheet must not explode the CLIP retrieval cost. When tiles are
    dropped it is the outer ones, which are margin."""
    tiles = _tiles(_image(400, 4000), 512, 256, budget=3)
    assert len(tiles) == 3


def test_a_wide_reference_is_cut_into_vertical_slices():
    """The mirror case: a wide sheet against a tall panel."""
    tiles = _tiles(_image(3000, 500), 256, 512, budget=6)
    assert len(tiles) > 1
    assert all(t.size == (256, 512) for t in tiles)


def test_tiles_are_never_letterboxed():
    """A reference exists to supply colour, so white padding inside a
    reference patch is wasted context for both retrieval and the DiT."""
    tiles = _tiles(_image(400, 2000, (10, 200, 10)), 512, 256, budget=6)
    for tile in tiles:
        pixels = np.asarray(tile)
        assert not (pixels == 255).all(axis=2).any(), "white padding in a reference tile"


def test_a_degenerate_reference_still_yields_one_tile():
    """A one-pixel-tall strip is not worth a crash."""
    assert len(_tiles(_image(600, 1), 512, 256, budget=6)) >= 1


# -- the panel side: polygon masking ----------------------------------------


def test_panel_line_art_is_masked_to_its_polygon(tmp_path):
    """A bounding box is only the panel when the panel is a rectangle.

    For an L-shaped panel the crop also holds whatever the neighbour put in
    the corner, and the proposer would retrieve references for a scene that is
    partly not this panel. What gets *painted* out there never mattered —
    those zones come back UNASSIGNED — but what the model reads does.
    """
    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.web.session import PanelState, Session

    page = tmp_path / "page.png"
    art = np.full((100, 100), 255, dtype=np.uint8)
    art[10:90, 10:90] = 0  # ink everywhere inside, so masking is visible
    Image.fromarray(art).save(page)

    # Masking is the subject here, not extraction: passthrough keeps the ink
    # where this test put it.
    session = Session(tmp_path / "work", extractor=PassthroughExtractor())
    session.load_page(page)

    # An L: the top-right quarter is not part of the panel.
    panel = PanelState(
        order=0,
        x=0,
        y=0,
        width=100,
        height=100,
        polygon=[(0, 0), (50, 0), (50, 50), (100, 50), (100, 100), (0, 100)],
    )
    line_art = session._line_art_for(panel)

    assert line_art.shape == (100, 100, 3)
    assert (line_art[10:40, 60:90] == 255).all(), "the cut-out corner must be paper"
    assert (line_art[60:90, 10:40] == 0).any(), "the panel's own ink must survive"


def test_a_rectangular_panel_is_unchanged_by_masking(tmp_path):
    """The common case must cost nothing."""
    from luikki.extract.passthrough import PassthroughExtractor
    from luikki.segmentation.panels import box_to_polygon, PanelBox
    from luikki.web.session import PanelState, Session

    page = tmp_path / "page.png"
    rng = np.random.default_rng(0)
    Image.fromarray(rng.integers(0, 255, (60, 80), dtype=np.uint8)).save(page)

    session = Session(tmp_path / "work", extractor=PassthroughExtractor())
    session.load_page(page)

    box = PanelBox(x=0, y=0, width=80, height=60)
    panel = PanelState(order=0, x=0, y=0, width=80, height=60, polygon=box_to_polygon(box))

    line_art = session._line_art_for(panel)
    assert (line_art[:, :, 0] == session.structural_lines()).all()


def test_the_proposer_reads_the_extractor_not_the_raw_ink(tmp_path):
    """The mirror of `test_segmentation_reads_the_extractor_not_the_raw_ink`.

    Cobra conditions its DiT on the soft output of a line model and never on
    the artist's file. Feeding it `self.grey` put heavy brush, spot black and
    hatching into a network trained on none of them, and left the proposer
    reading a different drawing from the one trapped-ball cut into zones.
    """
    from luikki.segmentation.panels import box_to_polygon, PanelBox
    from luikki.web.session import PanelState, Session

    from test_extraction_stage import FakeExtractor

    page = tmp_path / "page.png"
    art = np.full((60, 80), 255, dtype=np.uint8)
    art[20:40, 20:60] = 0  # a spot black the extractor would return as contour
    Image.fromarray(art).save(page)

    lines = np.full((60, 80), 255, dtype=np.uint8)
    lines[20:22, 20:60] = 0  # the extractor's answer: an outline, not a fill

    session = Session(tmp_path / "work", extractor=FakeExtractor(lines))
    session.load_page(page)

    box = PanelBox(x=0, y=0, width=80, height=60)
    panel = PanelState(order=0, x=0, y=0, width=80, height=60, polygon=box_to_polygon(box))

    line_art = session._line_art_for(panel)
    assert (line_art[:, :, 0] == lines).all()
    assert (line_art[30:38, 25:55] == 255).all(), "the spot black must not reach the model"


# -- sheets: tiles placed on the drawings -----------------------------------


def _montage(width=1200, height=1200, rows=3, cols=3, gap=60):
    """A character sheet: separate coloured drawings with paper between them."""
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    cell_w = (width - gap * (cols + 1)) // cols
    cell_h = (height - gap * (rows + 1)) // rows
    for r in range(rows):
        for c in range(cols):
            x = gap + c * (cell_w + gap)
            y = gap + r * (cell_h + gap)
            draw.ellipse(
                (x, y, x + cell_w, y + cell_h),
                fill=(40 + 20 * r, 90 + 30 * c, 200 - 15 * r),
            )
    return sheet


def test_a_sheet_is_cut_on_its_drawings():
    """One drawing per patch is the unit CLIP compares against a panel; a
    grid band through a montage is not."""
    from luikki.colour.cobra import _subjects

    sheet = _montage()
    assert len(_subjects(sheet)) == 9

    tiles = _tiles(sheet, 512, 256, budget=6, kind="sheet")
    assert len(tiles) == 6
    assert all(t.size == (512, 256) for t in tiles)


def test_a_sheet_is_cut_even_when_its_aspect_already_fits():
    """A montage needs framing whatever its outline is: the whole-image patch
    of a 13-drawing sheet is 13 drawings too small to match anything."""
    sheet = _montage(1200, 1200)
    tiles = _tiles(sheet, 512, 512, budget=6, kind="sheet")
    assert len(tiles) > 1


def test_a_page_is_never_cut_on_subjects():
    """A finished page has no paper between its subjects, so there is nothing
    to place a window on — the grid is the honest answer."""
    sheet = _montage(1200, 1200)
    assert len(_tiles(sheet, 512, 512, budget=6, kind="page")) == 1


def test_one_big_drawing_falls_back_to_the_grid():
    """Not every reference is a montage. Below `_MIN_SUBJECTS` the sheet path
    must hand back to the grid rather than return one useless window."""
    from luikki.colour.cobra import _MIN_SUBJECTS, _subjects

    single = Image.new("RGB", (800, 2000), "white")
    ImageDraw.Draw(single).ellipse((100, 100, 700, 1900), fill=(200, 40, 40))
    assert len(_subjects(single)) < _MIN_SUBJECTS

    tiles = _tiles(single, 512, 256, budget=6, kind="sheet")
    assert len(tiles) > 1, "should have fallen back to grid striding"


def test_subject_windows_keep_the_target_aspect_exactly():
    """The patch must reach half the query's size without distortion, so the
    window it is cropped from has to be the target's shape already."""
    from luikki.colour.cobra import _subjects, _window_for

    sheet = _montage()
    for subject in _subjects(sheet):
        box = _window_for(subject, 512 / 256, sheet.size)
        assert (box[2] - box[0]) / (box[3] - box[1]) == pytest.approx(2.0, rel=0.02)
        assert 0 <= box[0] and 0 <= box[1]
        assert box[2] <= sheet.width and box[3] <= sheet.height


def test_subject_tiles_are_not_all_the_same_view():
    """Windows overlapping past `_SUBJECT_MAX_OVERLAP` are one view twice, and
    the whole point of a wide pool is that the k retrieved patches differ."""
    from luikki.colour.cobra import _SUBJECT_MAX_OVERLAP, _overlap, _subjects, _window_for

    sheet = _montage()
    kept = []
    for subject in _subjects(sheet):
        box = _window_for(subject, 2.0, sheet.size)
        if any(_overlap(box, other) > _SUBJECT_MAX_OVERLAP for other in kept):
            continue
        kept.append(box)
    for i, a in enumerate(kept):
        for b in kept[i + 1 :]:
            assert _overlap(a, b) <= _SUBJECT_MAX_OVERLAP


def test_subject_tiles_are_mostly_drawing_not_paper():
    """A window centred on a drawing should be filled by one.

    White inside a subject tile is the sheet's own paper, not padding — the
    tile is a crop, so nothing can be added. What matters is that the window
    landed on artwork rather than on the gap between two drawings.
    """
    for tile in _tiles(_montage(), 512, 256, budget=6, kind="sheet"):
        drawn = (np.asarray(tile) < 250).any(axis=2).mean()
        assert drawn > 0.15, f"window is {1 - drawn:.0%} paper"

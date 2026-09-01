"""The reference pool on disk, and the two ways a colour reaches the palette.

References stopped being a list of numpy arrays that dies with the process the
moment they became the input Cobra colours from. What the tests below pin is
the part that is easy to get subtly wrong once the palette is the artist's own
list rather than something derived: a character sheet *offers* colours and a
palette image *is* colours, so deleting the first must leave the palette
standing and deleting the second must take exactly its own colours with it.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from comiccolor.colour.references import KINDS, PALETTE_KIND, STORED_KINDS, ReferenceStore, UnknownKind
from comiccolor.web.session import Session


def _sheet(path, colours=((200, 30, 40), (30, 90, 200), (240, 220, 60))):
    """A character sheet: bands of flat colour on paper, with an ink border.

    `extract_palette(sheet_mode=True)` drops near-black and near-white first,
    so the bands are what must come back.
    """
    image = np.full((120, 120, 3), 250, dtype=np.uint8)
    for i, colour in enumerate(colours):
        image[10 + i * 30 : 34 + i * 30, 10:110] = colour
    image[:4, :] = 0
    Image.fromarray(image).save(path)
    return path


def test_add_then_reload_survives_a_new_store(tmp_path):
    """The point of the whole module: a restart keeps the book's references."""
    store = ReferenceStore(tmp_path / "references")
    store.add(_sheet(tmp_path / "teddy.png"), label="teddy sheet", kind="sheet")
    store.add(_sheet(tmp_path / "page12.png"), label="page 12", kind="page")

    reopened = ReferenceStore(tmp_path / "references")
    assert [r.label for r in reopened] == ["teddy sheet", "page 12"]
    assert [r.kind for r in reopened] == ["sheet", "page"]
    assert reopened.image(1).shape == (120, 120, 3)


def test_ids_are_never_reused(tmp_path):
    """A palette entry or a proposal log naming reference 3 must keep meaning
    the same image after reference 2 is deleted."""
    store = ReferenceStore(tmp_path / "references")
    store.add(_sheet(tmp_path / "a.png"))
    store.add(_sheet(tmp_path / "b.png"))
    store.remove(2)
    assert store.add(_sheet(tmp_path / "c.png")).id == 3


def test_unknown_kind_is_refused(tmp_path):
    """`kind` drives the proposal-time fitting step, so a typo must not reach
    it as a silently stored string."""
    store = ReferenceStore(tmp_path / "references")
    with pytest.raises(UnknownKind):
        store.add(_sheet(tmp_path / "a.png"), kind="charactersheet")
    assert len(store) == 0


def test_a_file_that_is_not_an_image_never_enters_the_index(tmp_path):
    """Verified on the way in, so a truncated upload fails at upload rather
    than at the first press of Generate flats."""
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    store = ReferenceStore(tmp_path / "references")
    with pytest.raises(Exception):
        store.add(broken)
    assert len(store) == 0
    assert len(ReferenceStore(tmp_path / "references")) == 0


def test_missing_file_is_dropped_rather_than_fatal(tmp_path):
    """The artist may tidy the folder by hand. The app must still open."""
    store = ReferenceStore(tmp_path / "references")
    store.add(_sheet(tmp_path / "a.png"))
    store.add(_sheet(tmp_path / "b.png"))
    store.path(1).unlink()

    reopened = ReferenceStore(tmp_path / "references")
    assert [r.id for r in reopened] == [2]


def test_a_reference_offers_colours_and_takes_none(tmp_path):
    """Upload is extraction, not inclusion.

    The image is what Cobra is shown and where colours are *found*; the
    palette is the artist's list. Nothing crosses between them without being
    chosen, which is the whole difference between the two.
    """
    session = Session(tmp_path / "work")
    stored = session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    offered = session.candidates(stored[0].id)

    assert len(offered) >= 3
    assert session.palette == [], "an upload put colours in the palette by itself"

    taken = session.include_candidate(1, offered[0])
    assert [entry.rgb for entry in session.palette] == [offered[0]]
    # Choosing the same colour twice is choosing it once.
    assert session.include_candidate(1, offered[0]).id == taken.id
    assert len(session.palette) == 1


def test_deleting_a_reference_keeps_the_colours_taken_from_it(tmp_path):
    """A colour in the palette is the artist's, not the image's.

    The reference is what gets deleted. Deleting the colours with it would
    repaint every zone snapped to them, which is a page-wide change made by a
    click that said nothing about colour.
    """
    session = Session(tmp_path / "work")
    stored = session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    offered = session.candidates(stored[0].id)
    for rgb in offered:
        session.include_candidate(1, rgb)
    kept = [entry.rgb for entry in session.palette]

    assert session.remove_reference(1)
    assert [entry.rgb for entry in session.palette] == kept
    assert len(session.reference_store) == 0


def test_removing_an_absent_reference_is_false_not_an_error(tmp_path):
    session = Session(tmp_path / "work")
    assert session.remove_reference(99) is False


def test_references_survive_loading_another_page(tmp_path, monkeypatch):
    """Rule: the reference pool belongs to the book, not the page in flight."""
    from comiccolor.segmentation import preprocess

    page = tmp_path / "page.png"
    Image.fromarray(np.full((40, 40), 255, dtype=np.uint8)).save(page)

    session = Session(tmp_path / "work")
    session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    before = len(session.palette)

    session.load_page(page)
    assert len(session.reference_store) == 1
    assert len(session.palette) == before


def test_a_new_session_on_the_same_workdir_finds_the_references(tmp_path):
    """What the artist experiences as "the app remembered my character sheet"."""
    first = Session(tmp_path / "work")
    first.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    for rgb in first.candidates(1):
        first.include_candidate(1, rgb)
    palette = [(entry.id, entry.rgb) for entry in first.palette]

    second = Session(tmp_path / "work")
    assert len(second.reference_store) == 1
    # Ids and all: a page reopened next week points at the same colours.
    assert [(entry.id, entry.rgb) for entry in second.palette] == palette


def test_a_palette_id_is_never_handed_out_twice(tmp_path):
    """A zone stores an id and nothing else, so a reused id silently repaints
    it. Ids are therefore monotonic and survive deletion — the palette is held
    now, not re-derived, and nothing renumbers it."""
    session = Session(tmp_path / "work")
    stored = session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    offered = session.candidates(stored[0].id)
    seen = [session.include_candidate(1, rgb).id for rgb in offered]

    session.delete_palette_entry(seen[0])
    more = session.add_reference(
        _sheet(tmp_path / "b.png", colours=((10, 200, 10),)), original_name="b.png"
    )
    seen.append(session.include_candidate(2, session.candidates(more[0].id)[0]).id)

    assert len(set(seen)) == len(seen)
    assert seen[-1] > max(seen[:-1]), "a deleted id came back"


def _coloured_page(path, panels=2, scale=3):
    """A finished page: framed panels, each a different colour world.

    Saved at `scale` times the sketch below, because a page is measured
    against the proposer's own frame: `_split_into_panels` drops a panel that
    would have to be blown up past `_MAX_UPSCALE` to reach it, and a 600 px
    "page" has no panel that survives. Real pages are thousands of pixels.
    """
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    fills = [(200, 60, 50), (60, 90, 200), (70, 170, 90)]
    for index in range(panels):
        left = 20 + index * 300
        image[20:380, left : left + 260] = fills[index % len(fills)]
        # A frame, and something inside it that is not the fill.
        image[20:26, left : left + 260] = 0
        image[374:380, left : left + 260] = 0
        image[20:380, left : left + 6] = 0
        image[20:380, left + 254 : left + 260] = 0
        image[120:220, left + 60 : left + 200] = (250, 230, 180)
    page = Image.fromarray(image)
    page.resize((page.width * scale, page.height * scale), Image.NEAREST).save(path)
    return path


def test_a_finished_page_is_stored_as_its_panels(tmp_path):
    """Cobra retrieves patches, and most patches of a whole page are
    backgrounds and props — so the tile covering a face can retrieve something
    that is not a face. Splitting on the way in is that finding made
    automatic: each stored reference is one composition."""
    session = Session(tmp_path / "work")
    stored = session.add_reference(
        _coloured_page(tmp_path / "finished.png"), original_name="finished.png", kind="page"
    )

    assert len(stored) == 2
    assert [reference.kind for reference in stored] == ["panel", "panel"]
    assert [reference.label for reference in stored] == [
        "finished.png — panel 1",
        "finished.png — panel 2",
    ]
    assert not [r for r in session.reference_store if r.kind == "page"]

    # Each panel is croppped to its own box, so its colours are its own.
    first, second = (session.candidates(reference.id) for reference in stored)
    assert first and second
    assert first != second


def test_a_page_whose_panels_cannot_be_found_is_stored_whole(tmp_path):
    """Half a split is worse than none. A page that bleeds, or one drawn
    without frames, stays one reference and says so through its kind."""
    session = Session(tmp_path / "work")
    stored = session.add_reference(
        _coloured_page(tmp_path / "one.png", panels=1),
        original_name="one.png",
        kind="page",
    )

    assert len(stored) == 1
    assert stored[0].kind == "page"
    assert stored[0].label == "one.png"


def test_the_panels_of_a_page_are_what_the_proposer_is_shown(tmp_path):
    session = Session(tmp_path / "work")
    session.add_reference(
        _coloured_page(tmp_path / "finished.png"), original_name="finished.png", kind="page"
    )
    shown = session.reference_images()
    assert [image.kind for image in shown] == ["panel", "panel"]
    # Cropped, so each one is smaller than the page it came from.
    assert all(image.pixels.shape[1] < 600 * 3 for image in shown)


def test_a_page_whose_panels_are_too_small_is_kept_whole(tmp_path):
    """Nothing reaches the model at its own size.

    `cobra._tiles` resizes every reference to the target bucket, so a panel
    well under that frame arrives blown up, and an upscaled smear outranks the
    sharp tile that holds the character — measured in `reports/10-retrieval`,
    the face falls from rank 1 to rank 22 of 80. Below the guard the page is
    worth more whole than in pieces.
    """
    session = Session(tmp_path / "work")
    stored = session.add_reference(
        _coloured_page(tmp_path / "small.png", scale=1),
        original_name="small.png",
        kind="page",
    )

    assert [reference.kind for reference in stored] == ["page"]


def test_kinds_are_the_three_the_fitting_step_knows(tmp_path):
    """Guards against a fourth kind arriving without the proposer learning it."""
    assert KINDS == ("page", "panel", "sheet")
    # `palette` is stored but is not a reference: the proposer is never shown a
    # strip of swatches as an example of how this book is coloured.
    assert PALETTE_KIND not in KINDS
    assert STORED_KINDS == (*KINDS, PALETTE_KIND)


def test_a_palette_image_takes_every_colour_without_asking(tmp_path):
    """The other door.

    A character sheet is a drawing whose colours are a proposal; a palette is
    the decision already made, in a file. Confirming each swatch of a strip
    the artist built on purpose is asking for the same work twice.
    """
    session = Session(tmp_path / "work")
    taken = session.add_palette(_sheet(tmp_path / "swatches.png"), original_name="p.png")

    assert len(taken) >= 3
    assert [entry.rgb for entry in session.palette] == [entry.rgb for entry in taken]
    assert [r.label for r in session.palette_images()] == ["p.png"]


def test_a_palette_image_is_not_shown_to_the_proposer(tmp_path):
    session = Session(tmp_path / "work")
    session.add_reference(_sheet(tmp_path / "sheet.png"), original_name="sheet.png")
    session.add_palette(_sheet(tmp_path / "swatches.png"), original_name="p.png")

    shown = session.reference_images()
    assert [image.label for image in shown] == ["sheet.png"]


def test_a_palette_goes_in_through_its_own_door(tmp_path):
    session = Session(tmp_path / "work")
    with pytest.raises(RuntimeError, match="Add palette"):
        session.add_reference(_sheet(tmp_path / "a.png"), kind=PALETTE_KIND)


def test_removing_a_palette_takes_its_colours_and_leaves_the_sheets(tmp_path):
    """The asymmetry the artist asked for, and the reason for it.

    A palette image *is* its colours. A character sheet is not: those were
    picked out of a drawing one at a time, and deleting the drawing must not
    repaint every zone snapped to them.
    """
    session = Session(tmp_path / "work")
    stored = session.add_reference(_sheet(tmp_path / "sheet.png"), original_name="s.png")
    offered = session.candidates(stored[0].id)
    from_sheet = session.include_candidate(1, offered[0]).id
    palette_colours = session.add_palette(
        _sheet(tmp_path / "swatches.png", colours=((10, 200, 10), (20, 20, 190))),
        original_name="p.png",
    )
    assert len(session.palette) == 1 + len(palette_colours)

    assert session.remove_reference(2)
    assert [entry.id for entry in session.palette] == [from_sheet]
    assert session.palette_images() == []

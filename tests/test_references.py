"""The reference pool: on disk, book-scoped, and derived colours follow it.

References stopped being a list of numpy arrays that dies with the process the
moment they became the input Cobra colours from. What the tests below pin is
the part that is easy to get subtly wrong once storage is real: the palette is
*derived* from the references, so deleting one must take its colours with it
and leave everything else standing.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from comiccolor.colour.references import KINDS, ReferenceStore, UnknownKind
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


def test_removing_a_reference_removes_its_colours(tmp_path):
    """The palette is derived, so deletion is not a separate bookkeeping
    problem — it is a rebuild."""
    session = Session(tmp_path / "work")
    session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")
    with_one = len(session.palette)
    assert with_one >= 3

    session.add_reference(
        _sheet(tmp_path / "b.png", colours=((10, 200, 10),)), original_name="b.png"
    )
    assert len(session.palette) > with_one

    assert session.remove_reference(2)
    assert len(session.palette) == with_one


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
    colours = [entry.rgb for entry in first.palette]

    second = Session(tmp_path / "work")
    assert len(second.reference_store) == 1
    assert [entry.rgb for entry in second.palette] == colours


def test_palette_ids_stay_unique_after_a_rebuild(tmp_path):
    """A rebuild renumbers the reference half, and the entries `generate_flats`
    invented sit above it. Colliding ids would silently repaint zones, since a
    zone stores an id and nothing else."""
    session = Session(tmp_path / "work")
    session.add_reference(_sheet(tmp_path / "a.png"), original_name="a.png")

    from comiccolor.model.entities import PaletteEntry

    session._created_palette.append(
        PaletteEntry(project_id=0, rgb=(1, 2, 3), label="invented", id=999)
    )
    session._rebuild_reference_palette()

    ids = [entry.id for entry in session.palette]
    assert len(ids) == len(set(ids))
    assert session.palette[-1].label == "invented"


def test_kinds_are_the_three_the_fitting_step_knows(tmp_path):
    """Guards against a fourth kind arriving without the proposer learning it."""
    assert KINDS == ("page", "panel", "sheet")

"""A project is a folder: close the app, start it again, and the page is there.

Each test does some work and then builds a *second* `Session` on the same
folder — which is what restarting the app is — and checks that the page came
back exactly: the same state, the same pixels.
"""

from __future__ import annotations

import json
import uuid

import cv2
import numpy as np
import pytest

from luikki.colour.proposer import DistinctColourProposer
from luikki.extract.passthrough import PassthroughExtractor
from luikki.model.masks import UNASSIGNED
from luikki.web import project
from luikki.web.session import Session, StepError


def _page(path, shift=0):
    """Two framed panels, each holding a circle and a box."""
    art = np.full((400, 600), 255, dtype=np.uint8)
    for x in (20, 320):
        cv2.rectangle(art, (x, 20), (x + 260, 380), 0, 3)
        cv2.circle(art, (x + 80 + shift, 140), 50, 0, 3)
        cv2.rectangle(art, (x + 40, 240), (x + 220, 350), 0, 3)
    cv2.imwrite(str(path), art)
    return path


def _swatch(path):
    image = np.zeros((40, 160, 3), dtype=np.uint8)
    for index, bgr in enumerate([(40, 30, 200), (200, 120, 30), (60, 180, 60), (180, 60, 180)]):
        image[:, index * 40 : (index + 1) * 40] = bgr
    cv2.imwrite(str(path), image)
    return path


def _start(workdir):
    """What starting the app does."""
    return Session(workdir, extractor=PassthroughExtractor())


def _zones(labels):
    return sorted(int(label) for label in np.unique(labels) if label != UNASSIGNED)


def _through_flats(session, page):
    session.load_page(page, original_name=page.name)
    session.detect_panels()
    session.segment_zones()
    session.generate_flats()


def test_a_page_reopens_exactly_as_it_was_left(tmp_path):
    work = tmp_path / "work"
    first = _start(work)
    first.add_palette(_swatch(tmp_path / "swatch.png"), original_name="swatch.png")
    first.load_page(_page(tmp_path / "page.png"), original_name="page.png")
    first.detect_panels()
    moved = [(x + 3, y) if i == 0 else (x, y) for i, (x, y) in enumerate(first.panels[0].polygon)]
    first.set_panel_polygon(0, moved)
    first.segment_zones()
    first.merge_zones(0, _zones(first.panels[0].label_map)[:2])
    first.generate_flats()
    segment = first.segments[0]
    first.snap_segment(segment.panel, segment.label)

    second = _start(work)

    assert second.state() == first.state()
    np.testing.assert_array_equal(second.zones_rgba(), first.zones_rgba())
    np.testing.assert_array_equal(second.flats_rgba(), first.flats_rgba())
    np.testing.assert_array_equal(second.unsnapped_mask(), first.unsnapped_mask())


def test_a_cut_survives_a_restart(tmp_path):
    first = _start(tmp_path / "work")
    first.load_page(_page(tmp_path / "page.png"))
    first.detect_panels()
    first.segment_zones()
    panel, label = first.zone_at(150, 300)  # inside the first panel's box
    first.cut_zone(panel, label, [(150, 235), (150, 355)])

    second = _start(tmp_path / "work")

    assert _zones(second.panels[panel].label_map) == _zones(first.panels[panel].label_map)
    np.testing.assert_array_equal(second.zones_rgba(), first.zones_rgba())


def test_two_pages_keep_their_own_work(tmp_path):
    session = _start(tmp_path / "work")
    session.load_page(_page(tmp_path / "a.png"), original_name="a.png")
    session.detect_panels()
    first = session.page_id
    session.load_page(_page(tmp_path / "b.png", shift=20), original_name="b.png")

    assert session.panels == []
    assert [(page["name"], page["stage"]) for page in session.state()["pages"]] == [
        ("a.png", "panels"),
        ("b.png", "page"),
    ]

    session.open_page(first)
    assert session.original_name == "a.png"
    assert len(session.panels) == 2
    assert _start(tmp_path / "work").page_id == first, "the app reopens the page left open"


def test_a_page_keeps_one_uuid_for_life(tmp_path):
    """The GPU quota counts pages by it. Folder numbers are reused after a
    deletion and repeat from project to project, so they cannot."""
    session = _start(tmp_path / "work")
    session.load_page(_page(tmp_path / "a.png"))
    first_id, first_uid = session.page_id, session.page_uid
    session.load_page(_page(tmp_path / "b.png"))

    assert uuid.UUID(first_uid) and session.page_uid != first_uid
    restarted = _start(tmp_path / "work")
    restarted.open_page(first_id)
    assert restarted.page_uid == first_uid


def test_a_page_saved_before_uuids_gets_one_and_keeps_it(tmp_path):
    session = _start(tmp_path / "work")
    session.load_page(_page(tmp_path / "a.png"))
    path = project.page_folder(session.workdir, session.page_id) / project.PAGE_FILE
    record = json.loads(path.read_text(encoding="utf-8"))
    del record["uid"]
    path.write_text(json.dumps(record), encoding="utf-8")

    given = _start(tmp_path / "work").page_uid
    assert given
    assert _start(tmp_path / "work").page_uid == given


class _Recorder(DistinctColourProposer):
    def __init__(self):
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        return super().propose(request)


def test_every_panel_of_one_press_shares_its_generation(tmp_path):
    recorder = _Recorder()
    session = Session(tmp_path / "work", proposer=recorder, extractor=PassthroughExtractor())
    _through_flats(session, _page(tmp_path / "page.png"))
    session.generate_flats()

    first, second = recorder.requests[:2], recorder.requests[2:]
    assert len(first) == len(second) == 2
    assert {request.page_id for request in recorder.requests} == {session.page_uid}
    assert len({request.generation_id for request in first}) == 1
    assert len({request.generation_id for request in second}) == 1
    assert first[0].generation_id != second[0].generation_id


def test_rerunning_a_step_leaves_no_stale_zone_files(tmp_path):
    session = _start(tmp_path / "work")
    session.load_page(_page(tmp_path / "page.png"))
    session.detect_panels()
    session.segment_zones()
    folder = project.page_folder(session.workdir, session.page_id)
    assert sorted(path.name for path in folder.glob("panel*.npy")) == ["panel0.npy", "panel1.npy"]

    session.detect_panels()

    assert list(folder.glob("panel*.npy")) == []
    assert _start(tmp_path / "work").state()["done"]["zones"] is False


def test_deleting_a_page_opens_the_newest_one_left(tmp_path):
    session = _start(tmp_path / "work")
    for name in ("a.png", "b.png", "c.png"):
        session.load_page(_page(tmp_path / name), original_name=name)
    first = session.state()["pages"][0]["id"]

    session.open_page(first)
    session.delete_page()
    assert session.original_name == "c.png"
    assert not project.page_folder(session.workdir, first).exists()

    session.delete_page()
    session.delete_page()
    assert session.page_id is None
    assert session.state()["pages"] == []
    with pytest.raises(StepError):
        session.delete_page()


def test_a_deleted_reference_warns_and_keeps_the_flats(tmp_path):
    session = _start(tmp_path / "work")
    stored = session.add_reference(_swatch(tmp_path / "sheet.png"), original_name="sheet.png")
    _through_flats(session, _page(tmp_path / "page.png"))
    assert session.state()["flats_stale"] is False

    session.remove_reference(stored[0].id)

    state = session.state()
    assert state["done"]["flats"] is True
    assert state["flats_stale"] is True
    assert _start(tmp_path / "work").state()["flats_stale"] is True


def test_a_colour_deleted_while_its_page_was_closed_lets_go_on_opening(tmp_path):
    session = _start(tmp_path / "work")
    session.add_palette(_swatch(tmp_path / "swatch.png"))
    _through_flats(session, _page(tmp_path / "a.png"))
    key = session.segments[0].key
    entry = session.snap_segment(*key).palette_entry_id
    closed = session.page_id

    session.load_page(_page(tmp_path / "b.png"))
    session.delete_palette_entry(entry)
    session.open_page(closed)

    reopened = session.segment(*key)
    assert reopened.snapped is False
    assert reopened.palette_entry_id != entry


def test_a_page_that_cannot_be_read_does_not_stop_the_app(tmp_path):
    session = _start(tmp_path / "work")
    session.load_page(_page(tmp_path / "page.png"))
    page_id = session.page_id
    session.source.unlink()

    restarted = _start(tmp_path / "work")

    assert restarted.page_id is None
    assert [page["id"] for page in restarted.state()["pages"]] == [page_id]
    with pytest.raises(StepError):
        restarted.open_page(page_id)


def test_pages_over_http(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from luikki.web.app import create_app

    client = TestClient(create_app(tmp_path / "work", extractor=PassthroughExtractor()))
    for name in ("a.png", "b.png"):
        with _page(tmp_path / name).open("rb") as handle:
            state = client.post("/api/page", files={"file": (name, handle, "image/png")}).json()
    assert [page["name"] for page in state["pages"]] == ["a.png", "b.png"]
    assert state["page"]["name"] == "b.png"

    state = client.post(f"/api/pages/{state['pages'][0]['id']}/open").json()
    assert state["page"]["name"] == "a.png"

    state = client.delete("/api/page").json()
    assert [page["name"] for page in state["pages"]] == ["b.png"]
    assert state["page"]["name"] == "b.png"

    assert client.post("/api/pages/99/open").status_code == 409
    assert not list((tmp_path / "work").glob("tmp*")), "an upload is not left in the project"

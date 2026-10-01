"""The progress bar reports work done, and only work done."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.web.app import create_app  # noqa: E402
from luikki.web.progress import Cancelled, Progress  # noqa: E402


def test_nothing_running_reads_as_nothing():
    snapshot = Progress().snapshot()
    assert snapshot["running"] is False
    assert snapshot["percent"] == 0


def test_ticks_never_go_backwards_or_past_the_end():
    progress = Progress()
    seen = []
    with progress.run(10):
        for units in (3, -5, 4, 50):
            progress.tick(units)
            seen.append(progress.snapshot()["percent"])
        assert progress.snapshot()["running"] is True
    assert seen == sorted(seen)
    assert seen[-1] == 100
    assert progress.snapshot()["running"] is False


def test_a_failed_step_stops_without_claiming_it_finished():
    progress = Progress()
    with pytest.raises(RuntimeError):
        with progress.run(10):
            progress.tick(4)
            raise RuntimeError("the step broke")
    snapshot = progress.snapshot()
    assert snapshot["running"] is False
    assert snapshot["percent"] == 40


@pytest.fixture
def client(tmp_path):
    from luikki.extract.passthrough import PassthroughExtractor

    app = create_app(tmp_path / "work", extractor=PassthroughExtractor())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def page(tmp_path):
    """Two framed panels, each holding two closed shapes."""
    art = np.full((400, 600), 255, dtype=np.uint8)
    for x in (20, 320):
        cv2.rectangle(art, (x, 20), (x + 260, 380), 0, 3)
        cv2.circle(art, (x + 80, 140), 50, 0, 3)
        cv2.rectangle(art, (x + 40, 240), (x + 220, 350), 0, 3)
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), art)
    return path


def _watch(session, monkeypatch):
    """Every snapshot the step produced, one per tick."""
    seen = []
    tick = session.progress.tick

    def spy(units):
        tick(units)
        seen.append(session.progress.snapshot())

    monkeypatch.setattr(session.progress, "tick", spy)
    return seen


def _upload(client, path):
    with path.open("rb") as handle:
        return client.post("/api/page", files={"file": (path.name, handle, "image/png")})


def test_segmenting_reports_every_panel_and_ends_at_100(client, page, monkeypatch):
    assert client.get("/api/progress").json()["running"] is False
    _upload(client, page)
    panels = len(client.post("/api/panels").json()["panels"])
    seen = _watch(client.app.state.session, monkeypatch)

    assert client.post("/api/zones").status_code == 200

    percents = [snapshot["percent"] for snapshot in seen]
    assert percents == sorted(percents)
    assert 0 < percents[0] < 100
    assert {s["index"] for s in seen if s["phase"] == "segment"} == set(range(1, panels + 1))
    assert client.get("/api/progress").json() == {
        "running": False,
        "cancellable": False,
        "phase": "segment",
        "index": panels,
        "count": panels,
        "percent": 100.0,
    }


def test_finding_the_planes_reports_its_panels(client, page, monkeypatch):
    _upload(client, page)
    client.post("/api/panels")
    client.post("/api/zones")
    seen = _watch(client.app.state.session, monkeypatch)

    assert client.post("/api/planes").status_code == 200

    assert seen and all(snapshot["phase"] == "depth" for snapshot in seen)
    final = client.get("/api/progress").json()
    assert final["running"] is False
    assert final["percent"] == 100.0


def test_only_a_cancellable_run_stops():
    progress = Progress()
    assert progress.cancel() is False, "nothing is running"
    with progress.run(10):
        assert progress.cancel() is False, "a run that says it cannot stop does not"
        progress.tick(1)
    with pytest.raises(Cancelled):
        with progress.run(10, cancellable=True):
            assert progress.snapshot()["cancellable"] is True
            assert progress.cancel() is True
            progress.tick(1)
    # The flag dies with the run it stopped.
    with progress.run(10, cancellable=True):
        progress.tick(1)


def test_stopping_segmentation_leaves_the_page_as_it_was(client, page, monkeypatch):
    """Stop lands between two passes, and nothing of the run is kept: the
    zones and planes from before the press are all still there."""
    _upload(client, page)
    client.post("/api/panels")
    client.post("/api/zones")
    client.post("/api/planes")
    before = client.get("/api/state").json()
    before_planes = client.get("/api/planes.png").content

    session = client.app.state.session
    tick = session.progress.tick
    ticks = []

    def press_stop_midway(units):
        ticks.append(units)
        if len(ticks) == 3:
            assert client.post("/api/cancel").json() == {"stopping": True}
        tick(units)

    monkeypatch.setattr(session.progress, "tick", press_stop_midway)
    stopped = client.post("/api/zones")
    assert stopped.status_code == 409
    assert stopped.json()["code"] == "cancelled"

    assert client.get("/api/state").json() == before
    assert client.get("/api/planes.png").content == before_planes
    assert client.get("/api/progress").json()["running"] is False

    monkeypatch.setattr(session.progress, "tick", tick)
    assert client.post("/api/zones").status_code == 200, "a stopped run can be run again"


def test_stopping_the_planes_leaves_none(client, page, monkeypatch):
    _upload(client, page)
    client.post("/api/panels")
    client.post("/api/zones")
    session = client.app.state.session
    tick = session.progress.tick

    def press_stop(units):
        client.post("/api/cancel")
        tick(units)

    monkeypatch.setattr(session.progress, "tick", press_stop)
    stopped = client.post("/api/planes")
    assert stopped.json()["code"] == "cancelled"
    assert client.get("/api/state").json()["done"]["planes"] is False

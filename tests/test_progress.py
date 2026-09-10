"""The progress bar reports work done, and only work done."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from luikki.web.app import create_app  # noqa: E402
from luikki.web.progress import Progress  # noqa: E402


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
        "phase": "segment",
        "index": panels,
        "count": panels,
        "percent": 100.0,
    }


def test_generating_flats_reports_its_panels(client, page, monkeypatch):
    _upload(client, page)
    client.post("/api/panels")
    client.post("/api/zones")
    seen = _watch(client.app.state.session, monkeypatch)

    assert client.post("/api/flats").status_code == 200

    assert seen and all(snapshot["phase"] == "colour" for snapshot in seen)
    final = client.get("/api/progress").json()
    assert final["running"] is False
    assert final["percent"] == 100.0

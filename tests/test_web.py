"""Rule 3: every screen reaches the next one.

"panel detection, bubble detection and the editor route were all built,
tested, and unreachable" is the failure this file exists to catch. It presses
the buttons in order, through the HTTP API the browser actually calls, and
takes a PSD out the far end.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psd_tools")

from fastapi.testclient import TestClient  # noqa: E402

from comiccolor.web.app import create_app  # noqa: E402


@pytest.fixture
def page(tmp_path):
    """Two framed panels, each holding two closed shapes, plus a bubble."""
    art = np.full((400, 600), 255, dtype=np.uint8)
    for x in (20, 320):
        cv2.rectangle(art, (x, 20), (x + 260, 380), 0, 3)
        cv2.circle(art, (x + 80, 140), 50, 0, 3)
        cv2.rectangle(art, (x + 40, 240), (x + 220, 350), 0, 3)
        # Scattered small marks. The glyph filter bands around the page's
        # *median* component height, so a page made only of large shapes
        # rejects real lettering as too small. Spaced past cluster_dilate_px
        # so they never cluster into a bubble seed themselves.
        for i in range(8):
            mx, my = x + 20 + (i % 4) * 60, 200 + (i // 4) * 160
            cv2.rectangle(art, (mx, my), (mx + 6, my + 11), 0, -1)

    # A bubble: a closed white ellipse with baseline-aligned glyphs inside.
    cv2.ellipse(art, (200, 90), (70, 34), 0, 0, 360, 0, 2)
    for i in range(6):
        cv2.rectangle(art, (160 + i * 13, 84), (160 + i * 13 + 8, 96), 0, -1)

    path = tmp_path / "page.png"
    cv2.imwrite(str(path), art)
    return path


@pytest.fixture
def swatch(tmp_path):
    """A four-chip swatch image."""
    image = np.zeros((40, 160, 3), dtype=np.uint8)
    for index, bgr in enumerate([(40, 30, 200), (200, 120, 30), (60, 180, 60), (180, 60, 180)]):
        image[:, index * 40 : (index + 1) * 40] = bgr
    path = tmp_path / "swatch.png"
    cv2.imwrite(str(path), image)
    return path


@pytest.fixture
def client(tmp_path):
    """Passthrough extractor: these tests are about the button wiring.

    The real extractor is 172 MB of weights and a torch import, and what it
    does to segmentation is `test_extraction_feeds_segmentation` below, not
    every route test.
    """
    from comiccolor.extract.passthrough import PassthroughExtractor

    app = create_app(tmp_path / "work", extractor=PassthroughExtractor())
    with TestClient(app) as client:
        yield client


def upload(client, route, path):
    with path.open("rb") as handle:
        return client.post(route, files={"file": (path.name, handle, "image/png")})


def test_every_button_in_order_yields_a_psd(client, page, tmp_path):
    assert upload(client, "/api/page", page).status_code == 200

    for route in ("/api/panels", "/api/bubbles", "/api/zones", "/api/flats"):
        response = client.post(route)
        assert response.status_code == 200, (route, response.text)

    state = response.json()
    assert state["done"] == {
        "page": True, "panels": True, "bubbles": True, "zones": True, "flats": True,
    }
    assert state["panels"], "no panels detected on a two-panel page"
    assert sum(panel["zones"] for panel in state["panels"]) > 0
    assert state["result"]["assigned"] > 0

    export = client.post("/api/export")
    assert export.status_code == 200
    assert export.content[:4] == b"8BPS"

    out = tmp_path / "out.psd"
    out.write_bytes(export.content)
    from psd_tools import PSDImage

    groups = [layer for layer in PSDImage.open(out) if layer.is_group()]
    assert groups and all(len(group) for group in groups)


def test_buttons_refuse_out_of_order(client):
    """Rule 2's corollary: a step that has not run cannot be skipped past."""
    assert client.post("/api/panels").status_code == 409
    assert client.post("/api/zones").status_code == 409
    assert client.post("/api/flats").status_code == 409
    assert client.post("/api/export").status_code == 409


def test_zones_need_panels_even_with_a_page(client, page):
    upload(client, "/api/page", page)
    response = client.post("/api/zones")
    assert response.status_code == 409
    assert "panel" in response.json()["error"].lower()


def test_rerunning_a_step_invalidates_what_depended_on_it(client, page):
    """Rule 4. Zones computed before the bubbles were known are stale."""
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/zones")
    assert client.post("/api/flats").json()["done"]["flats"] is True

    state = client.post("/api/bubbles").json()
    assert state["done"]["zones"] is False
    assert state["done"]["flats"] is False
    assert client.post("/api/flats").status_code == 409


def test_a_swatch_gives_the_page_a_palette_to_snap_to(client, page, swatch):
    upload(client, "/api/page", page)
    state = upload(client, "/api/reference", swatch).json()
    assert len(state["palette"]) >= 2

    client.post("/api/panels")
    client.post("/api/zones")
    result = client.post("/api/flats").json()["result"]

    assert result["assigned"] > 0


def test_previews_exist_for_every_stage_that_renders_one(client, page):
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/zones")
    client.post("/api/flats")

    for route in ("/api/page.png", "/api/zones.png", "/api/flats.png"):
        response = client.get(route)
        assert response.status_code == 200, route
        assert response.headers["content-type"] == "image/png"


def test_the_proposal_raster_is_not_reachable(client, page):
    """Rule 6: Cobra's raw output never reaches the artist's eye.

    There is no route that returns it, and adding one is the mistake this
    guards against.
    """
    assert client.get("/api/proposal.png").status_code == 404
    routes = {route.path for route in client.app.routes}
    assert not any("proposal" in route for route in routes)


# -- the reference pool over HTTP -------------------------------------------


def _sheet(path):
    """A character sheet: flat colour bands on paper, with an ink edge."""
    import numpy as np
    from PIL import Image

    image = np.full((120, 120, 3), 250, dtype=np.uint8)
    for i, colour in enumerate(((200, 30, 40), (30, 90, 200), (240, 220, 60))):
        image[10 + i * 30 : 34 + i * 30, 10:110] = colour
    image[:4, :] = 0
    Image.fromarray(image).save(path)
    return path


def _add_reference(client, path, kind="sheet"):
    with path.open("rb") as handle:
        return client.post(
            "/api/reference",
            files={"file": (path.name, handle, "image/png")},
            data={"kind": kind},
        )


def test_reference_round_trip_over_http(tmp_path, client):
    """Upload, see it listed with its kind, fetch its thumbnail, delete it.
    Rule 3: a route with no way to reach it is a feature that does not exist,
    so every one of these has a button behind it in `app.js`."""
    sheet = _sheet(tmp_path / "sheet.png")

    response = _add_reference(client, sheet, kind="page")
    assert response.status_code == 200
    state = response.json()
    assert len(state["references"]) == 1
    assert state["references"][0]["kind"] == "page"
    assert state["palette"], "a sheet with three colour bands must yield colours"

    reference_id = state["references"][0]["id"]
    thumbnail = client.get(f"/api/reference/{reference_id}.png")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/png"

    deleted = client.request("DELETE", f"/api/reference/{reference_id}")
    assert deleted.status_code == 200
    assert deleted.json()["references"] == []
    assert deleted.json()["palette"] == []


def test_deleting_an_absent_reference_is_404(client):
    assert client.request("DELETE", "/api/reference/99").status_code == 404


def test_unknown_kind_is_refused_by_the_api(tmp_path, client):
    response = _add_reference(client, _sheet(tmp_path / "sheet.png"), kind="nonsense")
    assert response.status_code == 422
    assert client.get("/api/state").json()["references"] == []


def test_a_reference_that_is_not_an_image_is_refused(tmp_path, client):
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    with broken.open("rb") as handle:
        response = client.post(
            "/api/reference", files={"file": ("broken.png", handle, "image/png")}
        )
    assert response.status_code == 422
    assert client.get("/api/state").json()["references"] == []

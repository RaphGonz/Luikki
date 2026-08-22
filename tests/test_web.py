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


# -- steps 2 and 3, corrected by hand ----------------------------------------
#
# Detection proposes the geometry and the artist settles it. These press the
# routes the canvas presses: replace a polygon, add one, delete one — and
# refuse all three everywhere the stage rules say they do not belong.

SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]


def test_bubbles_wait_for_panels(client, page):
    """The steps run in one order. A balloon traced onto a page whose panels
    are about to be re-detected is work the artist cannot get back."""
    upload(client, "/api/page", page)
    refused = client.post("/api/bubbles")
    assert refused.status_code == 409
    assert "panel" in refused.json()["error"].lower()

    client.post("/api/panels")
    assert client.post("/api/bubbles").status_code == 200


def test_a_panel_keeps_the_corners_the_artist_left_it_with(client, page):
    upload(client, "/api/page", page)
    state = client.post("/api/panels").json()
    assert state["editable"] == {"panels": True, "bubbles": False}

    order = state["panels"][0]["order"]
    moved = client.put(f"/api/panel/{order}", json={"polygon": SQUARE})
    assert moved.status_code == 200

    corners = {tuple(point) for point in moved.json()["panels"][0]["polygon"]}
    assert corners == {(100, 100), (300, 100), (300, 300), (100, 300)}


def test_a_drawn_panel_takes_its_place_in_reading_order(client, page):
    """A panel added last does not export last. The number in its corner is
    the order the PSD groups run in, so it is re-derived, not appended."""
    upload(client, "/api/page", page)
    before = client.post("/api/panels").json()["panels"]

    # Above every detected panel on the test page, so it must read first.
    added = client.post(
        "/api/panel", json={"polygon": [[30, 5], [560, 5], [560, 15], [30, 15]]}
    )
    assert added.status_code == 200
    panels = added.json()["panels"]

    assert len(panels) == len(before) + 1
    assert [p["order"] for p in panels] == list(range(len(panels)))
    assert panels[0]["polygon"][0] == [30, 5], "the new panel reads first"


def test_a_panel_can_be_deleted_but_not_the_last_one(client, page):
    upload(client, "/api/page", page)
    panels = client.post("/api/panels").json()["panels"]
    assert len(panels) >= 2

    while len(panels) > 1:
        response = client.delete(f"/api/panel/{panels[-1]['order']}")
        assert response.status_code == 200
        panels = response.json()["panels"]

    refused = client.delete(f"/api/panel/{panels[0]['order']}")
    assert refused.status_code == 409
    assert "last panel" in refused.json()["error"]
    assert len(client.get("/api/state").json()["panels"]) == 1


def test_two_corners_are_not_a_panel(client, page):
    upload(client, "/api/page", page)
    order = client.post("/api/panels").json()["panels"][0]["order"]
    refused = client.put(f"/api/panel/{order}", json={"polygon": [[10, 10], [20, 20]]})
    assert refused.status_code == 409
    assert "three corners" in refused.json()["error"]


def test_correcting_a_panel_invalidates_what_was_cut_from_it(client, page):
    """Rule 4, for geometry the artist moved rather than a button they pressed."""
    upload(client, "/api/page", page)
    order = client.post("/api/panels").json()["panels"][0]["order"]
    client.post("/api/bubbles")
    client.post("/api/zones")

    # ...and once the zones exist, the shape they were cut from is settled.
    refused = client.put(f"/api/panel/{order}", json={"polygon": SQUARE})
    assert refused.status_code == 409
    assert client.get("/api/state").json()["editable"] == {
        "panels": False,
        "bubbles": False,
    }

    # Detecting panels again reopens it, exactly as the message says.
    client.post("/api/panels")
    assert client.get("/api/state").json()["editable"]["panels"] is True


def test_a_bubble_can_be_traced_corrected_and_removed(client, page):
    upload(client, "/api/page", page)
    client.post("/api/panels")

    refused = client.post("/api/bubble", json={"polygon": SQUARE})
    assert refused.status_code == 409, "no tracing before the step has run"

    client.post("/api/bubbles")
    added = client.post("/api/bubble", json={"polygon": SQUARE})
    assert added.status_code == 200
    protected = added.json()["protected"]
    index = len(protected) - 1
    assert [list(point) for point in protected[index]] == SQUARE

    corrected = client.put(
        f"/api/bubble/{index}", json={"polygon": [[10, 10], [60, 10], [60, 60]]}
    )
    assert corrected.status_code == 200
    assert len(corrected.json()["protected"][index]) == 3

    removed = client.delete(f"/api/bubble/{index}")
    assert removed.status_code == 200
    assert len(removed.json()["protected"]) == len(protected) - 1
    assert client.delete(f"/api/bubble/{index}").status_code == 409

# -- step 6, the way the browser presses it ---------------------------------


def _through_flats(client, page, tmp_path):
    _add_reference(client, _sheet(tmp_path / "sheet.png"))
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/zones")
    return client.post("/api/flats").json()


def test_the_sidebar_can_count_what_step_six_has_left(client, page, tmp_path):
    """`state.segments` is what the snap step's note is written from.

    Without it the browser has no way to say "501 snapped, 251 still the
    model's guess" without pulling every segment down to count them.
    """
    state = _through_flats(client, page, tmp_path)
    segments = state["segments"]
    assert segments["count"] > 0
    assert segments["snapped"] == 0, "flats never snap"
    assert segments["snappable"] is True
    assert segments["threshold"] > 0

    sources = {entry["source"] for entry in state["palette"]}
    assert sources == {"reference", "proposed"}


def test_clicking_a_zone_snaps_it_and_unsnapping_puts_it_back(client, page, tmp_path):
    """The inspector's whole loop: click, see the suggestion, snap, undo."""
    state = _through_flats(client, page, tmp_path)

    listed = client.get("/api/segments?limit=1").json()["segments"]
    assert listed, "flats produced no segments to click"
    biggest = listed[0]
    x, y = biggest["anchor"]

    clicked = client.get(f"/api/segment?x={x}&y={y}").json()
    assert clicked["panel"] == biggest["panel"]
    assert clicked["label"] == biggest["label"]
    assert clicked["snapped"] is False
    assert clicked["suggestion"]["delta"] >= 0

    entry = clicked["suggestion"]["palette_entry_id"]
    snapped = client.post(
        f"/api/segment/{clicked['panel']}/{clicked['label']}/snap?entry_id={entry}"
    ).json()
    assert snapped["palette_entry_id"] == entry
    assert snapped["snapped"] is True
    assert client.get("/api/state").json()["segments"]["snapped"] == 1

    back = client.post(
        f"/api/segment/{clicked['panel']}/{clicked['label']}/unsnap"
    ).json()
    assert back["palette_entry_id"] == clicked["palette_entry_id"]
    assert back["snapped"] is False
    assert client.get("/api/state").json()["segments"]["snapped"] == 0


def test_a_click_on_the_gutter_resolves_to_nothing(client, page, tmp_path):
    _through_flats(client, page, tmp_path)
    assert client.get("/api/segment?x=0&y=0").status_code == 404


def test_ignoring_the_guard_snaps_everything(client, page, tmp_path):
    """The checkbox sends `inf`, which is the CLI's `--threshold inf`."""
    _through_flats(client, page, tmp_path)

    guarded = client.post("/api/snap-all").json()["result"]
    everything = client.post("/api/snap-all?threshold=inf").json()["result"]

    assert everything["skipped"] == 0
    assert everything["snapped"] >= guarded["snapped"]
    assert everything["snapped"] == everything["segments"]


def test_what_step_six_has_left_is_a_picture(client, page, tmp_path):
    """The "left to snap" overlay. 404 before flats: there is no workload yet."""
    assert client.get("/api/unsnapped.png").status_code == 404

    _through_flats(client, page, tmp_path)
    response = client.get("/api/unsnapped.png")
    assert response.status_code == 200
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

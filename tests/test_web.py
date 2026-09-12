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

from luikki.web.app import create_app  # noqa: E402


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
    from luikki.extract.passthrough import PassthroughExtractor

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

    # The default stack is one layer per colour, over the page: no groups, and
    # exactly as many layers as the sidebar said it was about to write.
    top = list(PSDImage.open(out))
    assert top and not any(layer.is_group() for layer in top)
    assert len(top) == state["export"]["layers"]["colour"]

    # The other stack, on the same page, from the same button.
    grouped = client.post("/api/export?granularity=panel")
    assert grouped.status_code == 200
    out.write_bytes(grouped.content)
    groups = [layer for layer in PSDImage.open(out) if layer.is_group()]
    assert groups and all(len(group) for group in groups)
    assert sum(len(group) for group in groups) == state["export"]["layers"]["panel"]


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
    assert response.json()["code"] == "panels_first"


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
    state = _take_every_colour(client, upload(client, "/api/reference", swatch).json())
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
    assert refused.json()["code"] == "panels_first"

    client.post("/api/panels")
    assert client.post("/api/bubbles").status_code == 200


def test_a_panel_keeps_the_corners_the_artist_left_it_with(client, page):
    upload(client, "/api/page", page)
    state = client.post("/api/panels").json()
    assert state["editable"] == {"panels": True, "bubbles": False, "zones": False}

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
    assert refused.json()["code"] == "last_panel"
    assert len(client.get("/api/state").json()["panels"]) == 1


def test_two_corners_are_not_a_panel(client, page):
    upload(client, "/api/page", page)
    order = client.post("/api/panels").json()["panels"][0]["order"]
    refused = client.put(f"/api/panel/{order}", json={"polygon": [[10, 10], [20, 20]]})
    assert refused.status_code == 409
    assert refused.json()["code"] == "corners_too_few"


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
        "zones": True,
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

# -- step 4b: zones the artist corrects -------------------------------------
#
# Trapped-ball cuts from the ink it can see. Where the ink is open it leaks a
# shape into the background, and where the drawing is busy it returns forty
# scraps of one garment. These press the two corrections that follow, and the
# stage rule that makes them safe to be permanent.


def _zoned(client, page):
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/bubbles")
    return client.post("/api/zones").json()


def _zones_of(client, panel=0):
    """Every label in one panel, biggest first — what a press could land on."""
    state = client.get("/api/state").json()
    assert state["panels"][panel]["zones"] > 1
    return state


def test_zones_are_correctable_between_the_cut_and_the_colour(client, page):
    """The whole stage rule, in one test.

    Not before the zones exist, and not once the flats are coloured from them:
    the corrections are permanent and there is no unmerge, so the boundary is
    what protects the artist rather than a history they would have to manage.
    """
    upload(client, "/api/page", page)
    client.post("/api/panels")
    assert client.get("/api/state").json()["editable"]["zones"] is False

    _zoned(client, page)
    assert client.get("/api/state").json()["editable"]["zones"] is True

    client.post("/api/flats")
    assert client.get("/api/state").json()["editable"]["zones"] is False
    refused = client.post("/api/zones/merge", json={"panel": 0, "labels": [1, 2]})
    assert refused.status_code == 409
    assert refused.json()["code"] == "zones_closed"


def test_a_press_resolves_to_the_zone_under_it(client, page):
    _zoned(client, page)
    state = client.get("/api/state").json()
    panel = state["panels"][0]
    inside = client.get(
        f"/api/zone?x={panel['polygon'][0][0] + 40}&y={panel['polygon'][0][1] + 40}"
    )
    assert inside.status_code == 200
    assert inside.json()["panel"] == 0
    assert len(inside.json()["bounds"]) == 4

    # The mask that draws the highlight, cropped to the zone's own bounds.
    label = inside.json()["label"]
    mask = client.get(f"/api/zone/0/{label}.png")
    assert mask.status_code == 200
    assert mask.headers["x-bounds"] == ",".join(
        str(edge) for edge in inside.json()["bounds"]
    )

    assert client.get("/api/zone?x=0&y=0").status_code == 404


def test_a_sweep_picks_up_what_it_passes_over(client, page):
    """One request for the whole gesture, not one per zone."""
    _zoned(client, page)
    panel = client.get("/api/state").json()["panels"][0]
    x0, y0 = panel["polygon"][0]

    swept = client.post(
        "/api/zones/along",
        json={"points": [[x0 + 80, y0 + 40], [x0 + 80, y0 + 320]]},
    ).json()["zones"]

    assert len(swept) >= 2, "a stroke across a panel met one zone or none"
    assert len({(z["panel"], z["label"]) for z in swept}) == len(swept)
    # The boxes travel with the zones, or the browser would ask for forty of
    # them one at a time and undo the point of one request per gesture.
    assert all(len(zone["bounds"]) == 4 for zone in swept)


def test_merging_makes_several_zones_one(client, page):
    _zoned(client, page)
    before = client.get("/api/state").json()["panels"][0]["zones"]
    swept = client.post(
        "/api/zones/along",
        json={"points": [[100, 60], [100, 340]]},
    ).json()["zones"]
    labels = [z["label"] for z in swept if z["panel"] == 0][:3]
    assert len(labels) >= 2

    merged = client.post("/api/zones/merge", json={"panel": 0, "labels": labels})
    assert merged.status_code == 200
    assert merged.json()["result"]["merged"] == len(labels)
    assert merged.json()["panels"][0]["zones"] == before - (len(labels) - 1)

    # One address from here on: every pixel of the merged zones answers with
    # the surviving label.
    survivor = merged.json()["result"]["label"]
    for label in labels:
        assert label == survivor or label not in [
            z["label"] for z in client.post(
                "/api/zones/along", json={"points": [[100, 60], [100, 340]]}
            ).json()["zones"]
        ]


def test_one_zone_is_not_a_merge(client, page):
    _zoned(client, page)
    refused = client.post("/api/zones/merge", json={"panel": 0, "labels": [1]})
    assert refused.status_code == 409
    assert refused.json()["code"] == "merge_too_few"


def test_a_cut_splits_a_zone_and_keeps_every_pixel(client, page):
    """The stroke is the line the ink was missing, and its own pixels go to
    whichever piece they are nearest — a cut leaves no unassigned seam."""
    _zoned(client, page)
    state = client.get("/api/state").json()
    before = state["panels"][0]["zones"]

    # The test page's first panel is a framed rectangle holding a circle and a
    # box; the zone under this point is the panel's background.
    target = client.get("/api/zone?x=40&y=40").json()
    assert target["panel"] == 0
    left, top, right, bottom = target["bounds"]
    middle = (top + bottom) // 2

    painted = _painted_pixels(client)
    cut = client.post(
        "/api/zones/cut",
        json={
            "panel": 0,
            "label": target["label"],
            "stroke": [[left - 5, middle], [right + 5, middle]],
        },
    )
    assert cut.status_code == 200
    assert cut.json()["result"]["pieces"] >= 2
    assert cut.json()["panels"][0]["zones"] > before
    assert _painted_pixels(client) == painted, "a cut lost pixels to the seam"


def test_a_stroke_that_separates_nothing_changes_nothing(client, page):
    _zoned(client, page)
    target = client.get("/api/zone?x=40&y=40").json()
    before = client.get("/api/state").json()["panels"][0]["zones"]

    refused = client.post(
        "/api/zones/cut",
        json={"panel": 0, "label": target["label"], "stroke": [[40, 40], [44, 44]]},
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "cut_no_split"
    assert client.get("/api/state").json()["panels"][0]["zones"] == before


def _painted_pixels(client):
    """How much of the page is inside some zone, from the zone map itself."""
    import io

    from PIL import Image

    image = Image.open(io.BytesIO(client.get("/api/zones.png").content))
    return int((np.array(image)[:, :, 3] > 0).sum())


# -- the palette, as its own thing ------------------------------------------


def _palette_of(state):
    return [e for e in state["palette"] if e["source"] == "palette"]


def test_changing_a_palette_colour_repaints_every_zone_holding_it(
    client, page, tmp_path
):
    """Rule 1, as the thing the artist actually feels.

    A zone stores `palette_entry_id` and never an RGB, so changing the entry
    is the repaint — no re-segmentation, no re-proposal, and the snapped
    zones stay snapped to the colour they were pointed at.
    """
    state = _through_flats(client, page, tmp_path)
    entry = _palette_of(state)[0]

    snapped = client.post("/api/snap-all?threshold=inf").json()
    assert snapped["result"]["snapped"] > 0
    before = client.get("/api/flats.png").content

    recoloured = client.put(f"/api/palette/{entry['id']}", json={"rgb": [7, 240, 13]})
    assert recoloured.status_code == 200
    assert [e for e in recoloured.json()["palette"] if e["id"] == entry["id"]][0][
        "rgb"
    ] == [7, 240, 13]

    # Still snapped, still the same segments — only the colour moved.
    assert recoloured.json()["segments"]["snapped"] == snapped["segments"]["snapped"]
    assert client.get("/api/flats.png").content != before


def test_a_colour_that_is_not_a_colour_is_refused(client, page, tmp_path):
    state = _through_flats(client, page, tmp_path)
    entry = _palette_of(state)[0]
    off_scale = client.put(f"/api/palette/{entry['id']}", json={"rgb": [7, 300, 13]})
    assert off_scale.status_code == 409
    assert off_scale.json()["code"] == "colour_invalid"
    assert client.put("/api/palette/9999", json={"rgb": [7, 24, 13]}).status_code == 409


def test_dropping_a_colour_unsnaps_what_was_pointed_at_it(client, page, tmp_path):
    """A zone cannot hold an id that is gone, so it goes back to what the
    model proposed — the same thing Undo does, done for the artist."""
    state = _through_flats(client, page, tmp_path)
    entry = _palette_of(state)[0]
    client.post("/api/snap-all?threshold=inf")

    segment = client.get("/api/segments?limit=1").json()["segments"][0]
    client.post(
        f"/api/segment/{segment['panel']}/{segment['label']}/snap?entry_id={entry['id']}"
    )

    dropped = client.delete(f"/api/palette/{entry['id']}").json()
    assert not [e for e in dropped["palette"] if e["id"] == entry["id"]]

    back = client.get(f"/api/segment?x={segment['anchor'][0]}&y={segment['anchor'][1]}").json()
    assert back["palette_entry_id"] != entry["id"]
    assert back["snapped"] is False


def test_a_colour_the_reference_does_not_have_is_refused(client, tmp_path):
    state = _add_reference(client, _sheet(tmp_path / "sheet.png")).json()
    reference_id = state["references"][0]["id"]
    refused = client.post(
        "/api/palette", json={"reference_id": reference_id, "rgb": [1, 2, 3]}
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "colour_not_offered"


def test_a_palette_image_needs_no_clicking(client, tmp_path):
    """Upload, and the colours are in. No chips, and not a reference."""
    swatches = _sheet(tmp_path / "swatches.png")
    with swatches.open("rb") as handle:
        state = client.post(
            "/api/palette/image",
            files={"file": (swatches.name, handle, "image/png")},
        ).json()

    assert len(state["palettes"]) == 1
    assert state["references"] == [], "a palette image is not a reference"
    assert len(_palette_of(state)) == len(state["palettes"][0]["colours"])


def test_removing_a_palette_leaves_the_colours_picked_from_a_sheet(client, tmp_path):
    sheet = _add_reference(client, _sheet(tmp_path / "sheet.png")).json()
    candidate = sheet["references"][0]["candidates"][0]
    kept = client.post(
        "/api/palette",
        json={"reference_id": sheet["references"][0]["id"], "rgb": candidate["rgb"]},
    ).json()["entry_id"]

    swatches = _sheet(tmp_path / "swatches.png")
    with swatches.open("rb") as handle:
        state = client.post(
            "/api/palette/image",
            files={"file": (swatches.name, handle, "image/png")},
        ).json()
    assert len(_palette_of(state)) > 1

    dropped = client.request(
        "DELETE", f"/api/reference/{state['palettes'][0]['id']}"
    ).json()
    assert [e["id"] for e in _palette_of(dropped)] == [kept]
    assert dropped["palettes"] == []


# -- step 6, the way the browser presses it ---------------------------------


def _through_flats(client, page, tmp_path):
    _take_every_colour(client, _add_reference(client, _sheet(tmp_path / "sheet.png")).json())
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
    assert sources == {"palette", "proposed"}


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


def test_snap_all_ignores_the_guard_unless_asked(client, page, tmp_path):
    """The default is the artist's palette, not the guard.

    Pressing Snap all with nothing typed in the box sends no threshold, and
    every segment goes to its nearest palette colour. What the artist wants by
    default is their own colours; a segment snapped from far away is still one
    click from `unsnap`. The guard is what they turn on, not what they turn off.
    """
    _through_flats(client, page, tmp_path)

    # The guard first, while nothing has moved: asked for, it still refuses.
    guarded = client.post("/api/snap-all?threshold=0").json()["result"]
    assert guarded["snapped"] == 0

    everything = client.post("/api/snap-all").json()["result"]
    assert everything["skipped"] == 0
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


def _take_every_colour(client, state):
    """Choose the whole of every reference's offer, the way clicking each chip
    would. Upload extracts; only this puts anything in the palette."""
    for reference in state["references"]:
        for candidate in reference["candidates"]:
            state = client.post(
                "/api/palette",
                json={"reference_id": reference["id"], "rgb": candidate["rgb"]},
            ).json()
    return state


def test_reference_round_trip_over_http(tmp_path, client):
    """Upload, see it listed with its kind, fetch its thumbnail, delete it.
    Rule 3: a route with no way to reach it is a feature that does not exist,
    so every one of these has a button behind it in `app.js`."""
    sheet = _sheet(tmp_path / "sheet.png")

    # `panel` rather than `page`: a page is stored as the panels it splits
    # into, which is its own test below.
    response = _add_reference(client, sheet, kind="panel")
    assert response.status_code == 200
    state = response.json()
    assert len(state["references"]) == 1
    assert state["references"][0]["kind"] == "panel"
    assert state["palette"] == [], "an upload put colours in the palette by itself"

    candidates = state["references"][0]["candidates"]
    assert candidates, "a sheet with three colour bands must offer colours"
    assert all(candidate["entry_id"] is None for candidate in candidates)

    reference_id = state["references"][0]["id"]
    thumbnail = client.get(f"/api/reference/{reference_id}.png")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/png"

    taken = client.post(
        "/api/palette",
        json={"reference_id": reference_id, "rgb": candidates[0]["rgb"]},
    ).json()
    assert len(taken["palette"]) == 1
    assert taken["references"][0]["candidates"][0]["entry_id"] == taken["entry_id"]

    deleted = client.request("DELETE", f"/api/reference/{reference_id}")
    assert deleted.status_code == 200
    assert deleted.json()["references"] == []
    # The image is gone; the colour taken from it is the artist's and stays.
    assert len(deleted.json()["palette"]) == 1


def test_uploading_a_finished_page_adds_its_panels(client, tmp_path):
    """One upload, several references — and the artist sees which."""
    import numpy as np
    from PIL import Image

    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    for index, fill in enumerate([(200, 60, 50), (60, 90, 200)]):
        left = 20 + index * 300
        image[20:380, left : left + 260] = fill
        image[20:26, left : left + 260] = 0
        image[374:380, left : left + 260] = 0
        image[20:380, left : left + 6] = 0
        image[20:380, left + 254 : left + 260] = 0
        image[120:220, left + 60 : left + 200] = (250, 230, 180)
    finished = tmp_path / "finished.png"
    # At a real page's scale: `_split_into_panels` drops panels too small for
    # the proposer's frame, and none of a 600 px page's would survive.
    page = Image.fromarray(image)
    page.resize((page.width * 3, page.height * 3), Image.NEAREST).save(finished)

    state = _add_reference(client, finished, kind="page").json()

    assert len(state["references"]) == 3
    assert [r["kind"] for r in state["references"]] == ["page", "panel", "panel"]
    assert state["result"] == {"added": 3, "kind": "page", "panels": 2}


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
    assert response.json()["code"] == "image_unreadable"
    assert client.get("/api/state").json()["references"] == []

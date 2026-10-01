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

    for route in ("/api/panels", "/api/bubbles", "/api/zones", "/api/planes"):
        response = client.post(route)
        assert response.status_code == 200, (route, response.text)

    state = response.json()
    assert state["done"] == {
        "page": True, "panels": True, "bubbles": True, "zones": True, "planes": True,
    }
    assert state["panels"], "no panels detected on a two-panel page"
    assert sum(panel["zones"] for panel in state["panels"]) > 0
    assert sum(state["planes"]["counts"].values()) == sum(p["zones"] for p in state["panels"])

    export = client.post("/api/export")
    assert export.status_code == 200
    assert export.content[:4] == b"8BPS"

    out = tmp_path / "out.psd"
    out.write_bytes(export.content)
    from psd_tools import PSDImage

    # The default stack is one layer per plane, balloons on top: no groups,
    # and exactly as many layers as the sidebar said it was about to write.
    top = list(PSDImage.open(out))
    assert top and not any(layer.is_group() for layer in top)
    assert len(top) == state["export"]["layers"]["plane"]
    assert top[-1].name == "Balloons"

    # The other stack, on the same page, from the same button.
    grouped = client.post("/api/export?granularity=colour")
    assert grouped.status_code == 200
    out.write_bytes(grouped.content)
    groups = [layer for layer in PSDImage.open(out) if layer.is_group()]
    assert groups and all(len(group) for group in groups)
    assert sum(len(group) for group in groups) + 1 == state["export"]["layers"]["colour"]


def test_the_planes_may_be_skipped(client, page, tmp_path):
    """Planes are optional: straight from the zones to one layer of flats."""
    _zoned(client, page)
    export = client.post("/api/export", json={"names": {"flats": "Aplats", "balloons": "Bulles"}})
    assert export.status_code == 200
    out = tmp_path / "out.psd"
    out.write_bytes(export.content)
    from psd_tools import PSDImage

    assert [layer.name for layer in PSDImage.open(out)] == ["Aplats", "Bulles"]


def test_the_artist_moves_zones_between_planes(client, page):
    _zoned(client, page)
    zone = client.get("/api/zone?x=40&y=40").json()
    body = {"zones": [{"panel": zone["panel"], "label": zone["label"]}], "plane": 3}

    refused = client.put("/api/planes", json=body)
    assert refused.status_code == 409
    assert refused.json()["code"] == "planes_first"

    client.post("/api/planes")
    moved = client.put("/api/planes", json=body)
    assert moved.status_code == 200
    assert moved.json()["planes"]["counts"]["3"] == 1
    assert client.get("/api/zone?x=40&y=40").json()["plane"] == 3

    unknown = client.put("/api/planes", json={**body, "plane": 7})
    assert unknown.json()["code"] == "plane_unknown"

    # Ctrl+Z takes a plane change back, like a merge or a cut.
    back = client.post("/api/zones/undo")
    assert back.status_code == 200
    assert back.json()["planes"]["counts"]["3"] == 0


def test_every_zone_lands_on_one_plane(client, page):
    """Depth votes: a zone is never split across two layers."""
    _zoned(client, page)
    state = client.post("/api/planes").json()
    zones = sum(panel["zones"] for panel in state["panels"])
    assert sum(state["planes"]["counts"].values()) == zones
    assert state["planes"]["counts"]["3"] == 0, "no model calls anything a character"


def test_buttons_refuse_out_of_order(client):
    """Rule 2's corollary: a step that has not run cannot be skipped past."""
    assert client.post("/api/panels").status_code == 409
    assert client.post("/api/zones").status_code == 409
    assert client.post("/api/planes").status_code == 409
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
    assert client.post("/api/planes").json()["done"]["planes"] is True

    state = client.post("/api/bubbles").json()
    assert state["done"]["zones"] is False
    assert state["done"]["planes"] is False
    assert client.post("/api/planes").status_code == 409

    client.post("/api/zones")
    client.post("/api/planes")
    assert client.post("/api/zones").json()["done"]["planes"] is False, "new zones, no planes"


def test_previews_exist_for_every_stage_that_renders_one(client, page):
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/zones")
    assert client.get("/api/planes.png").status_code == 404
    client.post("/api/planes")

    # The browser sends the tints its stylesheet holds.
    assert client.get("/api/planes.png?tints=eb5a3c,78c850,3ca0e6,c83cc8").status_code == 200
    assert client.get("/api/planes.png?tints=nothex").status_code == 422

    for route in ("/api/page.png", "/api/zones.png", "/api/planes.png"):
        response = client.get(route)
        assert response.status_code == 200, route
        assert response.headers["content-type"] == "image/png"


# -- steps 2 and 3, corrected by hand ----------------------------------------
#
# Detection proposes the geometry and the artist settles it. These press the
# routes the canvas presses: replace a polygon, add one, delete one — and
# refuse all three everywhere the stage rules say they do not belong.

SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]


def test_a_page_can_say_it_has_no_bubbles(client, page):
    """Professionals ink first and letter afterwards, so the page that reaches
    Luikki often has no balloon on it. Saying so is a press of step 3, not a
    step left unrun: zones wait on the step, not on the balloons."""
    upload(client, "/api/page", page)
    client.post("/api/panels")

    skipped = client.post("/api/bubbles/skip")
    assert skipped.status_code == 200
    assert skipped.json()["protected"] == []
    assert skipped.json()["done"]["bubbles"] is True

    assert client.post("/api/zones").status_code == 200


def test_saying_there_are_no_bubbles_still_needs_panels(client, page):
    upload(client, "/api/page", page)
    refused = client.post("/api/bubbles/skip")
    assert refused.status_code == 409
    assert refused.json()["code"] == "panels_first"


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
    assert state["editable"] == {"panels": True, "bubbles": False, "zones": False, "planes": False}

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
        "planes": False,
    }

    # Detecting panels again reopens it, exactly as the message says.
    client.post("/api/panels")
    assert client.get("/api/state").json()["editable"]["panels"] is True


def test_a_curve_is_sampled_where_it_is_rasterised():
    """Nothing downstream of `flatten_polygon` knows what a Bezier is. The
    nodes and their handles are the stored truth — so a handle can be grabbed
    again after reopening a page — and the points are made at the moment of
    use, half a pixel apart, which is below what the rasteriser can tell
    apart."""
    from luikki.web.session import flatten_polygon

    square = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert flatten_polygon(square) == square

    # One node pulled straight up: the edge leaving it has to bulge off the
    # straight line between the two corners.
    drawn = flatten_polygon([(0, 0, 0, -50), (100, 0), (100, 100), (0, 100)])
    assert len(drawn) > 4
    assert min(y for _, y in drawn) < 0
    assert (0, 0) in drawn and (100, 100) in drawn


def test_a_bubble_keeps_the_curve_it_was_drawn_with(client, page):
    """A balloon is round, and the tester drew it with the handles every
    drawing program has. What comes back is the nodes, handles included."""
    upload(client, "/api/page", page)
    client.post("/api/panels")
    client.post("/api/bubbles")

    curved = [[100, 100, 30, 0], [200, 100, 0, 30], [200, 200, -30, 0], [100, 200, 0, -30]]
    added = client.post("/api/bubble", json={"polygon": curved})
    assert added.status_code == 200
    assert added.json()["protected"][-1] == curved

    # And the panel it sits in still segments: the shape reaches the
    # rasteriser as points, whatever the artist drew it with.
    assert client.post("/api/zones").status_code == 200


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


def test_zones_are_correctable_from_the_cut_through_the_planes(client, page):
    """Not before the zones exist; from then on, planes or not."""
    upload(client, "/api/page", page)
    client.post("/api/panels")
    assert client.get("/api/state").json()["editable"]["zones"] is False

    _zoned(client, page)
    assert client.get("/api/state").json()["editable"]["zones"] is True

    client.post("/api/planes")
    assert client.get("/api/state").json()["editable"]["zones"] is True


def _plane(client, zone):
    left, top, right, bottom = zone["bounds"]
    found = client.post(
        "/api/zones/along", json={"points": [[left, top], [right, bottom]]}
    ).json()["zones"]
    return {(z["panel"], z["label"]): z["plane"] for z in found}[(zone["panel"], zone["label"])]


def test_a_merged_zone_votes_again_unless_it_is_a_character(client, page):
    _zoned(client, page)
    client.post("/api/planes")
    session = client.app.state.session
    crossed, untouched = _stacked_pair(client)
    labels = [crossed["label"], untouched["label"]]

    merged = client.post("/api/zones/merge", json={"panel": 0, "labels": labels}).json()
    survivor = merged["result"]["label"]
    panel = session.panels[0]
    from luikki.segmentation.planes import planes_from

    assert session.plane_of(0, survivor) == planes_from(panel.label_map, panel.depth_groups)[survivor]
    zones = sum(each["zones"] for each in merged["panels"])
    assert sum(merged["planes"]["counts"].values()) == zones

    client.post("/api/zones/undo")
    client.put("/api/planes", json={"zones": [crossed, untouched], "plane": 3})
    merged = client.post("/api/zones/merge", json={"panel": 0, "labels": labels}).json()
    assert session.plane_of(0, merged["result"]["label"]) == 3


def test_a_cut_over_the_planes_gives_every_piece_the_plane(client, page):
    _zoned(client, page)
    client.post("/api/planes")
    crossed, _ = _stacked_pair(client)
    client.put("/api/planes", json={"zones": [crossed], "plane": 3})

    left, top, right, bottom = crossed["bounds"]
    cut = client.post(
        "/api/zones/cut",
        json={
            "panel": 0,
            "label": crossed["label"],
            "stroke": [[left - 5, (top + bottom) // 2], [right + 5, (top + bottom) // 2]],
        },
    )
    assert cut.status_code == 200
    assert cut.json()["planes"]["counts"]["3"] == 2
    assert client.post("/api/export").status_code == 200


def test_each_piece_of_a_cut_votes_again_on_its_depth(client, page):
    """The plane belongs to the pixels: a zone cut across the depth gives
    pieces on different planes (the fake depth grows down the panel)."""
    _zoned(client, page)
    client.post("/api/planes")
    session = client.app.state.session
    target = client.get("/api/zone?x=40&y=40").json()
    left, top, right, bottom = target["bounds"]
    cut = client.post(
        "/api/zones/cut",
        json={"panel": 0, "label": target["label"],
              "stroke": [[left - 5, (top + bottom) // 2], [right + 5, (top + bottom) // 2]]},
    ).json()["result"]
    planes = {session.plane_of(0, label) for label in cut["labels"]}
    assert len(planes) > 1, planes

    # And a restart keeps the depth to vote on.
    from luikki.web.session import Session

    reopened = Session(session.workdir, extractor=session.raw_extractor)
    assert reopened.panels[0].depth_groups is not None


def test_undo_over_the_planes_puts_the_planes_back(client, page):
    _zoned(client, page)
    client.post("/api/planes")
    before = client.get("/api/state").json()["planes"]["counts"]
    crossed, untouched = _stacked_pair(client)
    client.post(
        "/api/zones/merge",
        json={"panel": 0, "labels": [crossed["label"], untouched["label"]]},
    )
    assert client.post("/api/zones/undo").json()["planes"]["counts"] == before


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


def _stacked_pair(client):
    """Two zones of one panel that do not touch and do not share a row.

    The sweep runs down the panel, so what it meets is stacked: a horizontal
    stroke across one of them cannot reach the other.
    """
    swept = client.post(
        "/api/zones/along",
        json={"points": [[100, 60], [100, 340]]},
    ).json()["zones"]
    zones = [zone for zone in swept if zone["panel"] == 0]
    for first in zones:
        for second in zones:
            if second["label"] == first["label"]:
                continue
            if first["bounds"][3] < second["bounds"][1]:
                return first, second
    raise AssertionError("the sweep met no two zones stacked one above the other")


def test_a_cut_keeps_the_rest_of_a_merged_zone_together(client, page):
    """A merged zone is several disconnected pieces, and a cut divides only
    the piece the stroke crossed.

    Reading the cut off the pieces that remained gave every one of them a
    label of its own — one stroke undid the whole merge, and the first tester
    had to build a forty-piece garment again by hand.
    """
    _zoned(client, page)
    before = client.get("/api/state").json()["panels"][0]["zones"]

    crossed, untouched = _stacked_pair(client)
    merged = client.post(
        "/api/zones/merge",
        json={"panel": 0, "labels": [crossed["label"], untouched["label"]]},
    )
    assert merged.status_code == 200
    survivor = merged.json()["result"]["label"]
    assert merged.json()["panels"][0]["zones"] == before - 1

    left, top, right, bottom = crossed["bounds"]
    cut = client.post(
        "/api/zones/cut",
        json={
            "panel": 0,
            "label": survivor,
            "stroke": [[left - 5, (top + bottom) // 2], [right + 5, (top + bottom) // 2]],
        },
    )
    assert cut.status_code == 200
    # One stroke, one new zone. The piece it never reached is still the
    # survivor's, not a label the artist would have to merge back in.
    assert cut.json()["panels"][0]["zones"] == before
    assert len(cut.json()["result"]["labels"]) == 2


def test_a_merge_and_a_cut_can_be_taken_back(client, page):
    """Step 4 is undoable inside itself. The stage boundary is still what
    makes the corrections permanent — the stack dies with the step."""
    _zoned(client, page)
    before = client.get("/api/state").json()["panels"][0]["zones"]
    assert client.get("/api/state").json()["undo"] == 0

    crossed, untouched = _stacked_pair(client)
    merged = client.post(
        "/api/zones/merge",
        json={"panel": 0, "labels": [crossed["label"], untouched["label"]]},
    )
    assert merged.json()["panels"][0]["zones"] == before - 1
    assert merged.json()["undo"] == 1

    survivor = merged.json()["result"]["label"]
    left, top, right, bottom = crossed["bounds"]
    cut = client.post(
        "/api/zones/cut",
        json={
            "panel": 0,
            "label": survivor,
            "stroke": [[left - 5, (top + bottom) // 2], [right + 5, (top + bottom) // 2]],
        },
    )
    assert cut.json()["panels"][0]["zones"] == before
    assert cut.json()["undo"] == 2

    assert client.post("/api/zones/undo").json()["panels"][0]["zones"] == before - 1
    assert client.post("/api/zones/undo").json()["panels"][0]["zones"] == before

    nothing = client.post("/api/zones/undo")
    assert nothing.status_code == 409
    assert nothing.json()["code"] == "nothing_to_undo"


def test_taking_back_a_zone_edit_stops_at_the_stage_boundary(client, page):
    """Segmenting again, or finding the planes, ends the stack: an undo across
    either would put back zones, or planes, the page no longer describes."""
    _zoned(client, page)
    crossed, untouched = _stacked_pair(client)
    client.post(
        "/api/zones/merge",
        json={"panel": 0, "labels": [crossed["label"], untouched["label"]]},
    )
    assert client.get("/api/state").json()["undo"] == 1

    assert client.post("/api/zones").json()["undo"] == 0

    crossed, untouched = _stacked_pair(client)
    client.post(
        "/api/zones/merge",
        json={"panel": 0, "labels": [crossed["label"], untouched["label"]]},
    )
    client.post("/api/planes")
    refused = client.post("/api/zones/undo")
    assert refused.status_code == 409
    assert refused.json()["code"] == "nothing_to_undo"


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


def test_touching_zones_never_share_a_colour(client, page):
    """The zone map is the fake flats the PSD carries: no two zones that touch
    alike, so a magic wand takes one zone and no more."""
    import io

    from PIL import Image

    from luikki.export.flat_colours import adjacency

    _zoned(client, page)
    session = client.app.state.session
    rgba = np.array(Image.open(io.BytesIO(client.get("/api/zones.png").content)))
    panel = session.panels[0]
    for a, b in adjacency(panel.label_map).tolist():
        assert panel.assignments[a] != panel.assignments[b]
    assert set(map(tuple, rgba[rgba[:, :, 3] > 0][:, :3])) <= {
        entry.rgb for entry in session.palette
    }

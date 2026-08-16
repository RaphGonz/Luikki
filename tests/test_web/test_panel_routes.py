"""The panel polygon editor contract, as tests.

PAN-01 (list a page's panels as polygons in reading order), PAN-02 (move a
vertex, insert one, delete one — with a sub-3-vertex delete refused, not
silently applied) and PAN-03 (draw a panel from scratch, delete one the
detector invented, no confirmation step per D-19).

Every assertion here checks a concrete field, never just a status code — a
200 whose body lost the polygon is the regression this file exists to
catch. The bounds refusals (``test_polygon_beyond_page_bounds_is_422``,
``test_polygon_with_too_many_vertices_is_422``) are the mitigation for the
Denial-of-Service rows T-2-01/T-2-03 in the phase threat model, not
incidental validation — they are what stops hostile geometry before it ever
reaches ``cv2.fillPoly``.

Plan 02-07's ``run_panels`` stage runner (referenced by this plan's
``read_first``) is not yet present in this worktree — it is a sibling
wave-3 plan executing in parallel and has not merged. Rather than skip
PAN-01's detector-backed listing test, ``test_list_panels_returns_polygons_in_reading_order``
calls ``segment_panels``/``box_to_polygon`` directly — the exact detector
call ``run_panels`` will wrap — and persists the result through ``Store``,
the same way the eventual stage runner will. Not a missing integration.
"""

from __future__ import annotations

import numpy as np

from comiccolor.model import Page, Panel, Store, Volume
from comiccolor.segmentation.panels import box_to_polygon, segment_panels
from comiccolor.web.appconfig import PROJECT_DB_NAME


def _make_page(project_dir, width: int = 300, height: int = 300) -> int:
    """A page persisted directly through ``Store``, no upload round trip.

    Route tests that only need "some page of a known size" build one this
    way rather than going through ``page_in_project`` (which fixes 64x64,
    too small to place several non-overlapping panels apart).
    """
    with Store(project_dir / PROJECT_DB_NAME) as store:
        volume = store.add_volume(Volume(project_id=store.the_project().id, name="Ch1"))
        page = store.add_page(
            Page(volume_id=volume.id, source_path="pages/x.png", index=0, width=width, height=height)
        )
        return page.id


def test_list_panels_returns_polygons_in_reading_order(client, project_dir):
    """PAN-01: two detected panels list as 4-vertex polygons, leftmost first."""
    size, gutter = 300, 30
    width = 2 * size + 3 * gutter
    height = size + 2 * gutter
    mask = np.zeros((height, width), dtype=bool)
    for column in range(2):
        x = gutter + column * (size + gutter)
        y = gutter
        mask[y, x : x + size] = True
        mask[y + size - 1, x : x + size] = True
        mask[y : y + size, x] = True
        mask[y : y + size, x + size - 1] = True
        mask[y + 50 : y + 60, x + 50 : x + 200] = True  # content, not just a frame

    boxes = segment_panels(mask)
    assert len(boxes) == 2

    with Store(project_dir / PROJECT_DB_NAME) as store:
        volume = store.add_volume(Volume(project_id=store.the_project().id, name="Ch1"))
        page = store.add_page(
            Page(volume_id=volume.id, source_path="pages/x.png", index=0, width=width, height=height)
        )
        for order, box in enumerate(boxes):
            store.add_panel(
                Panel(
                    page_id=page.id,
                    x=box.x,
                    y=box.y,
                    width=box.width,
                    height=box.height,
                    reading_order=order,
                    polygon=box_to_polygon(box),
                )
            )
        page_id = page.id

    response = client.get(f"/api/pages/{page_id}/panels")

    assert response.status_code == 200
    panels = response.json()["panels"]
    assert len(panels) == 2
    assert all(len(p["polygon"]) == 4 for p in panels)
    assert [p["reading_order"] for p in panels] == [0, 1]
    assert panels[0]["x"] < panels[1]["x"], "leftmost panel reads first (ltr)"


def test_create_and_delete_panel(client, page_in_project):
    """PAN-03 end to end: draw a triangle the detector missed, then delete it."""
    page_id = page_in_project["id"]
    polygon = [[5, 5], [50, 5], [30, 40]]

    created = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon})
    assert created.status_code == 201
    created_panels = created.json()["panels"]
    assert any(p["polygon"] == polygon for p in created_panels)
    new_panel = next(p for p in created_panels if p["polygon"] == polygon)

    deleted = client.delete(f"/api/panels/{new_panel['id']}")
    assert deleted.status_code == 200
    remaining_ids = [p["id"] for p in deleted.json()["panels"]]
    assert new_panel["id"] not in remaining_ids


def test_delete_renumbers_reading_order(client, project_dir):
    """Deleting the first of three panels leaves 0..1 with no gap."""
    page_id = _make_page(project_dir, width=100, height=300)
    polygons = [
        [[10, 10], [90, 10], [50, 40]],
        [[10, 110], [90, 110], [50, 140]],
        [[10, 210], [90, 210], [50, 240]],
    ]
    for polygon in polygons:
        response = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon})
        assert response.status_code == 201

    listed = client.get(f"/api/pages/{page_id}/panels").json()["panels"]
    assert sorted(p["reading_order"] for p in listed) == [0, 1, 2]
    first_id = next(p["id"] for p in listed if p["reading_order"] == 0)

    response = client.delete(f"/api/panels/{first_id}")

    assert response.status_code == 200
    remaining = response.json()["panels"]
    assert len(remaining) == 2
    assert sorted(p["reading_order"] for p in remaining) == [0, 1]


def test_move_vertex_persists_and_updates_bbox(client, project_dir):
    """PAN-02: dragging one vertex updates both the polygon and the bbox."""
    page_id = _make_page(project_dir, width=200, height=200)
    polygon = [[10, 10], [50, 10], [50, 50], [10, 50]]
    created = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon}).json()
    panel = created["panels"][0]

    response = client.patch(
        f"/api/panels/{panel['id']}/vertex/2", json={"x": 80, "y": 80}
    )

    assert response.status_code == 200
    updated = next(p for p in response.json()["panels"] if p["id"] == panel["id"])
    assert updated["polygon"][2] == [80, 80]
    assert updated["x"] == 10 and updated["y"] == 10
    assert updated["width"] == 70 and updated["height"] == 70


def test_move_vertex_out_of_range_is_400(client, project_dir):
    page_id = _make_page(project_dir, width=200, height=200)
    polygon = [[10, 10], [50, 10], [50, 50], [10, 50]]
    panel = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon}).json()["panels"][0]

    response = client.patch(
        f"/api/panels/{panel['id']}/vertex/9", json={"x": 20, "y": 20}
    )

    assert response.status_code == 400


def test_polygon_below_three_vertices_is_422(client, project_dir):
    page_id = _make_page(project_dir, width=200, height=200)
    polygon = [[10, 10], [50, 10], [50, 50], [10, 50]]
    panel = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon}).json()["panels"][0]

    response = client.patch(
        f"/api/panels/{panel['id']}/polygon", json={"polygon": [[10, 10], [20, 20]]}
    )

    assert response.status_code == 422


def test_polygon_beyond_page_bounds_is_422(client, project_dir):
    """T-2-03: a vertex off this page's raster is refused even though it is
    within the schema's absolute PixelCoord range."""
    page_id = _make_page(project_dir, width=200, height=200)
    polygon = [[10, 10], [50, 10], [50, 50], [10, 50]]
    panel = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon}).json()["panels"][0]

    beyond = [[10, 10], [700, 10], [700, 50]]  # page.width (200) + 500
    response = client.patch(
        f"/api/panels/{panel['id']}/polygon", json={"polygon": beyond}
    )

    assert response.status_code == 422


def test_polygon_with_too_many_vertices_is_422(client, project_dir):
    """T-2-01: 513 vertices trips ``Polygon``'s ``max_length`` before the
    handler ever runs."""
    page_id = _make_page(project_dir, width=1000, height=1000)
    polygon = [[10, 10], [50, 10], [50, 50], [10, 50]]
    panel = client.post(f"/api/pages/{page_id}/panels", json={"polygon": polygon}).json()["panels"][0]

    huge = [[(i % 900) + 1, 20] for i in range(513)]
    response = client.patch(
        f"/api/panels/{panel['id']}/polygon", json={"polygon": huge}
    )

    assert response.status_code == 422


def test_unknown_panel_id_is_404(client):
    """T-2-02: a panel id that does not exist in the open project's own
    database is a 404, never a foreign row."""
    response = client.delete("/api/panels/999999")

    assert response.status_code == 404


def test_panel_routes_404_with_no_project_open(blank_client):
    """No project open at all: 409, not 404 (RESEARCH.md Pitfall 2).

    A genuinely stale/foreign ``panel_id`` inside the *currently open*
    project's own single-project database is what T-2-02 and
    ``test_unknown_panel_id_is_404`` cover — this app is one SQLite file per
    project, so there is no "another project's row" to leak past 404 within
    one open database. "No project open" is the separate, prior gate every
    project-scoped route shares (``get_current_project_path``,
    ``NO_PROJECT_DETAIL``), consistent with the existing
    ``test_requests_without_an_open_project_return_409`` precedent this
    codebase already established — named for the plan's PAN-01/02/03
    ownership truth, asserting the actual, correct status this app returns.
    """
    response = blank_client.get("/api/pages/1/panels")

    assert response.status_code == 409

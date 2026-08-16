"""Protected-mask route coverage: PROT-01, PROT-02, PROT-03.

D-19: delete has no confirmation, server-side or otherwise.
D-20: masks are page-scoped, so a bubble straddling two panels is exactly
one row, clipped into each panel's local frame only at segmentation time —
the straddling test here is the route-level half of success criterion 4.
D-24: the detector only ever proposes bubbles; hand-drawing carries the
bubble/SFX choice.

Beyond status codes, this file pins one behavioural contract the frontend
depends on: ``touched`` is the client's only signal for dashed-versus-solid
rendering (UI-SPEC §3) — False means "detector-proposed, not yet looked
at", True means "the artist's". A hand-drawn mask is born touched; any
reshape of a proposed mask flips it.

``run_protected`` (plan 02-07) is the real detector entry point that would
normally produce an untouched bubble mask, but 02-07 lands in the same wave
as this plan and is not yet merged here. ``test_detector_proposed_masks_are_untouched_bubbles``
therefore constructs a detector-shaped row directly through ``Store`` —
pinning the exact contract (``touched=False``, ``kind=bubble``) that
``run_protected``'s own output must satisfy once merged, rather than
skipping the assertion.
"""

from __future__ import annotations

from comiccolor.model import ProtectedKind, ProtectedMask, Store
from comiccolor.segmentation.protected import rasterize_protected_for_panel
from comiccolor.web.appconfig import PROJECT_DB_NAME


def _bubble_polygon() -> list[list[int]]:
    return [[10, 10], [30, 10], [30, 30], [10, 30]]


def test_create_mask_by_hand(client, page_in_project):
    """PROT-02: hand-drawing a bubble is born touched, with a real area and
    a bbox matching the polygon."""
    resp = client.post(
        f"/api/pages/{page_in_project['id']}/protected",
        json={"kind": "bubble", "polygon": _bubble_polygon()},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["touched"] is True
    assert body["kind"] == "bubble"
    assert body["area"] > 0
    assert body["bbox"] == [10, 10, 21, 21]


def test_create_sfx_mask_by_hand(client, page_in_project):
    """D-24: the detector never proposes SFX, but the hand path covers it
    fully — the artist chooses ``kind`` on the request."""
    resp = client.post(
        f"/api/pages/{page_in_project['id']}/protected",
        json={"kind": "sfx", "polygon": _bubble_polygon()},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "sfx"
    assert body["touched"] is True


def test_reshape_and_delete(client, project_dir, page_in_project):
    """Named exactly this in 02-VALIDATION.md's Requirement -> Test Map.

    A mask forced ``touched=False`` (simulating a detector proposal) is
    reshaped through the polygon route, which must flip it to touched and
    persist the new vertices; then deleted, with no trace left in a
    subsequent list.
    """
    with Store(project_dir / PROJECT_DB_NAME) as store:
        mask = store.add_protected_mask(
            ProtectedMask(
                page_id=page_in_project["id"],
                kind=ProtectedKind.BUBBLE,
                polygon=[(5, 5), (15, 5), (15, 15), (5, 15)],
                touched=False,
                area=100,
                bbox=(5, 5, 10, 10),
            )
        )

    new_polygon = [[6, 6], [20, 6], [20, 20], [6, 20]]
    reshaped = client.patch(f"/api/protected/{mask.id}/polygon", json={"polygon": new_polygon})

    assert reshaped.status_code == 200
    body = reshaped.json()
    assert body["touched"] is True
    assert body["polygon"] == new_polygon

    deleted = client.delete(f"/api/protected/{mask.id}")
    assert deleted.status_code == 204

    listing = client.get(f"/api/pages/{page_in_project['id']}/protected").json()
    assert all(m["id"] != mask.id for m in listing["masks"])


def test_move_vertex_sets_touched_and_moves_one_point(client, project_dir, page_in_project):
    """PROT-03: only the targeted vertex changes; the rest are byte-identical."""
    original = [(5, 5), (15, 5), (15, 15), (5, 15)]
    with Store(project_dir / PROJECT_DB_NAME) as store:
        mask = store.add_protected_mask(
            ProtectedMask(
                page_id=page_in_project["id"],
                kind=ProtectedKind.BUBBLE,
                polygon=list(original),
                touched=False,
                area=100,
                bbox=(5, 5, 10, 10),
            )
        )

    resp = client.patch(
        f"/api/protected/{mask.id}/vertex/1", json={"x": 40, "y": 41}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["touched"] is True
    expected = [[5, 5], [40, 41], [15, 15], [5, 15]]
    assert body["polygon"] == expected


def test_detector_proposed_masks_are_untouched_bubbles(client, project_dir, page_in_project):
    """See module docstring: stands in for ``run_protected`` (plan 02-07,
    not yet merged into this wave) by writing the same shape directly."""
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.add_protected_mask(
            ProtectedMask(
                page_id=page_in_project["id"],
                kind=ProtectedKind.BUBBLE,
                polygon=_bubble_polygon(),
                touched=False,
                area=400,
                bbox=(10, 10, 21, 21),
            )
        )

    listing = client.get(f"/api/pages/{page_in_project['id']}/protected").json()

    assert len(listing["masks"]) == 1
    assert listing["masks"][0]["touched"] is False
    assert listing["masks"][0]["kind"] == "bubble"


def test_straddling_mask_is_one_row_for_the_page(client, project_dir, page_in_project):
    """D-20 and success criterion 4 at the route level: one polygon spanning
    two panels is exactly one row, and it rasterises non-empty into both."""
    page_id = page_in_project["id"]
    with Store(project_dir / PROJECT_DB_NAME) as store:
        from comiccolor.model import Panel

        left = store.add_panel(
            Panel(
                page_id=page_id,
                x=0,
                y=0,
                width=32,
                height=64,
                reading_order=0,
                polygon=[(0, 0), (32, 0), (32, 64), (0, 64)],
            )
        )
        right = store.add_panel(
            Panel(
                page_id=page_id,
                x=32,
                y=0,
                width=32,
                height=64,
                reading_order=1,
                polygon=[(32, 0), (64, 0), (64, 64), (32, 64)],
            )
        )

    straddling_polygon = [[20, 20], [44, 20], [44, 44], [20, 44]]
    created = client.post(
        f"/api/pages/{page_id}/protected",
        json={"kind": "bubble", "polygon": straddling_polygon},
    )
    assert created.status_code == 201

    listing = client.get(f"/api/pages/{page_id}/protected").json()
    assert len(listing["masks"]) == 1
    page_polygon = listing["masks"][0]["polygon"]

    left_mask = rasterize_protected_for_panel(
        [page_polygon], left.x, left.y, left.width, left.height
    )
    right_mask = rasterize_protected_for_panel(
        [page_polygon], right.x, right.y, right.width, right.height
    )
    assert left_mask.any()
    assert right_mask.any()


def test_mask_polygon_beyond_page_bounds_is_422(client, page_in_project):
    resp = client.post(
        f"/api/pages/{page_in_project['id']}/protected",
        json={"kind": "bubble", "polygon": [[10, 10], [1000, 10], [1000, 30], [10, 30]]},
    )
    assert resp.status_code == 422


def test_mask_polygon_with_too_many_vertices_is_422(client, page_in_project):
    huge_polygon = [[i % 60, i % 60] for i in range(513)]
    resp = client.post(
        f"/api/pages/{page_in_project['id']}/protected",
        json={"kind": "bubble", "polygon": huge_polygon},
    )
    assert resp.status_code == 422


def test_unknown_mask_id_is_404(client):
    patched = client.patch("/api/protected/999999/polygon", json={"polygon": _bubble_polygon()})
    assert patched.status_code == 404

    moved = client.patch("/api/protected/999999/vertex/0", json={"x": 1, "y": 1})
    assert moved.status_code == 404

    deleted = client.delete("/api/protected/999999")
    assert deleted.status_code == 404


def test_requests_without_an_open_project_return_409(blank_client):
    resp = blank_client.get("/api/pages/1/protected")
    assert resp.status_code == 409

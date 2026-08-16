"""Gate confirm and Go-Back route coverage: D-06, D-07, D-08, PAN-01, PROT-01.

01-UI-SPEC.md §3 makes every Go-Back sentence a contract, not a convenience
— it is computed server-side from real counts and a target whose cost
cannot be computed is simply not offered. This file pins the exact copy
strings 02-UI-SPEC.md §4 and §8 fix, plus the zero-panel refusal, which is
the only thing standing between D-18's deliberate over-proposal, D-19's
routine deletion, and a page reaching Zones with nothing to segment.

``run_panels``/``run_protected`` (plan 02-07) are used directly to arrange
panel and mask counts, and direct ``Store`` writes are used elsewhere,
rather than driving the whole polygon/mask editor — this file is about the
gate and Go-Back contract, not panel/protected editing itself.
"""

from __future__ import annotations

import cv2

from comiccolor.model import Page, Panel, PipelineStage, ProtectedKind, ProtectedMask, Store
from comiccolor.pipeline.runner import run_panels, run_protected
from comiccolor.web.appconfig import PROJECT_DB_NAME
from tests.conftest import bubble_page


def _add_panels(store: Store, page_id: int, count: int) -> None:
    for i in range(count):
        store.add_panel(
            Panel(
                page_id=page_id,
                x=i * 10,
                y=0,
                width=10,
                height=10,
                reading_order=i,
                polygon=[(i * 10, 0), (i * 10 + 10, 0), (i * 10 + 10, 10), (i * 10, 10)],
            )
        )


def _add_masks(store: Store, page_id: int, count: int) -> None:
    for i in range(count):
        store.add_protected_mask(
            ProtectedMask(
                page_id=page_id,
                kind=ProtectedKind.BUBBLE,
                polygon=[(i, i), (i + 5, i), (i + 5, i + 5), (i, i + 5)],
                touched=i % 2 == 0,
                area=25,
                bbox=(i, i, 5, 5),
            )
        )


def _page_with_bubble(project_dir):
    """A page whose on-disk raster has one detectable speech bubble, so
    confirming out of ``panels`` runs real bubble detection rather than the
    always-zero-bubbles result a flat-colour fixture page would give.

    Built directly through ``Store`` (not the HTTP upload route), matching
    the pattern ``test_pipeline.py``'s ``bubble_page_page`` fixture already
    established for this exact raster.
    """
    grey, _ = bubble_page()
    height, width = grey.shape
    with Store(project_dir / PROJECT_DB_NAME) as store:
        from comiccolor.model import Volume

        vol = store.add_volume(Volume(project_id=1, name="Chapter 1"))
        page = store.add_page(
            Page(
                volume_id=vol.id,
                source_path="pages/bubble.png",
                index=0,
                width=width,
                height=height,
            )
        )
        cv2.imwrite(str(project_dir / "pages" / "bubble.png"), grey)
    return page


# ---- confirm_stage (Task 1) -------------------------------------------------


def test_confirm_from_panels_advances_and_runs_bubble_detection(client, project_dir):
    page = _page_with_bubble(project_dir)
    with Store(project_dir / PROJECT_DB_NAME) as store:
        _add_panels(store, page.id, 2)

    resp = client.post(f"/api/pages/{page.id}/stage/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"]["stage"] == "protected"
    assert body["detection_failed"] is False
    with Store(project_dir / PROJECT_DB_NAME) as store:
        assert store.page_by_id(page.id).stage == PipelineStage.PROTECTED
        assert len(store.protected_for_page(page.id)) == 1


def test_confirm_from_panels_with_zero_panels_is_409_and_stays(client, page_in_project):
    resp = client.post(f"/api/pages/{page_in_project['id']}/stage/confirm")

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Draw at least one panel before continuing."

    page = client.get(f"/api/pages/{page_in_project['id']}").json()
    assert page["stage"] == "panels"


def test_confirm_from_panels_when_detection_fails_still_advances_with_banner(
    client, project_dir, monkeypatch
):
    page = _page_with_bubble(project_dir)
    with Store(project_dir / PROJECT_DB_NAME) as store:
        _add_panels(store, page.id, 1)

    monkeypatch.setattr(
        "comiccolor.segmentation.bubbles.detect_bubbles",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    resp = client.post(f"/api/pages/{page.id}/stage/confirm")

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"]["stage"] == "protected"
    assert body["detection_failed"] is True
    assert body["detection_message"] == (
        "Bubble detection failed — you can still draw protected masks by hand."
    )
    with Store(project_dir / PROJECT_DB_NAME) as store:
        assert store.page_by_id(page.id).stage == PipelineStage.PROTECTED


def test_confirm_from_protected_with_zero_masks_advances_to_zones(
    client, project_dir, page_in_project
):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)

    resp = client.post(f"/api/pages/{page_in_project['id']}/stage/confirm")

    assert resp.status_code == 200
    assert resp.json()["page"]["stage"] == "zones"


def test_confirm_from_zones_advances_to_propose_without_error(
    client, project_dir, page_in_project
):
    """``zones`` has no runner (D-11); confirming out of it must not surface
    ``StageNotImplementedError`` to the artist — it advances silently."""
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.ZONES)

    resp = client.post(f"/api/pages/{page_in_project['id']}/stage/confirm")

    assert resp.status_code == 200
    assert resp.json()["page"]["stage"] == "propose"


def test_confirm_from_export_is_409(client, project_dir, page_in_project):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.EXPORT)

    resp = client.post(f"/api/pages/{page_in_project['id']}/stage/confirm")

    assert resp.status_code == 409


def test_confirm_unknown_page_id_is_404(client):
    resp = client.post("/api/pages/999999/stage/confirm")
    assert resp.status_code == 404


def test_confirm_no_project_open_is_409(blank_client):
    resp = blank_client.post("/api/pages/1/stage/confirm")
    assert resp.status_code == 409


# ---- go-back-targets and go-back (Task 2) -----------------------------------


def test_go_back_targets_from_protected_panels_body_and_label(
    client, project_dir, page_in_project
):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)
        _add_masks(store, page_in_project["id"], 4)

    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    assert resp.status_code == 200
    targets = {t["stage"]: t for t in resp.json()}
    panels_target = targets["panels"]
    assert panels_target["body"] == (
        "This discards 4 protected masks and re-runs bubble detection for the whole page."
    )
    assert panels_target["confirm_label"] == "Go back and discard 4 edits"
    assert panels_target["heading"] == "Go back to Panels?"
    assert panels_target["cancel_label"] == "Stay on Protected"


def test_go_back_targets_from_protected_import_body_and_label(
    client, project_dir, page_in_project
):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        _add_panels(store, page_in_project["id"], 6)
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)
        _add_masks(store, page_in_project["id"], 4)

    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    targets = {t["stage"]: t for t in resp.json()}
    import_target = targets["import"]
    assert import_target["body"] == (
        "This discards 6 panel polygons and 4 protected masks, and re-runs"
        " panel detection for the whole page."
    )
    assert import_target["confirm_label"] == "Go back and discard 10 edits"


def test_go_back_targets_singular_counts_use_singular_wording(
    client, project_dir, page_in_project
):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        _add_panels(store, page_in_project["id"], 1)
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)
        _add_masks(store, page_in_project["id"], 1)

    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    targets = {t["stage"]: t for t in resp.json()}
    assert targets["panels"]["confirm_label"] == "Go back and discard 1 edit"
    assert "1 protected mask " in targets["panels"]["body"]
    assert "1 protected masks" not in targets["panels"]["body"]
    import_body = targets["import"]["body"]
    assert "1 panel polygon " in import_body
    assert "1 panel polygons" not in import_body


def test_go_back_targets_from_panels_offers_only_import(client, page_in_project):
    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    assert resp.status_code == 200
    stages = [t["stage"] for t in resp.json()]
    assert stages == ["import"]


def test_go_back_targets_from_import_offers_none(client, project_dir, page_in_project):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.IMPORT)

    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    assert resp.status_code == 200
    assert resp.json() == []


def test_go_back_targets_every_body_contains_a_digit(client, project_dir, page_in_project):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)

    resp = client.get(f"/api/pages/{page_in_project['id']}/stage/go-back-targets")

    for target in resp.json():
        assert any(ch.isdigit() for ch in target["body"])


def test_go_back_to_panels_discards_all_masks_including_touched(
    client, project_dir, page_in_project
):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)
        store.add_protected_mask(
            ProtectedMask(
                page_id=page_in_project["id"],
                kind=ProtectedKind.BUBBLE,
                polygon=[(1, 1), (6, 1), (6, 6), (1, 6)],
                touched=True,
                area=25,
                bbox=(1, 1, 5, 5),
            )
        )

    resp = client.post(
        f"/api/pages/{page_in_project['id']}/stage/go-back", json={"target": "panels"}
    )

    assert resp.status_code == 200
    assert resp.json()["page"]["stage"] == "panels"
    with Store(project_dir / PROJECT_DB_NAME) as store:
        assert store.protected_for_page(page_in_project["id"]) == []
        assert store.page_by_id(page_in_project["id"]).stage == PipelineStage.PANELS


def test_go_back_to_import_discards_panels_and_masks(client, project_dir, page_in_project):
    with Store(project_dir / PROJECT_DB_NAME) as store:
        _add_panels(store, page_in_project["id"], 2)
        store.set_page_stage(page_in_project["id"], PipelineStage.PROTECTED)
        _add_masks(store, page_in_project["id"], 3)

    resp = client.post(
        f"/api/pages/{page_in_project['id']}/stage/go-back", json={"target": "import"}
    )

    assert resp.status_code == 200
    assert resp.json()["page"]["stage"] == "import"
    with Store(project_dir / PROJECT_DB_NAME) as store:
        assert store.panels_for_page(page_in_project["id"]) == []
        assert store.protected_for_page(page_in_project["id"]) == []


def test_go_back_refuses_a_target_not_earlier_than_current_stage(client, page_in_project):
    resp = client.post(
        f"/api/pages/{page_in_project['id']}/stage/go-back", json={"target": "protected"}
    )
    assert resp.status_code == 409

    resp_same = client.post(
        f"/api/pages/{page_in_project['id']}/stage/go-back", json={"target": "panels"}
    )
    assert resp_same.status_code == 409


def test_go_back_unknown_page_id_is_404(client):
    resp = client.post("/api/pages/999999/stage/go-back", json={"target": "import"})
    assert resp.status_code == 404


def test_go_back_targets_no_project_open_is_409(blank_client):
    resp = blank_client.get("/api/pages/1/stage/go-back-targets")
    assert resp.status_code == 409
